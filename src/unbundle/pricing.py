"""Joint tests that a factor model prices a set of assets: are all the alphas zero?

Two versions, because they answer slightly different questions:

* **GRS** (Gibbons, Ross & Shanken 1989) - the exact finite-sample F test under normal,
  homoskedastic, serially uncorrelated errors. With maximum-likelihood covariances
  ``Sigma`` (residuals) and ``Omega`` (factors),

      GRS = (T - N - L) / N * a' Sigma^-1 a / (1 + mu' Omega^-1 mu)  ~  F(N, T - N - L)

  where ``a`` are the N alphas, ``mu`` the L factor means and T the number of months.

* **HAC Wald** - the same hypothesis with a Newey-West covariance of all N regressions
  stacked together, so it survives heteroskedasticity and autocorrelation; asymptotically
  chi-squared with N degrees of freedom. Matches linearmodels' ``TradedFactorModel``
  J-statistic (Bartlett kernel, ``debiased=False``).

Over decades of monthly data both reject almost every model - the test has enormous power.
The economically useful number is how *big* the alphas are, so :class:`AlphaTest` reports
the mean absolute alpha alongside.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .model import newey_west_lags


@dataclass
class AlphaTest:
    alphas: pd.Series
    nobs: int
    grs: float
    grs_pvalue: float
    grs_df: tuple[int, int]
    wald: float
    wald_pvalue: float
    maxlags: int

    @property
    def n_assets(self) -> int:
        return int(self.alphas.shape[0])

    @property
    def mean_abs_alpha(self) -> float:
        """Average |alpha| across assets, annualized."""
        return float(12 * self.alphas.abs().mean())

    @property
    def max_abs_alpha(self) -> tuple[str, float]:
        name = self.alphas.abs().idxmax()
        return str(name), float(12 * self.alphas[name])

    def __repr__(self) -> str:
        worst, worst_alpha = self.max_abs_alpha
        return (
            f"<AlphaTest: {self.n_assets} assets, {self.nobs} months | "
            f"GRS F{self.grs_df} = {self.grs:.2f} (p = {self.grs_pvalue:.2g}) | "
            f"HAC Wald chi2({self.n_assets}) = {self.wald:.2f} (p = {self.wald_pvalue:.2g}) | "
            f"mean |alpha| {100 * self.mean_abs_alpha:.2f} %/yr, largest {worst} "
            f"{100 * worst_alpha:+.2f} %/yr>"
        )


def grs_test(
    alphas: np.ndarray, resid: np.ndarray, factors: np.ndarray
) -> tuple[float, float, tuple[int, int]]:
    """GRS statistic, p-value and degrees of freedom from alphas, residuals and factors."""
    t, n = resid.shape
    k = factors.shape[1]
    if t - n - k < 1:
        raise ValueError(f"GRS needs more months ({t}) than assets + factors ({n + k})")
    sigma = resid.T @ resid / t
    mu = factors.mean(axis=0)
    omega = np.atleast_2d(np.cov(factors, rowvar=False, bias=True))
    quad_alpha = float(alphas @ np.linalg.solve(sigma, alphas))
    quad_mu = float(mu @ np.linalg.solve(omega, mu))
    stat = (t - n - k) / n * quad_alpha / (1.0 + quad_mu)
    df = (n, t - n - k)
    return stat, float(stats.f.sf(stat, *df)), df


def hac_wald(alphas: np.ndarray, resid: np.ndarray, x: np.ndarray, maxlags: int) -> float:
    """Wald statistic for all alphas = 0 with a Newey-West covariance across equations."""
    t, n = resid.shape
    k1 = x.shape[1]
    scores = np.einsum("tn,tk->tnk", resid, x).reshape(t, n * k1)
    meat = scores.T @ scores
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        gamma = scores[lag:].T @ scores[:-lag]
        meat += weight * (gamma + gamma.T)
    bread = np.kron(np.eye(n), np.linalg.inv(x.T @ x))
    cov = bread @ meat @ bread
    rows = np.arange(n) * k1
    v_alpha = cov[np.ix_(rows, rows)]
    return float(alphas @ np.linalg.solve(v_alpha, alphas))


def alpha_test(
    excess: pd.DataFrame, factors: pd.DataFrame, *, maxlags: int | None = None
) -> AlphaTest:
    """Test that every column of ``excess`` has zero alpha against ``factors``.

    ``excess`` holds excess returns (one column per asset) and ``factors`` the factor
    returns only - no ``RF`` column - on the same months.
    """
    excess, factors = excess.align(factors, join="inner", axis=0)
    if excess.isna().any().any() or factors.isna().any().any():
        raise ValueError("drop missing months first: the joint test needs a common sample")
    y = excess.to_numpy(dtype=float)
    f = factors.to_numpy(dtype=float)
    t = y.shape[0]
    x = np.column_stack([np.ones(t), f])
    coef = np.linalg.lstsq(x, y, rcond=None)[0]
    alphas = coef[0]
    resid = y - x @ coef
    grs, grs_p, grs_df = grs_test(alphas, resid, f)
    lags = newey_west_lags(t) if maxlags is None else maxlags
    wald = hac_wald(alphas, resid, x, lags)
    return AlphaTest(
        alphas=pd.Series(alphas, index=excess.columns),
        nobs=t,
        grs=grs,
        grs_pvalue=grs_p,
        grs_df=grs_df,
        wald=wald,
        wald_pvalue=float(stats.chi2.sf(wald, y.shape[1])),
        maxlags=lags,
    )
