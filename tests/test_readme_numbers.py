"""Every number quoted in the README, recomputed from the bundled data.

If the math changes, the README is wrong - and this file fails first.
"""

import numpy as np
import pytest

from unbundle import FACTOR_SETS, TEST_ASSETS, FactorModel, alpha_test, load_factors

GRS_TABLE = {
    # (test assets, model): (GRS, p-value, mean |alpha| %/yr, worst portfolio, its alpha %/yr)
    ("size-value", "capm"): (7.19, "5.5e-10", 3.31, "S1V5", 6.6),
    ("size-value", "ff3"): (5.97, "4.8e-08", 1.58, "S1V1", -6.3),
    ("size-value", "carhart"): (5.12, "1.0e-06", 1.46, "S1V1", -5.6),
    ("size-momentum", "capm"): (11.04, "4.5e-16", 4.98, "S1M5", 8.6),
    ("size-momentum", "ff3"): (10.32, "6.1e-15", 5.04, "S1M1", -12.1),
    ("size-momentum", "carhart"): (7.89, "4.4e-11", 1.76, "S1M1", -4.7),
    ("industries", "capm"): (2.23, "9.3e-03", 1.55, "NoDur", 3.4),
    ("industries", "ff3"): (4.43, "7.7e-07", 2.06, "Hlth", 5.1),
    ("industries", "carhart"): (4.10, "3.5e-06", 1.75, "Hlth", 4.4),
}

INDUSTRIES = {
    # column: (excess, market, size, value, momentum, alpha) in %/yr, then t(alpha), R²
    "Enrgy": (7.32, 5.60, -0.54, 1.18, 0.78, 0.29, 0.16, 0.47),
    "BusEq": (7.31, 6.80, 0.55, -2.57, -0.81, 3.34, 2.45, 0.81),
    "Hlth": (8.21, 5.25, -0.63, -1.31, 0.55, 4.36, 3.15, 0.63),
}


@pytest.fixture(scope="module")
def carhart(sample):
    factors = load_factors("carhart", source="sample", start="1963-07")
    return FactorModel(sample[list(INDUSTRIES)], factors, "carhart").fit()


@pytest.mark.parametrize(("key", "expected"), GRS_TABLE.items())
def test_grs_table(sample, key, expected):
    assets, model = key
    grs, p, mean_abs, worst, worst_alpha = expected
    excess = sample[list(TEST_ASSETS[assets])].sub(sample["RF"], axis=0)
    t = alpha_test(excess, sample[list(FACTOR_SETS[model])])
    assert t.nobs == 645
    assert round(t.grs, 2) == grs
    assert f"{t.grs_pvalue:.1e}" == p
    assert round(100 * t.mean_abs_alpha, 2) == mean_abs
    name, alpha = t.max_abs_alpha
    assert (name, round(100 * alpha, 1)) == (worst, worst_alpha)


def test_industry_attributions(carhart):
    for name, (*parts, t, r2) in INDUSTRIES.items():
        a = carhart[name]
        excess, *contributions = parts
        assert round(100 * a.excess_annual, 2) == excess
        assert list(np.round(100 * a.contributions.to_numpy(), 2)) == contributions
        assert round(a.alpha_t, 2) == t
        assert round(a.r2, 2) == r2
        # t(alpha) is roughly the information ratio times the square root of the years
        assert a.information_ratio * np.sqrt(a.nobs / 12) == pytest.approx(a.alpha_t, rel=0.05)


def test_health_care_compounds_to_470_against_60(carhart):
    h = carhart["Hlth"]
    assert round((1 + h.excess + h.rf).prod()) == 470
    assert round((1 + h.replicating + h.rf).prod()) == 60


def test_volatility_drag_outweighs_energys_alpha(carhart):
    e = carhart["Enrgy"]
    assert round((1 + e.excess + e.rf).prod()) == 243
    assert round((1 + e.replicating + e.rf).prod()) == 341
    assert round(100 * e.tracking_error, 1) == 13.8
    assert round(100 * e.tracking_error**2 / 2, 2) == 0.95  # the drag, %/yr
    assert round(100 * e.alpha_annual, 2) == 0.29


def test_health_care_alpha_rises_when_size_and_value_enter(sample):
    fits = {}
    for model in ("capm", "ff3"):
        factors = load_factors(model, source="sample", start="1963-07")
        fits[model] = FactorModel(sample[["Hlth"]], factors, model).fit()["Hlth"]
    capm, ff3 = fits["capm"], fits["ff3"]
    assert (round(100 * capm.alpha_annual, 1), round(capm.alpha_t, 2)) == (3.0, 2.02)
    assert (round(100 * ff3.alpha_annual, 1), round(ff3.alpha_t, 2)) == (5.1, 3.86)
    assert (round(ff3.betas["SMB"], 2), round(ff3.betas["HML"], 2)) == (-0.24, -0.33)
    tilts = 100 * (ff3.contributions["SMB"] + ff3.contributions["HML"])
    assert round(tilts, 1) == -2.0  # what the large-growth tilt "should" have cost
