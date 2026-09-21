"""Time-series factor regressions with Newey-West standard errors, and return attribution.

For a fund with excess return ``r - rf`` and traded factors ``f``:

    r_t - rf_t = alpha + beta' f_t + e_t

``beta' f_t`` is the part of the return you could have bought by holding the factor
portfolios; ``alpha`` is what is left. Averaging both sides gives the attribution that
names this package - it holds exactly for OLS with an intercept:

    mean(r - rf) = alpha + sum_k beta_k * mean(f_k)

Monthly returns are autocorrelated and heteroskedastic, so standard errors are
Newey-West (HAC, Bartlett kernel) - computed by ``sandwich``, verified against statsmodels.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sandwich import OLS

from .factors import FACTOR_LABELS, resolve_model
from .returns import excess_returns

MIN_OBS = 24


def newey_west_lags(nobs: int) -> int:
    """Newey & West (1994) rule of thumb: floor(4 (T/100)^(2/9)). 6 lags for 50 years of months."""
    return int(np.floor(4 * (nobs / 100) ** (2 / 9)))


@dataclass
class Attribution:
    """One asset's factor regression: loadings, alpha, and where its average return came from."""

    name: str
    model: str
    factors: tuple[str, ...]
    maxlags: int
    params: pd.Series
    bse: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    r2: float
    r2_adj: float
    excess: pd.Series
    factor_returns: pd.DataFrame
    residuals: pd.Series = field(repr=False)
    rf: pd.Series | None = field(default=None, repr=False)

    # -- the headline numbers -----------------------------------------------------------
    @property
    def nobs(self) -> int:
        return int(self.excess.shape[0])

    @property
    def start(self) -> pd.Period:
        return self.excess.index[0]

    @property
    def end(self) -> pd.Period:
        return self.excess.index[-1]

    @property
    def alpha(self) -> float:
        """Monthly alpha."""
        return float(self.params["alpha"])

    @property
    def alpha_annual(self) -> float:
        return 12 * self.alpha

    @property
    def alpha_t(self) -> float:
        return float(self.tvalues["alpha"])

    @property
    def alpha_p(self) -> float:
        return float(self.pvalues["alpha"])

    @property
    def betas(self) -> pd.Series:
        return self.params[list(self.factors)]

    @property
    def excess_annual(self) -> float:
        """Average excess return over the risk-free rate, per year."""
        return 12 * float(self.excess.mean())

    @property
    def tracking_error(self) -> float:
        """Annualized volatility of the residual - the return the factors do not explain."""
        dof = self.nobs - len(self.factors) - 1
        return float(np.sqrt(12 * (self.residuals @ self.residuals) / dof))

    @property
    def information_ratio(self) -> float:
        return self.alpha_annual / self.tracking_error if self.tracking_error > 0 else np.nan

    @property
    def premia(self) -> pd.Series:
        """Average factor returns over this asset's sample, per year."""
        return 12 * self.factor_returns.mean()

    @property
    def contributions(self) -> pd.Series:
        """Annualized excess return split into beta_k * E[f_k] per factor, plus alpha.

        The entries sum exactly to ``excess_annual``.
        """
        parts = self.betas * self.premia
        return pd.concat([parts, pd.Series({"alpha": self.alpha_annual})])

    @property
    def replicating(self) -> pd.Series:
        """The factor-mimicking excess return, sum_k beta_k f_k: what the factors alone paid."""
        return self.factor_returns @ self.betas

    # -- presentation ---------------------------------------------------------------------
    def to_frame(self) -> pd.DataFrame:
        """Coefficient table with the attribution alongside."""
        rows = ["alpha", *self.factors]
        premium = pd.concat([pd.Series({"alpha": np.nan}), self.premia])
        return pd.DataFrame(
            {
                "coef": self.params[rows],
                "std err (NW)": self.bse[rows],
                "t": self.tvalues[rows],
                "p": self.pvalues[rows],
                "premium %/yr": 100 * premium[rows],
                "contribution %/yr": 100 * self.contributions[rows],
            }
        )

    def summary(self) -> str:
        width = 72
        head = f"{self.name}  ·  {self.model}  ·  {self.start} to {self.end}  ·  {self.nobs} months"
        lines = [head, "=" * width]
        lines.append(f"{'Excess return over T-bills':<34}{100 * self.excess_annual:>9.2f} %/yr")
        for factor in self.factors:
            name = FACTOR_LABELS.get(factor, factor).lower()
            label = f"  from {name}  (beta {self.betas[factor]:.2f})"
            lines.append(f"{label:<34}{100 * self.contributions[factor]:>9.2f} %/yr")
        lines.append(
            f"{'  alpha':<34}{100 * self.alpha_annual:>9.2f} %/yr"
            f"   t = {self.alpha_t:.2f}, p = {self.alpha_p:.3f}"
        )
        lines.append("-" * width)
        lines.append(
            f"R² {self.r2:.3f}   tracking error {100 * self.tracking_error:.2f} %/yr   "
            f"information ratio {self.information_ratio:.2f}"
        )
        lines.append(f"Newey-West standard errors, {self.maxlags} lags")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.summary()


class Results(Mapping[str, Attribution]):
    """Attributions for one or more assets, keyed by name."""

    def __init__(
        self,
        attributions: dict[str, Attribution],
        model: str,
        excess: pd.DataFrame,
        factor_returns: pd.DataFrame,
    ):
        self._attributions = attributions
        self.model = model
        self.factors = resolve_model(model)
        self.excess = excess
        self.factor_returns = factor_returns

    def __getitem__(self, key: str) -> Attribution:
        return self._attributions[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._attributions)

    def __len__(self) -> int:
        return len(self._attributions)

    def table(self) -> pd.DataFrame:
        """One row per asset: sample, excess return, alpha and its t-stat, loadings, fit."""
        rows = {}
        for name, a in self._attributions.items():
            row = {
                "start": str(a.start),
                "end": str(a.end),
                "months": a.nobs,
                "excess %/yr": 100 * a.excess_annual,
                "alpha %/yr": 100 * a.alpha_annual,
                "t(alpha)": a.alpha_t,
            }
            row.update({f"b_{f}": a.betas[f] for f in self.factors})
            row.update({"R²": a.r2, "IR": a.information_ratio})
            rows[name] = row
        return pd.DataFrame.from_dict(rows, orient="index")

    def alpha_test(self, maxlags: int | None = None):
        """Joint test that every alpha is zero (GRS F and HAC Wald), on the common sample."""
        from .pricing import alpha_test

        common = self.excess.dropna()
        return alpha_test(common, self.factor_returns.loc[common.index], maxlags=maxlags)

    def rolling(self, name: str | None = None, window: int = 36) -> pd.DataFrame:
        """Rolling-window alpha and loadings for one asset (the first if not named)."""
        from .rolling import rolling_exposures

        a = self[name] if name is not None else next(iter(self._attributions.values()))
        return rolling_exposures(a.excess, a.factor_returns, window=window)

    def summary(self) -> str:
        return "\n\n".join(a.summary() for a in self._attributions.values())

    def __repr__(self) -> str:
        return self.summary()


class FactorModel:
    """``FactorModel(returns, factors, model="carhart").fit()``.

    ``returns`` is a Series or DataFrame of monthly total returns (decimals) on a monthly
    ``PeriodIndex``; ``factors`` is what :func:`unbundle.load_factors` returns, including
    ``RF``. Pass ``excess=True`` if the returns are already net of the risk-free rate. Each
    asset is fitted on every month it has data, so funds with different histories can be
    compared side by side.
    """

    def __init__(
        self,
        returns: pd.Series | pd.DataFrame,
        factors: pd.DataFrame,
        model: str = "carhart",
        *,
        excess: bool = False,
    ):
        self.model = model.lower()
        self.factors = resolve_model(model)
        missing = [f for f in self.factors if f not in factors.columns]
        if missing:
            raise ValueError(f"factor data has no {', '.join(missing)} (needed for {model})")
        frame = returns.to_frame() if isinstance(returns, pd.Series) else returns
        if not isinstance(frame.index, pd.PeriodIndex):
            frame = frame.copy()
            frame.index = pd.PeriodIndex(pd.to_datetime(frame.index), freq="M")
        if excess:
            frame, factors = frame.align(factors, join="inner", axis=0)
        else:
            if "RF" not in factors.columns:
                raise ValueError("factors need an RF column, or pass excess=True")
            frame = excess_returns(frame, factors["RF"])
            factors = factors.loc[frame.index]
        self.excess = frame
        self.factor_returns = factors.loc[:, list(self.factors)]
        self.rf = factors["RF"] if "RF" in factors.columns else None

    def fit(self, maxlags: int | None = None) -> Results:
        """Regress each asset on the factors; ``maxlags`` defaults to the Newey-West rule."""
        out = {}
        for name in self.excess.columns:
            y = self.excess[name].dropna()
            f = self.factor_returns.loc[y.index]
            if len(y) < MIN_OBS:
                raise ValueError(f"{name}: only {len(y)} months of data; need at least {MIN_OBS}")
            lags = newey_west_lags(len(y)) if maxlags is None else maxlags
            x = np.column_stack([np.ones(len(y)), f.to_numpy()])
            names = ["alpha", *self.factors]
            res = OLS(y.to_numpy(), x, names=names).fit(cov_type="HAC", maxlags=lags)
            out[str(name)] = Attribution(
                name=str(name),
                model=self.model,
                factors=self.factors,
                maxlags=lags,
                params=pd.Series(res.params, index=names),
                bse=pd.Series(res.bse, index=names),
                tvalues=pd.Series(res.tvalues, index=names),
                pvalues=pd.Series(res.pvalues, index=names),
                r2=res.r2,
                r2_adj=res.r2_adj,
                excess=y,
                factor_returns=f,
                residuals=pd.Series(res.resid, index=y.index),
                rf=None if self.rf is None else self.rf.loc[y.index],
            )
        return Results(out, self.model, self.excess, self.factor_returns)
