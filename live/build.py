"""Build the data behind unbundle live: fetch, fit, summarize, validate, write atomically.

    python -m live.build --out web/data [--prices CSV] [--save-prices CSV] [--overrides CSV]
                         [--allow-older] [--offline-sample]

For each fund in ``live/funds.csv`` this fetches monthly total returns from Yahoo Finance
(from 1990, in batches of 8 with retries), replaces the months listed in
``live/overrides.csv`` (sourced corrections where Yahoo's adjusted closes are known to be
wrong), fits the Carhart model on the trailing 120
months ending at ``through`` - the earlier of the last month of factor data and the most
common last month across the funds - plus the Fama-French five factors with momentum as a
robustness check, and 36-month rolling fits over the fund's whole history. It writes
``meta.json``, ``index.json`` and ``funds/<TICKER>.json`` (schema: :mod:`live.validate`).

It never replaces good data with bad. A fund whose fetch fails, or whose returns fail a
sanity check (a missing month inside the window, a monthly return beyond ±60%), keeps its
previous file marked ``stale``; with no previous file it is left out and listed in
``meta.excluded``. So does a fund whose returns now end before its published window does
(a short Yahoo response): data never moves backwards. The whole build aborts, writing
nothing, if more than 20% of the fetches fail, the factor data fails to load, the new data
would end before the published ``through`` (unless ``--allow-older``), more than 5 funds
show a past monthly return revised by more than 0.5 percentage points against the
published growth series, a control fund (SPY, VTI, IWM, IWD, IWF, MTUM) fails its
known-answer check, or the output fails validation. Files are staged in a temporary
directory, validated, then moved into place with ``os.replace``, ``meta.json`` last.
``generated_at`` changes only when some other content did, so a rerun on the same data
leaves every byte as it was. A fund whose refit differs from its published record only by
download noise (Yahoo's adjusted closes move by about one part in a million between
downloads) keeps the published record, so a fresh download of unchanged prices changes
nothing either.

``--prices`` reads monthly returns from a CSV (a ``month`` column, then one column per
ticker) instead of Yahoo; ``--save-prices`` writes the returns a successful run fetched, in
that format and before the overrides, so a real fetch can be replayed offline. Keep saved
prices out of the repository: Yahoo's terms restrict redistributing them.

``--offline-sample`` takes the factors from unbundle's bundled Ken French sample (1949 to
March 2017) instead of downloading them. The sample has no RMW or CMA, so the robustness
fit is a second Carhart fit: ``models.ff5mom`` then holds a fit whose ``model`` is
``"carhart"``, ``meta.robustness_model`` says ``"carhart"``, and no verdict gets a
robustness sentence. This mode is for tests and offline development, never for the site.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from functools import partial
from importlib import metadata
from pathlib import Path
from typing import Any

import pandas as pd

from unbundle import FactorModel, excess_returns, fetch_yahoo, load_factors, read_returns_csv

from . import (
    FUNDS_CSV,
    HEADLINE_MODEL,
    HISTORY_START,
    KINDS,
    MIN_MONTHS,
    OVERRIDES_CSV,
    ROBUSTNESS_MODEL,
    ROLLING_WINDOW,
    SCHEMA_VERSION,
    WINDOW_MONTHS,
    Fund,
    Override,
    read_funds,
    read_overrides,
)
from . import summarize as s
from .validate import is_month, validate

BATCH_SIZE = 8
ATTEMPTS = 3
BACKOFF = 2.0  # seconds after the first failed attempt; doubles after each further one
PAUSE = 2.0  # seconds between batches
MAX_FAILED_SHARE = 0.20
MAX_MONTHLY_RETURN = 0.60
MAX_REVISION = 0.005  # a past monthly return moving more than 0.5 percentage points
MAX_REVISED_FUNDS = 5
# Yahoo's dividend-adjusted closes differ by about 1e-6 from one download to the next, which
# moves the sixth decimal of most outputs; a refit within these tolerances of the published
# record keeps the published record (see unchanged())
NOISE = 1e-4
NOISE_LOOSE = 2e-3  # t-statistics, p-values, information ratios and factor shares move more
LOOSE_KEYS = frozenset({"t", "alpha_t", "alpha_p", "information_ratio", "factor_share"})
VERDICT_KEYS = frozenset({"verdict", "verdict_short"})

SOURCES = {
    "factors": "Kenneth R. French Data Library",
    "prices": "Yahoo Finance adjusted closes",
}
SAMPLE_SOURCES = {
    **SOURCES,
    "factors": "Kenneth R. French Data Library (unbundle's bundled 1949-2017 sample)",
}

Fetch = Callable[..., pd.DataFrame]
Log = Callable[[str], object]


class BuildError(Exception):
    """The build aborts: the new data cannot be trusted, and nothing has been written."""


# -- prices --------------------------------------------------------------------------------
def _attempt(
    fetch: Fetch,
    tickers: list[str],
    start: str,
    attempts: int,
    sleep: Callable[[float], object],
    log: Log,
) -> pd.DataFrame | None:
    for k in range(attempts):
        try:
            return fetch(tickers, start=start)
        except Exception as exc:  # yfinance raises many kinds; any failure means retry
            log(f"  fetch {' '.join(tickers)}: attempt {k + 1}/{attempts} failed: {exc}")
            sleep(BACKOFF * 2**k)
    return None


def fetch_returns(
    tickers: Sequence[str],
    fetch: Fetch = fetch_yahoo,
    *,
    start: str = HISTORY_START,
    sleep: Callable[[float], object] = time.sleep,
    log: Log = print,
) -> pd.DataFrame:
    """Monthly total returns for ``tickers``, fetched in batches of 8.

    ``fetch(tickers, start=...)`` returns monthly returns with one column per ticker, like
    :func:`unbundle.fetch_yahoo`. Each batch gets 3 attempts, sleeping 2, 4 and 8 seconds
    after failures; a batch that still fails is fetched one ticker at a time, so one bad
    ticker cannot sink the other seven. Tickers that never arrive are missing from the
    result.
    """
    tickers = list(tickers)
    frames = []
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        if i:
            sleep(PAUSE)
        got = _attempt(fetch, batch, start, ATTEMPTS, sleep, log)
        if got is not None:
            frames.append(got)
        elif len(batch) > 1:
            for ticker in batch:
                sleep(PAUSE)
                single = _attempt(fetch, [ticker], start, 1, sleep, log)
                if single is not None:
                    frames.append(single)
    return tidy_returns(pd.concat(frames, axis=1) if frames else pd.DataFrame(), tickers, start)


def tidy_returns(frame: pd.DataFrame, tickers: Sequence[str], start: str) -> pd.DataFrame:
    """The requested tickers that have any data, on a monthly PeriodIndex from ``start``."""
    frame = frame.copy()
    if not isinstance(frame.index, pd.PeriodIndex):
        frame.index = pd.PeriodIndex(pd.to_datetime(frame.index), freq="M")
    frame.index.name = "month"
    frame = frame.loc[:, ~frame.columns.duplicated()].sort_index().loc[start:]
    keep = [t for t in tickers if t in frame.columns and frame[t].notna().any()]
    return frame.loc[:, keep].astype(float)


def save_returns(returns: pd.DataFrame, path: str | os.PathLike) -> None:
    """Write monthly returns in the CSV format ``--prices`` reads."""
    returns.rename_axis("month").to_csv(path)


def apply_overrides(
    returns: pd.DataFrame, overrides: Sequence[Override], log: Log = print
) -> pd.DataFrame:
    """``returns`` with each override's month replaced by its sourced value.

    An override for a ticker or month that ``returns`` does not have is skipped.
    """
    returns = returns.copy()
    for o in overrides:
        m = pd.Period(o.month, freq="M")
        if o.ticker not in returns.columns or m not in returns.index:
            continue
        old = returns.at[m, o.ticker]
        was = "a missing month" if pd.isna(old) else f"{s.pct(old, '+.2f')}%"
        returns.at[m, o.ticker] = o.value
        log(f"  {o.ticker:<6} {o.month} return set to {s.pct(o.value, '+.2f')}% (was {was})")
    return returns


# -- one fund ------------------------------------------------------------------------------
def usable_history(returns: pd.Series, through: pd.Period) -> tuple[pd.Series, pd.Series] | str:
    """A fund's headline window and the unbroken history ending with it - or why not.

    The window is the trailing 120 months ending at ``through`` (or at the fund's last
    month, if earlier), or every month since inception if that is at least 36. The history,
    for the rolling fits, is the run of months without a gap that ends with the window.
    Returns a reason instead when the fund is too short, has a missing month inside the
    window, or has a monthly return beyond ±60% (a data error, not a fund).
    """
    valid = returns.loc[:through].dropna()
    if valid.empty:
        return f"no returns through {s.month(through)}"
    first, end = valid.index[0], valid.index[-1]
    full = returns.reindex(pd.period_range(first, end, freq="M"))
    window = full.loc[max(first, end - (WINDOW_MONTHS - 1)) :]
    if window.isna().any():
        return f"a missing month inside the window ({s.month(window.index[window.isna()][0])})"
    if len(window) < MIN_MONTHS:
        return f"only {len(window)} months of returns (need {MIN_MONTHS})"
    gaps = full.index[full.isna()]
    history = full.loc[gaps[-1] + 1 :] if len(gaps) else full
    worst = history.abs().idxmax()
    if abs(history[worst]) > MAX_MONTHLY_RETURN:
        return f"a monthly return of {history[worst]:+.0%} in {s.month(worst)}"
    return window, history


def fit_fund(
    fund: Fund,
    window: pd.Series,
    history: pd.Series,
    factors: pd.DataFrame,
    robust_factors: pd.DataFrame,
    robust_model: str,
    *,
    stale: bool,
) -> dict[str, Any]:
    """Fit one fund's headline, robustness and rolling models; its ``funds/<T>.json`` record."""
    name = fund.ticker
    headline = FactorModel(window.rename(name), factors, HEADLINE_MODEL).fit()[name]
    robust = FactorModel(window.rename(name), robust_factors, robust_model).fit()[name]
    if headline.nobs != len(window) or robust.nobs != len(window):
        raise BuildError(f"{name}: the factor data does not cover every month of its window")
    excess = excess_returns(history.rename(name), factors["RF"])[name]
    roll = s.rolling(excess, factors.loc[excess.index, list(headline.factors)], ROLLING_WINDOW)
    return s.fund_record(fund, headline, robust, roll, stale=stale)


def largest_revision(previous: Mapping[str, Any] | None, returns: pd.Series) -> float:
    """The largest change in a past monthly return against a previously published record."""
    if not previous:
        return 0.0
    worst = 0.0
    for m, old in s.growth_returns(previous["growth"]).items():
        new = returns.get(pd.Period(m, freq="M"))
        if new is not None and pd.notna(new):
            worst = max(worst, abs(float(new) - old))
    return worst


def unchanged(new: Any, old: Any, key: str = "") -> bool:
    """True when a refitted fund record says what the published one says, up to Yahoo's noise.

    Keys, strings, booleans, integers, list lengths and expense ratios must match exactly.
    Other numbers may differ by ``NOISE`` (``NOISE_LOOSE`` for t-statistics, p-values,
    information ratios and factor shares), relative to the number when it is above 1 in size.
    The verdicts are left out: noise can move a rounded number in them across a rounding
    boundary, and the published record's verdict matches its own numbers, which
    :func:`keep_published` checks against the current wording.
    """
    if isinstance(new, dict):
        return (
            isinstance(old, dict)
            and new.keys() == old.keys()
            and all(unchanged(new[k], old[k], k) for k in new if k not in VERDICT_KEYS)
        )
    if isinstance(new, list):
        return (
            isinstance(old, list)
            and len(new) == len(old)
            and all(unchanged(u, v, key) for u, v in zip(new, old, strict=True))
        )
    if (
        isinstance(new, float)
        and isinstance(old, (int, float))
        and not isinstance(old, bool)
        and key != "expense_ratio"
    ):
        tolerance = NOISE_LOOSE if key in LOOSE_KEYS else NOISE
        return abs(new - old) <= tolerance * max(1.0, abs(old))
    return type(new) is type(old) and new == old


def keep_published(new: Mapping[str, Any], old: Mapping[str, Any] | None) -> bool:
    """True when the published record ``old`` can stand for the refit ``new``.

    That is when they differ only by download noise (:func:`unchanged`) and the published
    verdict is the one the current wording gives for the published numbers.
    """
    return (
        old is not None
        and unchanged(new, old)
        and s.model_verdict(old["ticker"], old["kind"], old["models"])
        == (old["verdict_short"], old["verdict"])
    )


def control_checks(fits: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, bool]]:
    """Known-answer tests on headline Carhart fits: ``(description, passed)`` per check.

    Index funds with well-known exposures must show them, or something is wrong with the
    prices, the factors or the fit. A check is skipped only when its fund is not in ``fits``.
    """

    def beta(ticker: str, factor: str) -> float:
        return fits[ticker]["betas"][factor]["coef"]

    out = []
    for ticker in ("SPY", "VTI"):
        if ticker in fits:
            b, r2 = beta(ticker, "MktRF"), fits[ticker]["r2"]
            out.append(
                (
                    f"{ticker} market β {s.signed(b, '.2f')} in [0.93, 1.07], R² {r2:.2f} > 0.95",
                    0.93 <= b <= 1.07 and r2 > 0.95,
                )
            )
    for ticker, factor, sign, bound in (
        ("IWM", "SMB", ">", 0.5),
        ("IWD", "HML", ">", 0.15),
        ("IWF", "HML", "<", 0.0),
        ("MTUM", "Mom", ">", 0.1),
    ):
        if ticker in fits:
            b = beta(ticker, factor)
            passed = b > bound if sign == ">" else b < bound
            out.append((f"{ticker} {factor} β {s.signed(b, '.2f')} {sign} {bound:g}", passed))
    return out


# -- writing -------------------------------------------------------------------------------
def to_json(obj: Any) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _reusable(rec: Any) -> bool:
    """A previously written fund record of this schema (the build validates it again)."""
    return (
        isinstance(rec, dict)
        and rec.get("schema_version") == SCHEMA_VERSION
        and isinstance(rec.get("window"), dict)
        and isinstance(rec.get("growth"), dict)
    )


def current_files(out: Path) -> dict[str, bytes]:
    """The data files now in ``out``, as ``{relative path: bytes}``."""
    paths = [out / "meta.json", out / "index.json", *sorted((out / "funds").glob("*.json"))]
    return {p.relative_to(out).as_posix(): p.read_bytes() for p in paths if p.is_file()}


def write_atomically(out: Path, files: Mapping[str, bytes]) -> list[str]:
    """Stage ``files`` in a temporary directory, validate them, then move them into ``out``.

    Fund files go first, then fund files no longer listed are removed, then ``index.json``,
    then ``meta.json``. Files whose bytes are unchanged are left alone. Returns the paths
    that changed. Nothing outside the temporary directory is created until the files have
    passed validation, not even ``out`` or its parents.
    """
    anchor = out.parent  # the nearest existing directory, so os.replace stays on one disk
    while not anchor.is_dir():
        anchor = anchor.parent
    stage = Path(tempfile.mkdtemp(prefix=".live-build-", dir=anchor))
    try:
        for rel, data in files.items():
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_bytes(data)
        errors = validate(stage)
        if errors:
            raise BuildError("the new data failed validation:\n  " + "\n  ".join(errors))
        (out / "funds").mkdir(parents=True, exist_ok=True)
        changed = []

        def replace(rel: str) -> None:
            target = out / rel
            if target.is_file() and target.read_bytes() == files[rel]:
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / rel, target)
            changed.append(rel)

        for rel in sorted(r for r in files if r.startswith("funds/")):
            replace(rel)
        for path in sorted((out / "funds").glob("*.json")):
            if f"funds/{path.name}" not in files:
                path.unlink()
                changed.append(f"funds/{path.name} (removed)")
        replace("index.json")
        replace("meta.json")
        return changed
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _versions() -> dict[str, str]:
    out = {}
    for package in ("unbundle", "sandwich"):
        try:
            out[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            out[package] = "unknown"
    return out


def _line(rec: Mapping[str, Any]) -> str:
    win = rec["window"]
    flags = [f for f in ("stale", "short_history") if rec[f]]
    return (
        f"  {rec['ticker']:<6} {rec['kind']:<12} {win['start']}..{win['end']} {win['months']:>3} mo"
        f"  excess {s.pct(rec['excess_annual']):>6}%  alpha {s.pct(rec['alpha_annual']):>5}%"
        f"  t {s.signed(rec['alpha_t'], '+.2f'):>6}  R² {rec['r2']:.2f}  {rec['verdict_short']}"
        + (f"  [{', '.join(flags)}]" if flags else "")
    )


# -- the build -----------------------------------------------------------------------------
def build(
    out: str | os.PathLike,
    funds: Sequence[Fund],
    *,
    fetch: Fetch = fetch_yahoo,
    prices: pd.DataFrame | None = None,
    load: Callable[[str], pd.DataFrame] = load_factors,
    robust_model: str = ROBUSTNESS_MODEL,
    sources: Mapping[str, str] = SOURCES,
    save_prices: str | os.PathLike | None = None,
    overrides: Sequence[Override] = (),
    allow_older: bool = False,
    today: date | None = None,
    sleep: Callable[[float], object] = time.sleep,
    log: Log = print,
) -> dict[str, Any]:
    """Build the site's data into ``out`` and return the new ``meta.json`` contents.

    ``prices`` (monthly returns, one column per ticker) replaces the fetch; otherwise
    ``fetch`` is called as in :func:`fetch_returns`. ``load(model)`` returns factor returns
    plus ``RF`` like :func:`unbundle.load_factors`. ``overrides`` replace single monthly
    returns before anything is fitted. ``save_prices`` receives the returns as fetched, only
    once the build has succeeded. ``allow_older`` lets the data end before the published
    ``through``, and a fund's window end before its published one. Raises
    :class:`BuildError`, having written nothing, when the new data cannot be trusted.
    """
    out = Path(out)
    today = today or date.today()
    tickers = [f.ticker for f in funds]
    if not tickers:
        raise BuildError("the fund list is empty")

    try:
        factors = load(HEADLINE_MODEL)
        robust_factors = factors if robust_model == HEADLINE_MODEL else load(robust_model)
    except Exception as exc:  # a download, parse or cache failure: nothing to build on
        raise BuildError(f"the factor data failed to load: {exc}") from exc
    if factors.empty or robust_factors.empty:
        raise BuildError("the factor data is empty")
    factors_through = min(factors.index[-1], robust_factors.index[-1])

    if prices is None:
        log(f"fetching {len(tickers)} tickers from {HISTORY_START}")
        returns = fetch_returns(tickers, fetch, sleep=sleep, log=log)
    else:
        returns = tidy_returns(prices, tickers, HISTORY_START)
    fetched = returns
    failed = [t for t in tickers if t not in returns.columns]
    if len(failed) > MAX_FAILED_SHARE * len(tickers):
        raise BuildError(f"{len(failed)} of {len(tickers)} tickers failed: {' '.join(failed)}")
    returns = apply_overrides(returns, overrides, log)

    lasts = Counter(returns[t].last_valid_index() for t in returns.columns)
    top = max(lasts.values())
    through = min(factors_through, max(m for m, n in lasts.items() if n == top))
    before = _read_json(out / "meta.json")
    published = before.get("through") if isinstance(before, dict) else None
    if is_month(published) and s.month(through) < published and not allow_older:
        raise BuildError(
            f"the new data ends {s.month(through)} (factors through {s.month(factors_through)}), "
            f"before the published {published}; --allow-older publishes it anyway"
        )

    previous = {}
    for t in tickers:
        rec = _read_json(out / "funds" / f"{t}.json")
        if _reusable(rec):
            previous[t] = rec

    records: dict[str, dict[str, Any]] = {}
    fits: dict[str, dict[str, Any]] = {}
    excluded: list[str] = []
    revised: list[str] = []
    log(f"through {s.month(through)} (factors through {s.month(factors_through)})")
    for fund in funds:
        t = fund.ticker
        usable = "the fetch failed" if t in failed else usable_history(returns[t], through)
        old = previous.get(t)
        old_end = old["window"].get("end") if old else None
        if not isinstance(usable, str) and is_month(old_end) and not allow_older:
            end = s.month(usable[0].index[-1])
            if end < old_end:
                usable = f"its returns now end {end}, before the published {old_end}"
        if isinstance(usable, str):
            if old is not None and is_month(old_end) and old_end <= s.month(through):
                records[t] = {**old, "stale": True}
                log(f"  {t:<6} stale: {usable}; kept {old_end} data")
            else:
                excluded.append(t)
                log(f"  {t:<6} excluded: {usable}")
            continue
        window, history = usable
        rec = fit_fund(
            fund,
            window,
            history,
            factors,
            robust_factors,
            robust_model,
            stale=window.index[-1] < through,
        )
        if keep_published(rec, previous.get(t)):
            rec = previous[t]  # the same data up to download noise: keep the published bytes
        records[t] = fits[t] = rec
        log(_line(rec))
        revision = largest_revision(previous.get(t), returns[t])
        if revision > MAX_REVISION:
            revised.append(t)
            log(f"  {t:<6} a past monthly return moved by {100 * revision:.2f} points")
    if len(revised) > MAX_REVISED_FUNDS:
        raise BuildError(
            f"{len(revised)} funds had past returns revised by more than "
            f"{100 * MAX_REVISION:.1f} points: {' '.join(revised)}"
        )

    checks = control_checks({t: r["models"][HEADLINE_MODEL] for t, r in fits.items()})
    for text, passed in checks:
        log(f"  control {text}: {'ok' if passed else 'FAILED'}")
    failures = [text for text, passed in checks if not passed]
    if failures:
        raise BuildError("control-group check failed: " + "; ".join(failures))
    if not records:
        raise BuildError("no fund could be built")

    order = sorted(records.values(), key=lambda r: (KINDS.index(r["kind"]), r["ticker"]))
    index = {"through": s.month(through), "funds": [s.summary(r) for r in order]}
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": None,
        "through": s.month(through),
        "factors_through": s.month(factors_through),
        "headline_model": HEADLINE_MODEL,
        "robustness_model": robust_model,
        "window_months": WINDOW_MONTHS,
        "min_months": MIN_MONTHS,
        "rolling_window": ROLLING_WINDOW,
        "funds": len(records),
        "stale": sorted(t for t, r in records.items() if r["stale"]),
        "excluded": sorted(excluded),
        "sources": dict(sources),
        "versions": _versions(),
    }
    files = {f"funds/{t}.json": to_json(r) for t, r in records.items()}
    files["index.json"] = to_json(index)
    # generated_at moves only when something else changed: try the previous date first
    meta["generated_at"] = before.get("generated_at") if isinstance(before, dict) else None
    files["meta.json"] = to_json(meta)
    if meta["generated_at"] is None or files != current_files(out):
        meta["generated_at"] = today.isoformat()
        files["meta.json"] = to_json(meta)

    changed = write_atomically(out, files)
    if save_prices is not None:
        save_returns(fetched, save_prices)
        log(f"saved the monthly returns of {fetched.shape[1]} tickers to {save_prices}")
    log(
        f"{len(records)} funds ({len(meta['stale'])} stale, {len(excluded)} excluded) "
        f"through {meta['through']}: "
        + (f"{len(changed)} file(s) changed in {out}" if changed else f"no changes in {out}")
    )
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m live.build",
        description="Build the unbundle live data: meta.json, index.json and funds/*.json.",
    )
    parser.add_argument("--out", required=True, help="the data directory, e.g. web/data")
    parser.add_argument(
        "--funds", default=str(FUNDS_CSV), help="the fund list (default: live/funds.csv)"
    )
    parser.add_argument(
        "--prices",
        metavar="CSV",
        help="monthly returns from a CSV (a month column, then one column per ticker) "
        "instead of Yahoo Finance",
    )
    parser.add_argument(
        "--save-prices",
        metavar="PATH",
        help="also write the monthly returns used to a CSV that --prices can replay "
        "(keep it out of the repository: Yahoo's terms restrict redistribution)",
    )
    parser.add_argument(
        "--overrides",
        metavar="CSV",
        default=str(OVERRIDES_CSV),
        help="sourced corrections to single monthly returns (default: live/overrides.csv)",
    )
    parser.add_argument(
        "--allow-older",
        action="store_true",
        help="publish data that ends before the published data (normally an abort)",
    )
    parser.add_argument(
        "--offline-sample",
        action="store_true",
        help="factors from unbundle's bundled 1949-2017 Ken French sample, no download; "
        "it has no RMW/CMA, so the robustness fit is Carhart too (for tests, not the site)",
    )
    args = parser.parse_args(argv)
    try:
        funds = read_funds(args.funds)
        overrides = read_overrides(args.overrides)
        prices = read_returns_csv(args.prices) if args.prices else None
    except (OSError, ValueError) as exc:
        print(f"live.build: {exc}", file=sys.stderr)
        return 1
    options: dict[str, Any] = {}
    if args.offline_sample:
        options = {
            "load": partial(load_factors, source="sample"),
            "robust_model": HEADLINE_MODEL,
            "sources": SAMPLE_SOURCES,
        }
    try:
        build(
            args.out,
            funds,
            prices=prices,
            save_prices=args.save_prices,
            overrides=overrides,
            allow_older=args.allow_older,
            **options,
        )
    except BuildError as exc:
        print(f"live.build: aborted, nothing written: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
