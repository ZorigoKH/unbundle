import numpy as np
import pytest
import statsmodels.api as sm

from unbundle import rolling_exposures

CARHART = ["MktRF", "SMB", "HML", "Mom"]


@pytest.fixture(scope="module")
def health(sample):
    return (sample["Hlth"] - sample["RF"]), sample[CARHART]


def test_each_window_is_a_plain_ols_fit(health):
    excess, factors = health
    roll = rolling_exposures(excess, factors, window=60)
    assert len(roll) == len(excess) - 60 + 1
    assert roll.index[0] == excess.index[59] and roll.index[-1] == excess.index[-1]
    for pos in (0, 200, len(roll) - 1):
        y = excess.iloc[pos : pos + 60].to_numpy()
        x = sm.add_constant(factors.iloc[pos : pos + 60].to_numpy())
        ref = sm.OLS(y, x).fit()
        np.testing.assert_allclose(roll.iloc[pos][CARHART].to_numpy(), ref.params[1:], rtol=1e-9)
        assert roll.iloc[pos]["alpha %/yr"] == pytest.approx(1200 * ref.params[0])
        assert roll.iloc[pos]["R²"] == pytest.approx(ref.rsquared)


def test_window_errors(health):
    excess, factors = health
    with pytest.raises(ValueError, match="too short"):
        rolling_exposures(excess, factors, window=5)
    with pytest.raises(ValueError, match="only 24 months"):
        rolling_exposures(excess.iloc[:24], factors, window=36)


def test_results_rolling_uses_the_first_asset_by_default(sample):
    from unbundle import FactorModel, load_factors

    res = FactorModel(sample[["Hlth", "Enrgy"]], load_factors("ff3", source="sample"), "ff3").fit()
    assert res.rolling(window=36).equals(res.rolling("Hlth", window=36))
    assert not res.rolling("Enrgy", window=36).equals(res.rolling("Hlth", window=36))
