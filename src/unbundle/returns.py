"""Asset returns: prices to monthly returns, Yahoo Finance, CSV files, excess returns.

Everything is aligned on a monthly ``PeriodIndex`` so fund returns and Ken French factors
line up by calendar month regardless of which trading day each month ended on.

Use *adjusted* prices - split- and dividend-adjusted - or the returns are wrong: an S&P 500
fund priced without dividends loses about 1.5-2% a year, and that missing income would show
up as negative alpha.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import date

import pandas as pd


def prices_to_returns(
    prices: pd.Series | pd.DataFrame, *, drop_incomplete: bool = True
) -> pd.DataFrame:
    """Monthly simple returns from month-end prices.

    ``prices`` may be daily or any other frequency, indexed by dates. The last price in each
    calendar month is taken as that month's close. With ``drop_incomplete`` the current
    calendar month, whose close is not in yet, is dropped.
    """
    frame = prices.to_frame() if isinstance(prices, pd.Series) else prices.copy()
    frame.index = pd.DatetimeIndex(frame.index)
    if frame.index.tz is not None:
        frame.index = frame.index.tz_localize(None)
    frame = frame.sort_index()
    month_end = frame.groupby(frame.index.to_period("M")).last()
    if drop_incomplete and len(month_end) and month_end.index[-1] == pd.Period(date.today(), "M"):
        month_end = month_end.iloc[:-1]
    returns = month_end.pct_change(fill_method=None).iloc[1:]
    returns.index.name = "month"
    return returns


def fetch_yahoo(
    tickers: str | Iterable[str], *, start: str | None = None, end: str | None = None
) -> pd.DataFrame:
    """Monthly total returns for ``tickers`` from split- and dividend-adjusted Yahoo prices.

    ``start`` and ``end`` are months (``"2015-01"``; a full date works too), both included.
    Needs the optional dependency: ``pip install "unbundle[live]"``.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError('live prices need yfinance: pip install "unbundle[live]"') from exc
    names = [tickers] if isinstance(tickers, str) else list(tickers)
    first = None if start is None else pd.Period(start, freq="M")
    last = None if end is None else pd.Period(end, freq="M")
    try:
        data = yf.download(
            names,
            # the first month's return needs the previous month's close; Yahoo's end is exclusive
            start=None if first is None else (first - 1).start_time.strftime("%Y-%m-%d"),
            end=None if last is None else (last + 1).start_time.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            multi_level_index=True,
        )
    except Exception as exc:  # yfinance has its own error types (rate limits, bad tickers)
        raise RuntimeError(f"Yahoo Finance download failed: {exc}") from exc
    if data is None or data.empty:
        raise RuntimeError(f"no prices returned for {', '.join(names)}")
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(names[0])
    close = close.loc[:, [n for n in names if n in close.columns]]
    empty = [n for n in close.columns if close[n].notna().sum() < 2]
    if empty:
        raise RuntimeError(f"no usable prices for {', '.join(empty)}")
    return prices_to_returns(close).loc[first:last]


def read_returns_csv(
    path: str | os.PathLike, *, date_col: str | None = None, percent: bool = False
) -> pd.DataFrame:
    """Monthly returns from a CSV: one date column and one column per asset.

    Dates may fall on any day of the month (``2024-03-31``, ``2024-03``, ``3/1/2024``); each
    is mapped to its calendar month. Returns are decimals unless ``percent=True``.
    """
    frame = pd.read_csv(path)
    column = date_col or frame.columns[0]
    if column not in frame.columns:
        raise ValueError(f"no column {column!r} in {path}")
    months = pd.PeriodIndex(pd.to_datetime(frame.pop(column)), freq="M", name="month")
    frame.index = months
    if months.has_duplicates:
        raise ValueError("more than one row for the same month; the file must be monthly")
    frame = frame.apply(pd.to_numeric, errors="raise").sort_index()
    return frame / 100.0 if percent else frame


def excess_returns(returns: pd.Series | pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    """Subtract the risk-free rate month by month, keeping only months present in both."""
    frame = returns.to_frame() if isinstance(returns, pd.Series) else returns
    frame, rf = frame.align(rf, join="inner", axis=0)
    return frame.sub(rf, axis=0)
