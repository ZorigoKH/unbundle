"""Factor regressions agree with statsmodels (single equation) and linearmodels (system)."""

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from linearmodels.asset_pricing import TradedFactorModel

from unbundle import FactorModel, load_factors, newey_west_lags

CARHART = ["MktRF", "SMB", "HML", "Mom"]


@pytest.fixture(scope="module")
def industries(sample):
    return sample[["Enrgy", "BusEq", "Hlth", "Money"]]


@pytest.fixture(scope="module")
def results(industries):
    factors = load_factors("carhart", source="sample", start="1963-07")
    return FactorModel(industries, factors, "carhart").fit()


def test_newey_west_rule_of_thumb():
    assert newey_west_lags(645) == 6
    assert newey_west_lags(120) == 4
    assert newey_west_lags(36) == 3


def test_every_number_matches_statsmodels_hac(sample, results):
    x = sm.add_constant(sample[CARHART].to_numpy())
    for name, a in results.items():
        y = (sample[name] - sample["RF"]).to_numpy()
        ref = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": a.maxlags}, use_t=True)
        np.testing.assert_allclose(a.params.to_numpy(), ref.params, rtol=1e-10)
        np.testing.assert_allclose(a.bse.to_numpy(), ref.bse, rtol=1e-9)
        np.testing.assert_allclose(a.tvalues.to_numpy(), ref.tvalues, rtol=1e-9)
        np.testing.assert_allclose(a.pvalues.to_numpy(), ref.pvalues, rtol=1e-7, atol=1e-14)
        assert a.r2 == pytest.approx(ref.rsquared, rel=1e-10)
        assert a.r2_adj == pytest.approx(ref.rsquared_adj, rel=1e-10)


def test_alphas_betas_and_alpha_errors_match_linearmodels_system(sample, industries, results):
    excess = industries.sub(sample["RF"], axis=0)
    ref = TradedFactorModel(excess, sample[CARHART]).fit(
        cov_type="kernel", kernel="bartlett", bandwidth=6, debiased=False
    )
    names = list(industries.columns)
    np.testing.assert_allclose([results[n].alpha for n in names], ref.alphas.to_numpy(), rtol=1e-10)
    np.testing.assert_allclose(
        np.array([results[n].betas.to_numpy() for n in names]), ref.betas.to_numpy(), rtol=1e-10
    )
    ref_se = np.sqrt(
        np.diag(ref.cov.loc[[f"alpha-{n}" for n in names], [f"alpha-{n}" for n in names]])
    )
    np.testing.assert_allclose([results[n].bse["alpha"] for n in names], ref_se, rtol=1e-9)


def test_attribution_sums_exactly_to_the_excess_return(results):
    for a in results.values():
        assert a.contributions.sum() == pytest.approx(a.excess_annual, rel=1e-12, abs=1e-14)
        rebuilt = a.alpha + a.replicating + a.residuals
        np.testing.assert_allclose(rebuilt.to_numpy(), a.excess.to_numpy(), atol=1e-14)
        assert list(a.contributions.index) == [*CARHART, "alpha"]


def test_tracking_error_and_information_ratio(results):
    a = results["Hlth"]
    dof = a.nobs - len(a.factors) - 1
    expected_te = np.sqrt(12 * (a.residuals**2).sum() / dof)
    assert a.tracking_error == pytest.approx(expected_te)
    assert a.information_ratio == pytest.approx(a.alpha_annual / expected_te)


def test_assets_with_different_histories_use_their_own_months(sample):
    frame = sample[["Hlth", "Enrgy"]].copy()
    frame.loc[:"1989-12", "Enrgy"] = np.nan  # a fund launched in 1990
    factors = load_factors("ff3", source="sample", start="1963-07")
    res = FactorModel(frame, factors, "ff3").fit()
    assert str(res["Enrgy"].start) == "1990-01" and str(res["Hlth"].start) == "1963-07"
    alone = FactorModel(sample.loc["1990-01":, ["Enrgy"]], factors, "ff3").fit()["Enrgy"]
    np.testing.assert_allclose(res["Enrgy"].params.to_numpy(), alone.params.to_numpy())
    table = res.table()
    assert list(table.index) == ["Hlth", "Enrgy"] and table.loc["Enrgy", "months"] == alone.nobs


def test_excess_returns_can_be_passed_directly(sample, results):
    excess = (sample["Hlth"] - sample["RF"]).rename("Hlth")
    factors = sample[CARHART]
    direct = FactorModel(excess, factors, "carhart", excess=True).fit()["Hlth"]
    np.testing.assert_allclose(direct.params.to_numpy(), results["Hlth"].params.to_numpy())
    assert direct.rf is None


def test_dates_are_accepted_instead_of_periods(sample):
    frame = sample[["Hlth"]].copy()
    frame.index = frame.index.to_timestamp(how="end")
    factors = load_factors("capm", source="sample", start="1963-07")
    a = FactorModel(frame, factors, "capm").fit()["Hlth"]
    assert a.nobs == len(sample)


def test_errors_are_explained(sample):
    factors = load_factors("ff3", source="sample")
    with pytest.raises(ValueError, match="no Mom"):
        FactorModel(sample[["Hlth"]], factors, "carhart")
    with pytest.raises(ValueError, match="RF column"):
        FactorModel(sample[["Hlth"]], factors.drop(columns="RF"), "ff3")
    with pytest.raises(ValueError, match="need at least 24"):
        FactorModel(sample.loc["2016-01":, ["Hlth"]], factors, "ff3").fit()


def test_summary_and_table_render(results):
    text = results["Hlth"].summary()
    assert "Hlth" in text and "alpha" in text and "Newey-West" in text and "6 lags" in text
    frame = results["Hlth"].to_frame()
    assert list(frame.index) == ["alpha", *CARHART]
    assert frame["contribution %/yr"].sum() == pytest.approx(100 * results["Hlth"].excess_annual)
    assert isinstance(results.table(), pd.DataFrame) and len(results) == 4
