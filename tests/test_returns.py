import sys
import types

import numpy as np
import pandas as pd
import pytest

from unbundle import excess_returns, fetch_yahoo, prices_to_returns, read_returns_csv


def test_month_end_prices_to_monthly_returns():
    days = pd.to_datetime(["2024-01-02", "2024-01-31", "2024-02-15", "2024-02-29", "2024-03-28"])
    prices = pd.Series([99.0, 100.0, 104.0, 105.0, 94.5], index=days, name="FUND")
    out = prices_to_returns(prices, drop_incomplete=False)
    assert [str(p) for p in out.index] == ["2024-02", "2024-03"]
    np.testing.assert_allclose(out["FUND"].to_numpy(), [0.05, -0.10])


def test_timezones_are_dropped_and_the_current_month_is_incomplete():
    today = pd.Timestamp.today().normalize()
    days = pd.date_range(today - pd.DateOffset(months=3), today, freq="D", tz="America/New_York")
    prices = pd.DataFrame({"A": np.linspace(100, 130, len(days))}, index=days)
    out = prices_to_returns(prices)
    assert out.index[-1] < pd.Period(today, "M")
    assert out.index[-1] == pd.Period(today, "M") - 1


def test_read_csv_maps_any_day_to_its_month(tmp_path):
    path = tmp_path / "fund.csv"
    path.write_text("date,Fund A,Fund B\n2024-01-31,1.5,-2\n2024-02-29,0.5,1\n2024-03-01,-1,0.25\n")
    frame = read_returns_csv(path, percent=True)
    assert [str(p) for p in frame.index] == ["2024-01", "2024-02", "2024-03"]
    np.testing.assert_allclose(frame["Fund A"].to_numpy(), [0.015, 0.005, -0.01])
    dup = tmp_path / "dup.csv"
    dup.write_text("month,x\n2024-01-05,0.01\n2024-01-20,0.02\n")
    with pytest.raises(ValueError, match="more than one row"):
        read_returns_csv(dup)
    with pytest.raises(ValueError, match="no column"):
        read_returns_csv(path, date_col="when")


def test_excess_returns_align_on_common_months():
    idx = pd.period_range("2024-01", periods=4, freq="M")
    r = pd.Series([0.02, 0.01, -0.01, 0.03], index=idx, name="A")
    rf = pd.Series([0.004, 0.004, 0.005], index=idx[1:])
    out = excess_returns(r, rf)
    assert list(out.index) == list(idx[1:])
    np.testing.assert_allclose(out["A"].to_numpy(), [0.006, -0.014, 0.025])


def _fake_yfinance(frame):
    module = types.ModuleType("yfinance")
    module.calls = []

    def download(tickers, **kwargs):
        module.calls.append((tickers, kwargs))
        return frame

    module.download = download
    return module


def test_fetch_yahoo_uses_adjusted_closes(monkeypatch):
    days = pd.to_datetime(["2023-12-29", "2024-01-31", "2024-02-29"])
    cols = pd.MultiIndex.from_product(
        [["Close", "Open"], ["SPY", "ARKK"]], names=["Price", "Ticker"]
    )
    data = pd.DataFrame(
        [[100, 50, 0, 0], [101, 45, 0, 0], [103.02, 49.5, 0, 0]],
        index=days,
        columns=cols,
        dtype=float,
    )
    fake = _fake_yfinance(data)
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    out = fetch_yahoo(["SPY", "ARKK"], start="2024-01", end="2024-02")
    kwargs = fake.calls[0][1]
    assert kwargs["auto_adjust"] is True  # dividends in, or alpha is biased down
    # months in, dates out: January's return needs December's close; Yahoo's end is exclusive
    assert (kwargs["start"], kwargs["end"]) == ("2023-12-01", "2024-03-01")
    assert [str(m) for m in out.index] == ["2024-01", "2024-02"]
    assert list(out.columns) == ["SPY", "ARKK"]
    np.testing.assert_allclose(out.loc["2024-01"].to_numpy(), [0.01, -0.10])
    np.testing.assert_allclose(out.loc["2024-02"].to_numpy(), [0.02, 0.10])


def test_fetch_yahoo_reports_missing_tickers(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", _fake_yfinance(pd.DataFrame()))
    with pytest.raises(RuntimeError, match="no prices returned"):
        fetch_yahoo("NOPE")


def test_yahoo_errors_become_one_line_messages(monkeypatch):
    class YFRateLimitError(Exception):  # stands in for yfinance's own exception types
        pass

    def download(tickers, **kwargs):
        raise YFRateLimitError("Too Many Requests. Rate limited. Try after a while.")

    module = types.ModuleType("yfinance")
    module.download = download
    monkeypatch.setitem(sys.modules, "yfinance", module)
    with pytest.raises(RuntimeError, match="Yahoo Finance download failed: Too Many Requests"):
        fetch_yahoo("SPY")
