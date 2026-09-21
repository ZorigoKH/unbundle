"""Rolling-window exposures: how a fund's factor loadings drift over time.

A fund whose market beta climbs from 0.8 to 1.3, or whose momentum loading flips sign,
is not running the strategy it ran three years ago - even if its full-sample alpha looks
steady. Each window is a plain OLS fit on the trailing ``window`` months.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rolling_exposures(excess: pd.Series, factors: pd.DataFrame, window: int = 36) -> pd.DataFrame:
    """Alpha (annualized), loadings and R² on each trailing window, indexed by its last month."""
    excess, factors = excess.align(factors, join="inner", axis=0)
    k = factors.shape[1]
    if window <= k + 2:
        raise ValueError(f"window of {window} months is too short for {k} factors")
    if len(excess) < window:
        raise ValueError(f"only {len(excess)} months of data; window is {window}")
    y_all = excess.to_numpy(dtype=float)
    x_all = np.column_stack([np.ones(len(y_all)), factors.to_numpy(dtype=float)])
    rows = []
    for end in range(window, len(y_all) + 1):
        y = y_all[end - window : end]
        x = x_all[end - window : end]
        coef = np.linalg.lstsq(x, y, rcond=None)[0]
        resid = y - x @ coef
        dev = y - y.mean()
        r2 = 1.0 - (resid @ resid) / (dev @ dev) if dev @ dev > 0 else np.nan
        rows.append([1200 * coef[0], *coef[1:], r2])
    return pd.DataFrame(
        rows,
        index=excess.index[window - 1 :],
        columns=["alpha %/yr", *factors.columns, "R²"],
    )
