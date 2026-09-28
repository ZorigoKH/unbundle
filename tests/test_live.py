"""unbundle live, offline: Ken French sample portfolios stand in for funds, fetches are stubbed.

Industry and size/book-to-market portfolios play the funds (total returns); the factors are
the bundled sample, which has no RMW/CMA, so most builds run in offline sample mode with a
Carhart robustness fit. Nothing here touches the network.
"""

import json
import shutil
from datetime import date
from functools import partial

import numpy as np
import pandas as pd
import pytest

from live import (
    FUND_COLUMNS,
    KINDS,
    OVERRIDE_COLUMNS,
    VERDICTS,
    Fund,
    Override,
    read_funds,
    read_overrides,
)
from live import build as live_build
from live import summarize as s
from live import validate as live_validate
from live.build import BuildError, build, control_checks, fetch_returns, usable_history
from live.validate import validate
from unbundle import FACTOR_SETS, FactorModel, load_factors, read_returns_csv, rolling_exposures

TODAY = date(2026, 9, 27)
SAMPLE = partial(load_factors, source="sample")
KIND = {
    "HLTH": "active-fund",
    "ENRG": "active-fund",
    "TECH": "active-etf",
    "FOOD": "company",
    "SMALL": "factor-fund",
    "MTUM": "factor-fund",
    "SPY": "index-fund",
    "IWM": "index-fund",
    "IWD": "index-fund",
    "IWF": "index-fund",
    "UTIL": "sector-fund",
}
FUNDS = [
    Fund(t, f"{t} stand-in", k, "test", 0.0 if k == "company" else 0.005, "2026-01-01", "test")
    for t, k in KIND.items()
]
SPEC_ORDER = (
    "FCNTX FMAGX AGTHX AIVSX DODGX PRGFX VPMCX VWNFX SEQUX OAKMX FLPSX POAGX BGRFX JENSX "
    "ARKK JEPI BRK-B DFSVX AVUV MTUM QUAL USMV VBR SCHD SPY VTI QQQ IWM IWD IWF XLK XLE XLV"
).split()


@pytest.fixture(scope="module")
def standins(sample) -> pd.DataFrame:
    """Monthly total returns for the stand-in funds; SPY is the market plus a little noise."""
    noise = np.random.default_rng(0).normal(0, 0.003, len(sample))
    return pd.DataFrame(
        {
            "HLTH": sample["Hlth"],
            "ENRG": sample["Enrgy"],
            "TECH": sample["BusEq"],
            "FOOD": sample["NoDur"],
            "SMALL": sample["S1V5"],
            "MTUM": sample["S5M5"],
            "SPY": sample["MktRF"] + sample["RF"] + noise,
            "IWM": sample["S1V3"],
            "IWD": sample["S5V5"],
            "IWF": sample["S5V1"],
            "UTIL": sample["Utils"],
        }
    )


def _no_network(*args, **kwargs):
    raise AssertionError("tests must not fetch prices")


def run(out, prices=None, *, funds=FUNDS, today=TODAY, **kw):
    """``build`` in offline sample mode, with no sleeping, no logging and no network."""
    kw.setdefault("load", SAMPLE)
    kw.setdefault("robust_model", "carhart")
    kw.setdefault("fetch", _no_network)
    quiet = {"sleep": lambda _: None, "log": lambda _: None}
    return build(out, funds, prices=prices, today=today, **quiet, **kw)


def stub_fetch(frame, failing=()):
    """A fetch that serves ``frame`` and raises for any request that includes ``failing``."""

    def fetch(tickers, start=None, end=None):
        bad = [t for t in tickers if t in failing]
        if bad:
            raise RuntimeError(f"no usable prices for {', '.join(bad)}")
        return frame.loc[start:end, list(tickers)]

    return fetch


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def load(root, rel):
    return json.loads((root / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(tmp_path_factory, standins):
    out = tmp_path_factory.mktemp("live") / "data"
    run(out, standins)
    return out


# -- the fund list -------------------------------------------------------------------------
def test_fund_list_is_the_spec_list():
    funds = read_funds()
    assert [f.ticker for f in funds] == SPEC_ORDER
    assert all(f.kind in KINDS and f.category == f.category.lower() for f in funds)
    assert all(0 <= f.expense_ratio < 0.02 for f in funds)
    brk = next(f for f in funds if f.ticker == "BRK-B")
    assert brk.kind == "company" and brk.expense_ratio == 0 and "not a fund" in brk.note
    assert all("sales load" in f.note for f in funds if f.ticker in ("AGTHX", "AIVSX"))


def test_fund_list_rejects_bad_rows(tmp_path):
    path = tmp_path / "funds.csv"
    path.write_text(",".join(FUND_COLUMNS) + "\nSPY,SPDR,index,large blend,0.0009,,,\n")
    with pytest.raises(ValueError, match="unknown kind"):
        read_funds(path)
    path.write_text(",".join(FUND_COLUMNS) + "\n../x,SPDR,index-fund,large blend,0.0009,,,\n")
    with pytest.raises(ValueError, match="not a ticker"):
        read_funds(path)


# -- the output ----------------------------------------------------------------------------
def test_build_output_passes_validation(built):
    assert validate(built) == []
    assert live_validate.main([str(built)]) == 0
    meta, index = load(built, "meta.json"), load(built, "index.json")
    assert meta["through"] == index["through"] == "2017-03"
    assert meta["funds"] == 11 and meta["stale"] == meta["excluded"] == []
    assert meta["generated_at"] == "2026-09-27"
    kinds = [e["kind"] for e in index["funds"]]
    assert kinds == sorted(kinds, key=KINDS.index)
    assert [e["ticker"] for e in index["funds"]][:4] == ["ENRG", "HLTH", "TECH", "FOOD"]
    assert sorted(p.stem for p in (built / "funds").glob("*.json")) == sorted(KIND)


def test_contributions_add_up_and_growth_compounds_the_window(built, standins):
    for ticker in KIND:
        rec = load(built, f"funds/{ticker}.json")
        for fit in rec["models"].values():
            parts = fit["contributions"]
            assert abs(sum(parts.values()) - fit["excess_annual"]) <= 1e-9
            assert parts["alpha"] == pytest.approx(fit["alpha_annual"], abs=1e-5)
        win, growth = rec["window"], rec["growth"]
        assert win == {"start": "2007-04", "end": "2017-03", "months": 120}
        assert growth["months"][0] == "2007-03" and growth["months"][-1] == "2017-03"
        for series in ("fund", "replica", "tbills"):
            assert len(growth[series]) == win["months"] + 1 and growth[series][0] == 1.0
        r = standins[ticker].loc["2007-04":"2017-03"]
        assert growth["fund"][-1] == pytest.approx(np.prod(1 + r), rel=1e-5)


def test_summary_fields_mirror_the_carhart_fit_and_fee_block(built):
    rec = load(built, "funds/HLTH.json")
    fit = rec["models"]["carhart"]
    for key in ("excess_annual", "alpha_annual", "alpha_t", "alpha_p", "r2"):
        assert rec[key] == fit[key]
    fee = rec["fee"]
    assert fee["alpha_net"] == rec["alpha_annual"]
    assert fee["alpha_gross"] == pytest.approx(rec["alpha_annual"] + 0.005, abs=1e-6)
    assert fee["breakeven_fee"] == fee["alpha_gross"]
    se = fit["alpha_se_annual"]
    assert fee["alpha_ci95"] == pytest.approx(
        [fee["alpha_net"] - 1.96 * se, fee["alpha_net"] + 1.96 * se], abs=1e-6
    )
    assert load(built, "funds/FOOD.json")["fee"]["expense_ratio"] == 0


def test_rolling_alpha_is_decimal_per_year_from_1990(built, standins, sample):
    rec = load(built, "funds/HLTH.json")
    roll = rec["rolling"]
    carhart = list(FACTOR_SETS["carhart"])
    excess = (standins["HLTH"] - sample["RF"]).loc["1990-01":"2017-03"]
    ref = rolling_exposures(excess, sample.loc[excess.index, carhart], window=36)
    assert (
        roll["window"] == 36 and roll["months"][0] == "1992-12" and len(roll["months"]) == len(ref)
    )
    assert roll["alpha_annual"][-1] == pytest.approx(ref["alpha %/yr"].iloc[-1] / 100, abs=1e-6)
    assert roll["betas"]["Mom"][0] == pytest.approx(ref["Mom"].iloc[0], abs=1e-6)


# -- determinism ---------------------------------------------------------------------------
def test_rerun_is_byte_identical(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins, today=date(2026, 9, 1))
    first = snapshot(out)
    run(out, standins, today=date(2026, 9, 27))
    assert snapshot(out) == first
    assert load(out, "meta.json")["generated_at"] == "2026-09-01"


def test_generated_at_moves_when_content_changes(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins, today=date(2026, 9, 1))
    changed = standins.copy()
    changed.loc[pd.Period("2017-03", "M"), "HLTH"] += 0.001
    run(out, changed, today=date(2026, 9, 27))
    assert load(out, "meta.json")["generated_at"] == "2026-09-27"


def test_download_noise_leaves_the_files_alone(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins, today=date(2026, 9, 1))
    first = snapshot(out)
    jitter = np.random.default_rng(1).uniform(-2e-6, 2e-6, standins.shape)
    run(out, standins + jitter, today=date(2026, 9, 27))  # Yahoo's size of noise
    assert snapshot(out) == first
    revised = standins.copy()
    revised.loc[pd.Period("2016-06", "M"), "HLTH"] += 0.002
    run(out, revised, today=date(2026, 9, 27))
    after = snapshot(out)
    assert sorted(k for k in after if after[k] != first[k]) == [
        "funds/HLTH.json",
        "index.json",
        "meta.json",
    ]


def test_unchanged_is_exact_for_text_shapes_and_expense_ratios():
    rec = {"expense_ratio": 0.000945, "alpha_t": 1.2345, "r2": 0.9, "growth": [1.0, 2.0]}
    assert live_build.unchanged(
        {**rec, "alpha_t": 1.2355, "r2": 0.90005, "growth": [1.0, 2.0001]}, rec
    )
    assert not live_build.unchanged({**rec, "expense_ratio": 0.00095}, rec)
    assert not live_build.unchanged({**rec, "r2": 0.9002}, rec)
    assert not live_build.unchanged({**rec, "growth": [1.0, 2.0, 3.0]}, rec)
    assert not live_build.unchanged({**rec, "note": "new"}, rec)
    assert not live_build.unchanged({**rec, "r2": True}, {**rec, "r2": 1.0})
    assert live_build.unchanged({**rec, "verdict": "t = 1.24"}, {**rec, "verdict": "t = 1.23"})


def test_new_verdict_wording_is_published_without_new_data(tmp_path, standins, monkeypatch):
    out = tmp_path / "data"
    run(out, standins)
    wording = s.verdict
    monkeypatch.setattr(s, "verdict", lambda *a: (wording(*a)[0], "Reworded."))
    run(out, standins)
    assert load(out, "funds/HLTH.json")["verdict"] == "Reworded."


# -- failures ------------------------------------------------------------------------------
def test_a_fetch_that_raises_aborts_and_writes_nothing(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins)
    before = snapshot(out)
    with pytest.raises(BuildError, match="11 of 11 tickers failed"):
        run(out, fetch=stub_fetch(standins, failing=set(KIND)))
    assert snapshot(out) == before
    assert [p.name for p in tmp_path.iterdir()] == ["data"]  # no staging directory left


def test_one_failing_ticker_keeps_its_old_file_marked_stale(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins)
    before = snapshot(out)
    meta = run(out, fetch=stub_fetch(standins, failing={"HLTH"}))
    after = snapshot(out)
    assert meta["stale"] == ["HLTH"] and validate(out) == []
    old, new = json.loads(before["funds/HLTH.json"]), json.loads(after["funds/HLTH.json"])
    assert new == {**old, "stale": True}
    entry = next(e for e in load(out, "index.json")["funds"] if e["ticker"] == "HLTH")
    assert entry["stale"] is True
    unchanged = [r for r in before if r.startswith("funds/") and r != "funds/HLTH.json"]
    assert all(before[r] == after[r] for r in unchanged)


def test_fetch_retries_with_backoff_then_one_ticker_at_a_time(standins):
    tickers = [*KIND, "BAD"]  # 12 tickers: a batch of 8, then a batch of 4 with BAD in it
    calls, sleeps = [], []

    def fetch(names, start=None, end=None):
        calls.append(list(names))
        return stub_fetch(standins, failing={"BAD"})(names, start=start)

    got = fetch_returns(tickers, fetch, sleep=sleeps.append, log=lambda _: None)
    assert list(got.columns) == list(KIND) and str(got.index[0]) == "1990-01"
    assert calls[0] == tickers[:8] and calls[1:4] == [tickers[8:]] * 3
    assert calls[4:] == [[t] for t in tickers[8:]]
    assert sleeps[:4] == [2.0, 2.0, 4.0, 8.0]  # between batches, then the backoff


def test_too_many_failed_tickers_abort(tmp_path, standins):
    failing = stub_fetch(standins, failing={"HLTH", "ENRG", "TECH"})
    with pytest.raises(BuildError, match="3 of 11 tickers failed"):
        run(tmp_path / "data", fetch=failing, save_prices=tmp_path / "saved.csv")
    assert list(tmp_path.iterdir()) == []  # not even the saved prices


def test_factor_data_failure_aborts(tmp_path, standins):
    def broken(model):
        raise RuntimeError("F-F_Research_Data_Factors_CSV.zip did not arrive as a zipped CSV")

    with pytest.raises(BuildError, match="factor data failed"):
        run(tmp_path / "data", standins, load=broken)
    assert not (tmp_path / "data").exists()


def test_control_group_catches_a_spy_that_is_not_the_market(tmp_path, standins, sample):
    bad = standins.assign(SPY=standins["SPY"] - 0.5 * sample["MktRF"])  # half the market beta
    with pytest.raises(BuildError, match="control-group check failed: SPY market β 0.50"):
        run(tmp_path / "data", bad)
    assert not (tmp_path / "data").exists()


def test_control_checks_skip_absent_tickers_only():
    def fit(**betas):
        return {"betas": {f: {"coef": b} for f, b in betas.items()}, "r2": 0.99}

    assert control_checks({}) == []
    checks = control_checks({"VTI": fit(MktRF=1.2), "IWF": fit(HML=-0.2), "MTUM": fit(Mom=0.05)})
    assert [passed for _, passed in checks] == [False, True, False]


def test_revised_history_aborts_when_more_than_five_funds_move(tmp_path, standins):
    revised = standins.copy()
    for ticker in ("HLTH", "ENRG", "TECH", "FOOD", "SMALL", "UTIL"):
        revised.loc[pd.Period("2012-06", "M"), ticker] += 0.01  # one point, in the window
    five, six = tmp_path / "five", tmp_path / "six"
    run(five, standins)
    run(six, standins)
    before = snapshot(six)
    with pytest.raises(BuildError, match="6 funds had past returns revised"):
        run(six, revised)
    assert snapshot(six) == before
    run(five, revised.assign(UTIL=standins["UTIL"]))  # five revised funds are allowed
    assert snapshot(five) != before and validate(five) == []


def test_sanity_checks_exclude_new_funds_and_keep_old_files(tmp_path, standins):
    out = tmp_path / "data"
    broken = standins.copy()
    broken.loc[pd.Period("2015-02", "M"), "HLTH"] = np.nan  # a gap inside the window
    broken.loc[pd.Period("2001-02", "M"), "ENRG"] = 0.75  # not a real monthly return
    meta = run(out, broken)
    assert meta["excluded"] == ["ENRG", "HLTH"] and meta["funds"] == 9
    assert not (out / "funds" / "HLTH.json").exists()
    run(out, standins)
    meta = run(out, broken)
    assert meta["stale"] == ["ENRG", "HLTH"] and meta["excluded"] == []
    assert load(out, "funds/HLTH.json")["stale"] is True and validate(out) == []


def test_a_fund_whose_returns_now_end_earlier_keeps_its_published_record(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins)
    before = snapshot(out)
    short = standins.copy()
    short.loc["2017-02":, "HLTH"] = np.nan  # a short response: two months missing at the end
    meta = run(out, short)
    old, new = json.loads(before["funds/HLTH.json"]), load(out, "funds/HLTH.json")
    assert new == {**old, "stale": True} and new["window"]["end"] == "2017-03"
    assert meta["stale"] == ["HLTH"] and meta["through"] == "2017-03" and validate(out) == []
    meta = run(out, short, allow_older=True)  # asked for: the older window is published
    assert load(out, "funds/HLTH.json")["window"]["end"] == "2017-01"
    assert meta["stale"] == ["HLTH"] and validate(out) == []


def test_data_older_than_published_aborts_unless_allowed(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins)
    before = snapshot(out)

    def cut(model):  # e.g. a stale cached copy of the factor files
        return SAMPLE(model).loc[:"2017-01"]

    with pytest.raises(BuildError, match="ends 2017-01 .* before the published 2017-03"):
        run(out, standins, load=cut)
    assert snapshot(out) == before
    meta = run(out, standins, load=cut, allow_older=True)
    assert meta["through"] == "2017-01" and meta["stale"] == [] and validate(out) == []


def test_one_failing_ticker_after_an_allowed_older_build(tmp_path, standins):
    out = tmp_path / "data"
    run(out, standins)

    def cut(model):
        return SAMPLE(model).loc[:"2017-01"]

    fetch = stub_fetch(standins, failing={"HLTH"})
    meta = run(out, load=cut, allow_older=True, fetch=fetch)
    assert meta["excluded"] == ["HLTH"] and validate(out) == []  # its record ends too late


def test_overrides_replace_a_month_before_fitting(tmp_path, standins):
    fixed = Override("HLTH", "2016-06", -0.0123, "a distribution never paid", "https://x.test")
    absent = Override("ZZZ", "2016-06", 0.0, "a ticker that is not in the build", "https://x")
    lines = []
    out = tmp_path / "data"
    run(tmp_path / "plain", standins)
    build(
        out,
        FUNDS,
        prices=standins,
        overrides=[fixed, absent],
        load=SAMPLE,
        robust_model="carhart",
        today=TODAY,
        sleep=lambda _: None,
        log=lines.append,
    )
    rec = load(out, "funds/HLTH.json")
    assert s.growth_returns(rec["growth"])["2016-06"] == pytest.approx(-0.0123, abs=1e-5)
    assert rec != load(tmp_path / "plain", "funds/HLTH.json")
    assert load(out, "funds/ENRG.json") == load(tmp_path / "plain", "funds/ENRG.json")
    was = s.pct(standins.loc[pd.Period("2016-06", "M"), "HLTH"], "+.2f")
    assert f"  HLTH   2016-06 return set to −1.23% (was {was}%)" in lines


def test_override_file_is_checked(tmp_path):
    arkk = read_overrides()
    assert [(o.ticker, o.month) for o in arkk] == [("ARKK", "2023-09")]
    assert arkk[0].value == pytest.approx(-0.093257) and arkk[0].source.startswith("https://")
    path = tmp_path / "overrides.csv"
    head = ",".join(OVERRIDE_COLUMNS) + "\n"
    for row, problem in (
        ("ARKK,2023-9,-0.09,why,https://x\n", "not a YYYY-MM month"),
        ("ARKK,2023-09,-1.5,why,https://x\n", "not a monthly decimal return"),
        ("ARKK,2023-09,-0.09,,https://x\n", "needs a reason and a source URL"),
        ("ARKK,2023-09,-0.09,why,sec filing\n", "needs a reason and a source URL"),
        ("ARKK,2023-09,-0.09,why,https://x\n" * 2, "more than one override for ARKK 2023-09"),
    ):
        path.write_text(head + row)
        with pytest.raises(ValueError, match=problem):
            read_overrides(path)


def test_short_histories_and_early_ends(tmp_path, standins):
    frame = standins.assign(
        NEW=standins["HLTH"].where(standins.index >= pd.Period("2012-04", "M")),
        OLD=standins["UTIL"].where(standins.index <= pd.Period("2016-12", "M")),
        TINY=standins["TECH"].where(standins.index >= pd.Period("2015-04", "M")),
    )
    extra = [Fund(t, t, "active-fund", "test", 0.01) for t in ("NEW", "OLD", "TINY")]
    out = tmp_path / "data"
    meta = run(out, frame, funds=[*FUNDS, *extra])
    new, old = load(out, "funds/NEW.json"), load(out, "funds/OLD.json")
    assert new["short_history"] and new["window"] == {
        "start": "2012-04",
        "end": "2017-03",
        "months": 60,
    }
    assert len(new["growth"]["fund"]) == 61
    assert old["stale"] and old["window"]["end"] == "2016-12" and not old["short_history"]
    assert meta["stale"] == ["OLD"] and meta["excluded"] == ["TINY"]
    assert validate(out) == []


def test_usable_history_reasons(standins):
    r = standins["HLTH"].loc["1990-01":]
    through = pd.Period("2017-03", "M")
    window, history = usable_history(r, through)
    assert len(window) == 120 and str(history.index[0]) == "1990-01"
    gap_before = r.copy()
    gap_before.loc[pd.Period("2000-01", "M")] = np.nan
    window, history = usable_history(gap_before, through)
    assert str(history.index[0]) == "2000-02" and len(window) == 120
    assert "only 24 months" in usable_history(r.loc["2015-04":], through)
    assert "no returns through 1989-12" in usable_history(r, pd.Period("1989-12", "M"))


# -- the robustness model ------------------------------------------------------------------
def test_robustness_model_is_its_own_fit(tmp_path, standins):
    def five_factors(model):
        """The sample plus made-up RMW and CMA columns, to exercise the ff5mom path offline."""
        base = SAMPLE("carhart").loc["1963-07":]
        fake = standins.loc[base.index]
        five = base.assign(
            RMW=(fake["FOOD"] - fake["TECH"]) / 4, CMA=(fake["UTIL"] - fake["TECH"]) / 4
        )
        return five[[*FACTOR_SETS[model], "RF"]]

    out = tmp_path / "data"
    meta = run(out, standins, load=five_factors, robust_model="ff5mom")
    assert meta["robustness_model"] == "ff5mom" and validate(out) == []
    clauses = []
    for ticker in KIND:
        rec = load(out, f"funds/{ticker}.json")
        fit, robust = rec["models"]["carhart"], rec["models"]["ff5mom"]
        assert robust["model"] == "ff5mom" and len(robust["factors"]) == 6
        added = "With profitability and investment factors added" in rec["verdict"]
        assert added == s._robustness_differs(fit, robust)
        clauses.append(added)
    assert any(clauses) and not all(clauses)


# -- verdicts ------------------------------------------------------------------------------
def fake_fit(alpha=0.0, t=0.0, *, excess=0.08, nobs=120):
    factors = list(FACTOR_SETS["carhart"])
    parts = {"MktRF": 0.07, "SMB": 0.004, "HML": -0.01, "Mom": 0.001, "alpha": alpha}
    return {
        "model": "carhart",
        "factors": factors,
        "nobs": nobs,
        "alpha_annual": alpha,
        "alpha_t": t,
        "excess_annual": excess,
        "contributions": parts,
        "betas": {f: {"coef": 1.02 if f == "MktRF" else 0.3} for f in factors},
        "r2": 0.987,
    }


def test_verdict_skill():
    assert s.verdict("FCNTX", "active-fund", fake_fit(0.031, 2.5)) == (
        "skill",
        "After fees, FCNTX earned +3.1% a year more than its factor exposure explains "
        "(t = 2.50) over 10.0 years: evidence of skill.",
    )


def test_verdict_trails():
    assert s.verdict("ARKK", "active-etf", fake_fit(-0.0243, -2.31, nobs=90)) == (
        "trails its factors",
        "After fees, ARKK trailed its factor exposure by 2.4% a year (t = −2.31) over 7.5 years: "
        "its fee cost more than the manager added.",
    )


def test_verdict_no_alpha_with_factor_share():
    short, text = s.verdict("BRK-B", "company", fake_fit(-0.005, -0.4, excess=0.10))
    assert short == "no detectable alpha"
    assert text == (
        "BRK-B's alpha after fees, −0.5% a year, is statistically indistinguishable from zero "
        "(t = −0.40) over 10.0 years; 105% of its return was factor exposure an index fund "
        "sells for a few basis points."
    )


def test_verdict_no_alpha_without_factor_share():
    short, text = s.verdict("JEPI", "active-etf", fake_fit(0.004, 1.99, excess=0.009, nobs=54))
    assert short == "no detectable alpha"
    assert text == (
        "JEPI's alpha after fees, +0.4% a year, is statistically indistinguishable from zero "
        "(t = 1.99) over 4.5 years."
    )


def test_verdict_as_designed_names_the_largest_contribution():
    assert s.verdict("SPY", "index-fund", fake_fit(-0.0009, -0.35)) == (
        "as designed",
        "As designed: mostly market exposure (β = 1.02, R² = 0.99). "
        "What is left after fees is −0.1% a year (t = −0.35).",
    )
    value = fake_fit(0.012, 2.4)
    value["contributions"]["HML"] = -0.09
    value["betas"]["HML"]["coef"] = -0.45
    short, text = s.verdict("IWF", "index-fund", value)
    assert short == "as designed"  # passive funds are never "skill", whatever t says
    assert text.startswith("As designed: mostly value exposure (β = −0.45, R² = 0.99).")


def test_verdict_robustness_clause():
    clause = " With profitability and investment factors added, alpha is +1.0% a year (t = 1.10)."
    base = fake_fit(0.031, 2.5)
    assert s.verdict("FCNTX", "active-fund", base, fake_fit(0.0104, 1.1))[1].endswith(clause)
    flipped = s.verdict("DODGX", "active-fund", fake_fit(0.004, 0.5), fake_fit(-0.003, -0.3))[1]
    assert flipped.endswith("alpha is −0.3% a year (t = −0.30).")
    assert "profitability" not in s.verdict("FCNTX", "active-fund", base, fake_fit(0.02, 2.1))[1]
    assert "profitability" not in s.verdict("FCNTX", "active-fund", base)[1]
    passive = s.verdict("XLE", "sector-fund", fake_fit(-0.01, -1.0), fake_fit(0.002, 0.2))[1]
    assert passive.endswith("alpha is +0.2% a year (t = 0.20).")


def test_numbers_that_round_to_zero_have_no_sign():
    assert s.signed(-0.004, ".2f") == "0.00" and s.signed(-0.006, ".2f") == "−0.01"
    assert s.pct(-0.0004) == "0.0" and s.pct(0.0004) == "0.0" and s.pct(0.0) == "0.0"
    assert s.pct(-0.0006) == "−0.1" and s.pct(0.0006) == "+0.1"
    assert s.signed(-0.3, ".0f") == "0" and s.signed(0, "+d") == "0"
    text = s.verdict("SPY", "index-fund", fake_fit(-0.0004, -0.13))[1]
    assert text.endswith("What is left after fees is 0.0% a year (t = −0.13).")


def test_years_round_halves_up_like_the_site():
    assert [s.years(n) for n in (36, 75, 77, 81, 90, 120)] == [
        "3.0",
        "6.3",
        "6.4",
        "6.8",
        "7.5",
        "10.0",
    ]
    assert "over 6.3 years" in s.verdict("JEPI", "active-etf", fake_fit(0.004, 1.2, nobs=75))[1]


def test_every_verdict_short_is_known():
    assert {s.verdict_short(k, t) for k in KINDS for t in (-3, 0, 3)} == set(VERDICTS)


def test_factor_share():
    assert s.factor_share(0.01, 0.002) is None and s.factor_share(-0.03, 0.01) is None
    assert s.factor_share(0.10, 0.02) == pytest.approx(0.8)
    assert s.factor_share(0.10, -0.03) == pytest.approx(1.3)  # not clipped


def test_model_fit_is_rounded_and_still_adds_up(sample):
    a = FactorModel(sample["Hlth"], SAMPLE("carhart"), "carhart").fit()["Hlth"]
    rec = s.model_fit(a)
    assert rec["alpha_se_annual"] == pytest.approx(12 * a.bse["alpha"], abs=1e-6)
    assert abs(sum(rec["contributions"].values()) - rec["excess_annual"]) <= 1e-9
    assert rec["contributions"]["alpha"] == pytest.approx(a.alpha_annual, abs=5e-6)
    numbers = [rec["alpha_annual"], rec["r2"], *rec["premia"].values()]
    assert all(round(x, 6) == x for x in numbers)
    assert s.num(float("nan")) is None and str(s.num(-1e-9)) == "0.0"


# -- validation ----------------------------------------------------------------------------
def test_validate_catches_broken_data(tmp_path, built):
    out = tmp_path / "data"
    shutil.copytree(built, out)
    path = out / "funds" / "SPY.json"
    rec = json.loads(path.read_text())
    rec["models"]["carhart"]["contributions"]["MktRF"] += 0.001
    rec["growth"]["fund"] = rec["growth"]["fund"][:-1]
    rec["fee"]["alpha_gross"] = 0.5
    path.write_text(json.dumps(rec))
    (out / "funds" / "ZZZ.json").write_text("{}")
    errors = validate(out)
    assert any("contributions: sum differs" in e for e in errors)
    assert any("growth.months" in e or "growth.fund" in e for e in errors)
    assert any("SPY.json.fee" in e for e in errors)
    assert "funds/ZZZ.json: not listed in index.json" in errors
    assert live_validate.main([str(out)]) == 1
    (out / "meta.json").unlink()
    assert validate(out) == ["meta.json: missing"]


def test_validate_catches_a_stale_record_newer_than_through(tmp_path, built):
    out = tmp_path / "data"
    shutil.copytree(built, out)
    meta, index = load(out, "meta.json"), load(out, "index.json")
    meta["through"] = index["through"] = "2017-02"
    meta["stale"] = [e["ticker"] for e in index["funds"]]
    for e in index["funds"]:
        e["stale"] = True
        rec = load(out, f"funds/{e['ticker']}.json")
        (out / "funds" / f"{e['ticker']}.json").write_text(json.dumps({**rec, "stale": True}))
    (out / "meta.json").write_text(json.dumps(meta))
    (out / "index.json").write_text(json.dumps(index))
    errors = validate(out)
    assert "funds/SPY.json.window.end: 2017-03 is after through (2017-02)" in errors
    assert len(errors) == len(KIND)


def test_validation_failure_aborts_before_writing(tmp_path, standins, monkeypatch):
    monkeypatch.setattr(live_build, "validate", lambda path: ["funds/SPY.json: made-up problem"])
    with pytest.raises(BuildError, match="made-up problem"):
        run(tmp_path / "a" / "b" / "data", standins, save_prices=tmp_path / "saved.csv")
    assert list(tmp_path.iterdir()) == []  # no data, no parent directories, no saved prices


# -- the command line ----------------------------------------------------------------------
def test_saved_prices_replay_to_identical_files(tmp_path, standins):
    saved = tmp_path / "prices.csv"
    run(tmp_path / "fetched", fetch=stub_fetch(standins), save_prices=saved)
    replay = read_returns_csv(saved)
    pd.testing.assert_frame_equal(
        replay, standins.loc["1990-01":], check_freq=False, check_names=False
    )
    run(tmp_path / "replayed", replay)
    assert snapshot(tmp_path / "fetched") == snapshot(tmp_path / "replayed")


def test_command_line_offline_sample(tmp_path, standins, capsys):
    prices, funds_csv = tmp_path / "prices.csv", tmp_path / "funds.csv"
    standins.rename_axis("month").to_csv(prices)
    rows = [",".join(FUND_COLUMNS)]
    rows += [f"{f.ticker},{f.name},{f.kind},test,{f.expense_ratio},,TBD," for f in FUNDS]
    funds_csv.write_text("\n".join(rows) + "\n")
    out, saved = tmp_path / "data", tmp_path / "saved.csv"
    args = ["--out", str(out), "--prices", str(prices), "--funds", str(funds_csv)]
    assert live_build.main([*args, "--offline-sample", "--save-prices", str(saved)]) == 0
    text = capsys.readouterr().out
    assert "control SPY market β" in text and "11 funds (0 stale, 0 excluded)" in text
    meta = load(out, "meta.json")
    assert meta["robustness_model"] == "carhart" and "sample" in meta["sources"]["factors"]
    assert read_returns_csv(saved).shape == (327, 11) and validate(out) == []
    missing = tmp_path / "missing.csv"
    assert live_build.main(["--out", str(out), "--funds", str(missing)]) == 1
    assert "live.build:" in capsys.readouterr().err
