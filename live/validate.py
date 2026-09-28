"""Check the data behind unbundle live before anything publishes it.

    python -m live.validate web/data

Every file is checked against the schema - field names, types, numbers rounded to 6
decimals, ``"YYYY-MM"`` months - and against the invariants the site relies on:
contributions that add up to the excess return, growth series one entry longer than the
window and starting at 1.0, the fee arithmetic, verdicts that agree with the t-statistic,
and an index that matches the fund files. Exits 1 listing every problem. ``live.build``
runs the same checks on its output before moving it into place.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from unbundle import FACTOR_SETS, newey_west_lags

from . import HEADLINE_MODEL, KINDS, ROBUSTNESS_MODEL, SCHEMA_VERSION, TICKER, VERDICTS
from .summarize import SUMMARY_KEYS, Z95, factor_share, verdict_short

SUM_TOLERANCE = 1e-9  # contributions vs excess_annual
ROUNDING = 5e-6  # identities between separately rounded numbers

_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_DATE = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")

Check = Callable[[Any], bool]


# -- types ---------------------------------------------------------------------------------
def is_num(x: Any) -> bool:
    """A finite JSON number with at most 6 decimals."""
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(x)
        and round(x, 6) == x
    )


def is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def is_str(x: Any) -> bool:
    return isinstance(x, str)


def is_text(x: Any) -> bool:
    return isinstance(x, str) and x.strip() != ""


def is_bool(x: Any) -> bool:
    return isinstance(x, bool)


def is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def is_month(x: Any) -> bool:
    return isinstance(x, str) and _MONTH.fullmatch(x) is not None


def is_date(x: Any) -> bool:
    return isinstance(x, str) and _DATE.fullmatch(x) is not None


def is_ticker(x: Any) -> bool:
    return isinstance(x, str) and TICKER.fullmatch(x) is not None


def is_model(x: Any) -> bool:
    return isinstance(x, str) and x in FACTOR_SETS


def optional(check: Check) -> Check:
    return lambda x: x is None or check(x)


def list_of(check: Check) -> Check:
    return lambda x: isinstance(x, list) and all(check(v) for v in x)


def str_map(x: Any) -> bool:
    return isinstance(x, dict) and all(is_str(k) and is_str(v) for k, v in x.items())


def is_interval(x: Any) -> bool:
    return isinstance(x, list) and len(x) == 2 and all(is_num(v) for v in x) and x[0] <= x[1]


META = {
    "schema_version": is_int,
    "generated_at": is_date,
    "through": is_month,
    "factors_through": is_month,
    "headline_model": is_model,
    "robustness_model": is_model,
    "window_months": is_int,
    "min_months": is_int,
    "rolling_window": is_int,
    "funds": is_int,
    "stale": list_of(is_ticker),
    "excluded": list_of(is_ticker),
    "sources": str_map,
    "versions": str_map,
}
INDEX = {"through": is_month, "funds": lambda x: isinstance(x, list)}
WINDOW = {"start": is_month, "end": is_month, "months": is_int}
SUMMARY = {
    "ticker": is_ticker,
    "name": is_text,
    "kind": lambda x: x in KINDS,
    "category": is_text,
    "expense_ratio": is_num,
    "window": is_dict,
    "short_history": is_bool,
    "stale": is_bool,
    "excess_annual": is_num,
    "alpha_annual": is_num,
    "alpha_t": is_num,
    "alpha_p": is_num,
    "r2": is_num,
    "factor_share": optional(is_num),
    "verdict_short": lambda x: x in VERDICTS,
}
FUND = {
    **SUMMARY,
    "schema_version": is_int,
    "expense_ratio_as_of": is_str,
    "expense_ratio_source": is_str,
    "note": is_str,
    "verdict": is_text,
    "models": is_dict,
    "fee": is_dict,
    "growth": is_dict,
    "rolling": is_dict,
}
MODEL_FIT = {
    "model": is_model,
    "factors": list_of(is_str),
    "nobs": is_int,
    "maxlags": is_int,
    "alpha_annual": is_num,
    "alpha_se_annual": is_num,
    "alpha_t": is_num,
    "alpha_p": is_num,
    "betas": is_dict,
    "premia": is_dict,
    "contributions": is_dict,
    "excess_annual": is_num,
    "r2": is_num,
    "r2_adj": is_num,
    "tracking_error": is_num,
    "information_ratio": is_num,
}
BETA = {"coef": is_num, "se": is_num, "t": is_num}
FEE = {
    "expense_ratio": is_num,
    "alpha_net": is_num,
    "alpha_gross": is_num,
    "alpha_ci95": is_interval,
    "breakeven_fee": is_num,
}
GROWTH = {
    "months": list_of(is_month),
    "fund": list_of(is_num),
    "replica": list_of(is_num),
    "tbills": list_of(is_num),
}
ROLLING = {
    "window": is_int,
    "months": list_of(is_month),
    "alpha_annual": list_of(is_num),
    "betas": is_dict,
    "r2": list_of(is_num),
}


def _shape(obj: Any, schema: Mapping[str, Check], where: str, errors: list[str]) -> bool:
    """Exactly the schema's keys, each passing its check. Appends problems; True if none."""
    if not isinstance(obj, dict):
        errors.append(f"{where}: expected an object")
        return False
    before = len(errors)
    for key in sorted(set(schema) - set(obj)):
        errors.append(f"{where}: missing {key}")
    for key in sorted(set(obj) - set(schema)):
        errors.append(f"{where}: unexpected field {key}")
    for key, check in schema.items():
        if key in obj and not check(obj[key]):
            errors.append(f"{where}.{key}: bad value {_short(obj[key])}")
    return len(errors) == before


def _short(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."


# -- months as integers --------------------------------------------------------------------
def _mi(m: str) -> int:
    return int(m[:4]) * 12 + int(m[5:7]) - 1


def _consecutive(months: list[str]) -> bool:
    return [_mi(m) for m in months] == list(range(_mi(months[0]), _mi(months[0]) + len(months)))


# -- invariants ----------------------------------------------------------------------------
def _check_model(fit: Any, model: str, months: int, where: str, errors: list[str]) -> bool:
    """Append the problems with one ``ModelFit``; False if it is too malformed to use."""
    if not _shape(fit, MODEL_FIT, where, errors):
        return False
    if fit["model"] != model:
        errors.append(f"{where}.model: {fit['model']!r}, expected {model!r}")
        return False
    factors = list(FACTOR_SETS[model])
    if fit["factors"] != factors:
        errors.append(f"{where}.factors: {fit['factors']}, expected {factors}")
        return False
    sound = set(fit["betas"]) == set(factors) and all(
        [_shape(fit["betas"][f], BETA, f"{where}.betas.{f}", errors) for f in factors]
    )
    if set(fit["betas"]) != set(factors):
        errors.append(f"{where}.betas: expected exactly {factors}")
    if set(fit["premia"]) != set(factors) or not all(map(is_num, fit["premia"].values())):
        errors.append(f"{where}.premia: expected a number for each of {factors}")
        sound = False
    parts = fit["contributions"]
    if set(parts) != {*factors, "alpha"} or not all(map(is_num, parts.values())):
        errors.append(f"{where}.contributions: expected a number for each of {factors} + alpha")
        sound = False
    else:
        gap = sum(parts.values()) - fit["excess_annual"]
        if abs(gap) > SUM_TOLERANCE:
            errors.append(f"{where}.contributions: sum differs from excess_annual by {gap:.2e}")
        if abs(parts["alpha"] - fit["alpha_annual"]) > 1e-5:
            errors.append(f"{where}.contributions.alpha: differs from alpha_annual")
    if fit["nobs"] != months:
        errors.append(f"{where}.nobs: {fit['nobs']}, but the window has {months} months")
    if fit["maxlags"] != newey_west_lags(fit["nobs"]):
        errors.append(f"{where}.maxlags: {fit['maxlags']} is not the Newey-West rule")
    if not (0 <= fit["r2"] <= 1 and 0 <= fit["alpha_p"] <= 1 and fit["alpha_se_annual"] >= 0):
        errors.append(f"{where}: r2, alpha_p or alpha_se_annual out of range")
    return sound


def _check_fund(
    rec: Any, entry: Mapping[str, Any], meta: Mapping[str, Any], where: str
) -> list[str]:
    errors: list[str] = []
    if not _shape(rec, FUND, where, errors):
        return errors
    if rec["schema_version"] != SCHEMA_VERSION:
        errors.append(f"{where}.schema_version: {rec['schema_version']}")
    for key in SUMMARY_KEYS:
        if rec[key] != entry[key]:
            errors.append(f"{where}.{key}: differs from index.json")

    win = rec["window"]
    if not _shape(win, WINDOW, f"{where}.window", errors):
        return errors
    months = win["months"]
    if _mi(win["end"]) - _mi(win["start"]) + 1 != months:
        errors.append(f"{where}.window: {win['start']} to {win['end']} is not {months} months")
    if not meta["min_months"] <= months <= meta["window_months"]:
        errors.append(f"{where}.window.months: {months} is outside the allowed range")
    if rec["short_history"] != (months < meta["window_months"]):
        errors.append(f"{where}.short_history: disagrees with window.months")
    if not rec["stale"] and win["end"] != meta["through"]:
        errors.append(f"{where}.window.end: {win['end']} is not {meta['through']} but not stale")
    if rec["stale"] and win["end"] > meta["through"]:
        errors.append(f"{where}.window.end: {win['end']} is after through ({meta['through']})")
    if rec["kind"] == "company" and rec["expense_ratio"] != 0:
        errors.append(f"{where}.expense_ratio: a company has no expense ratio")

    models = rec["models"]
    if set(models) != {HEADLINE_MODEL, ROBUSTNESS_MODEL}:
        errors.append(f"{where}.models: expected {HEADLINE_MODEL} and {ROBUSTNESS_MODEL}")
        return errors
    sound = [
        _check_model(models[key], meta[field], months, f"{where}.models.{key}", errors)
        for key, field in (
            (HEADLINE_MODEL, "headline_model"),
            (ROBUSTNESS_MODEL, "robustness_model"),
        )
    ]
    if not all(sound):
        return errors
    fit = models[HEADLINE_MODEL]
    for key in ("excess_annual", "alpha_annual", "alpha_t", "alpha_p", "r2"):
        if rec[key] != fit[key]:
            errors.append(f"{where}.{key}: differs from models.carhart.{key}")
    share = factor_share(fit["excess_annual"], fit["alpha_annual"])
    if (share is None) != (rec["factor_share"] is None) or (
        share is not None and abs(share - rec["factor_share"]) > ROUNDING
    ):
        errors.append(f"{where}.factor_share: expected {share}")
    if rec["verdict_short"] != verdict_short(rec["kind"], fit["alpha_t"]):
        errors.append(f"{where}.verdict_short: disagrees with kind and alpha_t")

    fee = rec["fee"]
    if _shape(fee, FEE, f"{where}.fee", errors):
        net, se, er = fit["alpha_annual"], fit["alpha_se_annual"], rec["expense_ratio"]
        lo, hi = fee["alpha_ci95"]
        if (
            fee["expense_ratio"] != er
            or fee["alpha_net"] != net
            or abs(fee["alpha_gross"] - (net + er)) > ROUNDING
            or fee["breakeven_fee"] != fee["alpha_gross"]
            or abs(lo - (net - Z95 * se)) > ROUNDING
            or abs(hi - (net + Z95 * se)) > ROUNDING
        ):
            errors.append(f"{where}.fee: inconsistent with the expense ratio and carhart alpha")

    growth = rec["growth"]
    if _shape(growth, GROWTH, f"{where}.growth", errors):
        gm = growth["months"]
        if len(gm) != months + 1 or not _consecutive(gm):
            errors.append(f"{where}.growth.months: expected {months + 1} consecutive months")
        elif _mi(gm[0]) != _mi(win["start"]) - 1 or gm[-1] != win["end"]:
            errors.append(f"{where}.growth.months: should run from the month before the window")
        for name in ("fund", "replica", "tbills"):
            series = growth[name]
            if len(series) != len(gm) or not series or series[0] != 1.0:
                errors.append(f"{where}.growth.{name}: expected {len(gm)} values starting at 1.0")
            elif min(series) <= 0:
                errors.append(f"{where}.growth.{name}: values must be positive")

    roll = rec["rolling"]
    if _shape(roll, ROLLING, f"{where}.rolling", errors):
        rm = roll["months"]
        factors = list(FACTOR_SETS[HEADLINE_MODEL])
        if roll["window"] != meta["rolling_window"]:
            errors.append(f"{where}.rolling.window: {roll['window']}")
        if not rm or not _consecutive(rm) or rm[-1] != win["end"]:
            errors.append(
                f"{where}.rolling.months: expected consecutive months ending {win['end']}"
            )
        if set(roll["betas"]) != set(factors) or not all(
            list_of(is_num)(v) for v in roll["betas"].values()
        ):
            errors.append(f"{where}.rolling.betas: expected a series for each of {factors}")
        else:
            series = [roll["alpha_annual"], roll["r2"], *roll["betas"].values()]
            if any(len(s) != len(rm) for s in series):
                errors.append(f"{where}.rolling: every series needs {len(rm)} values")
    return errors


# -- the directory -------------------------------------------------------------------------
def _load(root: Path, name: str, errors: list[str]) -> Any:
    try:
        return json.loads((root / name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{name}: missing")
    except (OSError, ValueError) as exc:
        errors.append(f"{name}: unreadable ({exc})")
    return None


def validate(path: str | Path) -> list[str]:
    """Every problem with the data directory at ``path``; an empty list means it is valid."""
    root = Path(path)
    errors: list[str] = []
    meta = _load(root, "meta.json", errors)
    index = _load(root, "index.json", errors)
    if meta is None or index is None:
        return errors
    if not _shape(meta, META, "meta.json", errors):
        return errors
    if meta["schema_version"] != SCHEMA_VERSION:
        errors.append(f"meta.json.schema_version: {meta['schema_version']}")
    if meta["headline_model"] != HEADLINE_MODEL:
        errors.append(f"meta.json.headline_model: {meta['headline_model']!r}")
    if meta["through"] > meta["factors_through"]:
        errors.append("meta.json.through: later than factors_through")

    if not _shape(index, INDEX, "index.json", errors):
        return errors
    if index["through"] != meta["through"]:
        errors.append("index.json.through: differs from meta.json")
    entries = index["funds"]
    if meta["funds"] != len(entries):
        errors.append(f"meta.json.funds: {meta['funds']}, but index.json lists {len(entries)}")
    good = [
        e for i, e in enumerate(entries) if _shape(e, SUMMARY, f"index.json.funds[{i}]", errors)
    ]
    if len(good) != len(entries):
        return errors
    tickers = [e["ticker"] for e in entries]
    if len(set(tickers)) != len(tickers):
        errors.append("index.json: duplicate tickers")
    order = sorted(entries, key=lambda e: (KINDS.index(e["kind"]), e["ticker"]))
    if [e["ticker"] for e in order] != tickers:
        errors.append("index.json: funds are not sorted by kind, then ticker")
    stale = sorted(e["ticker"] for e in entries if e["stale"])
    if sorted(meta["stale"]) != stale:
        errors.append(f"meta.json.stale: {meta['stale']}, but the stale funds are {stale}")
    if set(meta["excluded"]) & set(tickers):
        errors.append("meta.json.excluded: lists funds that index.json includes")

    for entry in entries:
        name = f"funds/{entry['ticker']}.json"
        rec = _load(root, name, errors)
        if rec is not None:
            errors.extend(_check_fund(rec, entry, meta, name))
    extra = {p.stem for p in (root / "funds").glob("*.json")} - set(tickers)
    for ticker in sorted(extra):
        errors.append(f"funds/{ticker}.json: not listed in index.json")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m live.validate",
        description="Check the unbundle live data directory against its schema and invariants.",
    )
    parser.add_argument("path", help="the data directory, e.g. web/data")
    args = parser.parse_args(argv)
    errors = validate(args.path)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print(f"live.validate: {len(errors)} problem(s) in {args.path}", file=sys.stderr)
        return 1
    print(f"live.validate: {args.path} is valid")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
