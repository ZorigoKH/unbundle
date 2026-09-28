"""unbundle live: the data pipeline behind the static website.

For a fixed list of well-known equity funds (``live/funds.csv``), ``python -m live.build``
fetches monthly total returns, applies the sourced corrections in ``live/overrides.csv``,
fits the Carhart four-factor model over the trailing ten years (with Fama-French five
factors plus momentum as a robustness check), and writes one JSON file per fund, an index
and a metadata file for the site in ``web/``.
``python -m live.validate`` checks those files against the schema and its invariants.

* :mod:`live.summarize` - pure functions from fitted models to JSON records and verdicts.
* :mod:`live.build` - fetch, fit, summarize, validate, then write atomically.
* :mod:`live.validate` - schema and invariant checks; the build runs them before writing.
"""

from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
HEADLINE_MODEL = "carhart"
ROBUSTNESS_MODEL = "ff5mom"
WINDOW_MONTHS = 120
MIN_MONTHS = 36
ROLLING_WINDOW = 36
HISTORY_START = "1990-01"

KINDS = ("active-fund", "active-etf", "company", "factor-fund", "index-fund", "sector-fund")
PASSIVE_KINDS = frozenset({"factor-fund", "index-fund", "sector-fund"})
VERDICTS = ("skill", "trails its factors", "no detectable alpha", "as designed")

FUNDS_CSV = Path(__file__).with_name("funds.csv")
FUND_COLUMNS = (
    "ticker",
    "name",
    "kind",
    "category",
    "expense_ratio",
    "er_as_of",
    "er_source",
    "note",
)
TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]*")  # also a safe file name: funds/<TICKER>.json

OVERRIDES_CSV = Path(__file__).with_name("overrides.csv")
OVERRIDE_COLUMNS = ("ticker", "month", "return", "reason", "source")
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


@dataclass(frozen=True)
class Fund:
    """One row of ``funds.csv``. ``expense_ratio`` is a decimal (0.0039 is 0.39% a year)."""

    ticker: str
    name: str
    kind: str
    category: str
    expense_ratio: float
    er_as_of: str = ""
    er_source: str = ""
    note: str = ""


def read_funds(path: str | os.PathLike = FUNDS_CSV) -> list[Fund]:
    """The fund list, in file order, with every row checked."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != FUND_COLUMNS:
            raise ValueError(f"{path}: the columns must be {','.join(FUND_COLUMNS)}")
        funds = []
        for line, row in enumerate(reader, start=2):
            ticker, kind = row["ticker"].strip(), row["kind"].strip()
            if not TICKER.fullmatch(ticker):
                raise ValueError(f"{path}:{line}: {ticker!r} is not a ticker")
            if kind not in KINDS:
                raise ValueError(f"{path}:{line}: unknown kind {kind!r}; use one of {KINDS}")
            expense_ratio = float(row["expense_ratio"])
            if not 0 <= expense_ratio < 0.05:
                raise ValueError(f"{path}:{line}: expense ratio {expense_ratio} is not a decimal")
            funds.append(
                Fund(
                    ticker=ticker,
                    name=row["name"].strip(),
                    kind=kind,
                    category=row["category"].strip(),
                    expense_ratio=expense_ratio,
                    er_as_of=row["er_as_of"].strip(),
                    er_source=row["er_source"].strip(),
                    note=row["note"].strip(),
                )
            )
    tickers = [f.ticker for f in funds]
    dupes = sorted({t for t in tickers if tickers.count(t) > 1})
    if dupes:
        raise ValueError(f"{path}: duplicate tickers {', '.join(dupes)}")
    return funds


@dataclass(frozen=True)
class Override:
    """One row of ``overrides.csv``: a monthly return that replaces the one Yahoo reports.

    For months where the issuer's own figures show Yahoo's adjusted close is wrong, such as
    a distribution the fund never paid. ``value`` is a decimal (-0.093257 is -9.33%);
    ``reason`` says what is wrong and ``source`` is the URL of the evidence.
    """

    ticker: str
    month: str
    value: float
    reason: str
    source: str


def read_overrides(path: str | os.PathLike = OVERRIDES_CSV) -> list[Override]:
    """The return corrections, in file order, with every row checked."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if tuple(reader.fieldnames or ()) != OVERRIDE_COLUMNS:
            raise ValueError(f"{path}: the columns must be {','.join(OVERRIDE_COLUMNS)}")
        overrides = []
        for line, row in enumerate(reader, start=2):
            ticker, month = row["ticker"].strip(), row["month"].strip()
            reason, source = row["reason"].strip(), row["source"].strip()
            if not TICKER.fullmatch(ticker):
                raise ValueError(f"{path}:{line}: {ticker!r} is not a ticker")
            if not MONTH.fullmatch(month):
                raise ValueError(f"{path}:{line}: {month!r} is not a YYYY-MM month")
            value = float(row["return"])
            if not (math.isfinite(value) and -1 < value < 1):
                raise ValueError(f"{path}:{line}: return {value} is not a monthly decimal return")
            if not reason or not re.match(r"https?://", source):
                raise ValueError(f"{path}:{line}: every override needs a reason and a source URL")
            overrides.append(Override(ticker, month, value, reason, source))
    keys = [(o.ticker, o.month) for o in overrides]
    dupes = sorted({f"{t} {m}" for t, m in keys if keys.count((t, m)) > 1})
    if dupes:
        raise ValueError(f"{path}: more than one override for {', '.join(dupes)}")
    return overrides
