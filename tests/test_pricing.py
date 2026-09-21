"""Joint alpha tests: the HAC Wald against linearmodels, GRS against its own algebra and a
simulation of its size under the null."""

import numpy as np
import pytest
from linearmodels.asset_pricing import TradedFactorModel

from unbundle import alpha_test, grs_test

FF3 = ["MktRF", "SMB", "HML"]


def test_hac_wald_matches_linearmodels_j_statistic(sample, size_value):
    ours = alpha_test(size_value, sample[FF3], maxlags=6)
    ref = TradedFactorModel(size_value, sample[FF3]).fit(
        cov_type="kernel", kernel="bartlett", bandwidth=6, debiased=False
    )
    assert ours.wald == pytest.approx(ref.j_statistic.stat, rel=1e-8)
    assert ours.wald_pvalue == pytest.approx(ref.j_statistic.pval, rel=1e-6, abs=1e-15)
    np.testing.assert_allclose(ours.alphas.to_numpy(), ref.alphas.to_numpy(), rtol=1e-10)


def test_grs_equals_its_unbiased_covariance_form(sample, size_value):
    y, f = size_value.to_numpy(), sample[FF3].to_numpy()
    t, n, k = y.shape[0], y.shape[1], f.shape[1]
    x = np.column_stack([np.ones(t), f])
    coef = np.linalg.lstsq(x, y, rcond=None)[0]
    resid = y - x @ coef
    a = coef[0]
    sigma_unbiased = resid.T @ resid / (t - k - 1)
    mu = f.mean(0)
    omega = np.cov(f, rowvar=False, bias=True)
    other_form = (
        (t / n)
        * ((t - n - k) / (t - k - 1))
        * (a @ np.linalg.solve(sigma_unbiased, a))
        / (1 + mu @ np.linalg.solve(omega, mu))
    )
    stat, p, df = grs_test(a, resid, f)
    assert stat == pytest.approx(other_form, rel=1e-12)
    assert df == (9, t - 9 - 3)
    assert 0 < p < 1


def _simulate(rng, alpha, t=120, n=9, k=3):
    f = rng.normal(0.006, 0.045, size=(t, k))
    b = rng.normal(1.0, 0.3, size=(k, n))
    y = alpha + f @ b + rng.normal(0, 0.02, size=(t, n))
    x = np.column_stack([np.ones(t), f])
    coef = np.linalg.lstsq(x, y, rcond=None)[0]
    return grs_test(coef[0], y - x @ coef, f)[1]


def test_grs_has_the_right_size_under_the_null():
    rng = np.random.default_rng(2026)
    rejections = np.mean([_simulate(rng, 0.0) < 0.05 for _ in range(1000)])
    assert 0.03 <= rejections <= 0.07  # exact F test: 5% nominal size


def test_grs_has_power_against_real_alphas():
    rng = np.random.default_rng(7)
    alphas = np.linspace(-0.01, 0.01, 9)  # up to 12%/yr mispricing
    assert np.mean([_simulate(rng, alphas) < 0.05 for _ in range(200)]) > 0.9


def test_alpha_test_reports_the_economic_size(sample, size_value):
    t = alpha_test(size_value, sample[FF3])
    worst, worst_alpha = t.max_abs_alpha
    assert worst == "S1V1" and worst_alpha < 0  # small growth: the notorious one
    assert t.mean_abs_alpha == pytest.approx(12 * np.abs(t.alphas).mean())
    assert t.maxlags == 6 and t.n_assets == 9
    assert "GRS" in repr(t) and "HAC Wald" in repr(t)


def test_alpha_test_needs_a_common_sample_and_enough_months(sample, size_value):
    gappy = size_value.copy()
    gappy.iloc[0, 0] = np.nan
    with pytest.raises(ValueError, match="common sample"):
        alpha_test(gappy, sample[FF3])
    with pytest.raises(ValueError, match="needs more months"):
        alpha_test(size_value.iloc[:12], sample[FF3])
