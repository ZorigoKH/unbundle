"""Pure functions from fitted factor models to the JSON records the website reads.

Nothing here reads files or the network. Every number is a decimal (0.012 is 1.2%), per
year where the name says ``annual``, and rounded to 6 decimals; months are ``"YYYY-MM"``.

Returns come from adjusted prices, which are net of the fund's fees, so every alpha here
is *after fees*. Adding the expense ratio back gives the value the manager added before
charging for it; that is also the fee at which an investor would have broken even with
T-bills plus the same factor exposure.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from unbundle import FACTOR_LABELS, Attribution, rolling_exposures

from . import (
    HEADLINE_MODEL,
    PASSIVE_KINDS,
    ROBUSTNESS_MODEL,
    ROLLING_WINDOW,
    SCHEMA_VERSION,
    WINDOW_MONTHS,
    Fund,
)

DECIMALS = 6
Z95 = 1.96
SHARE_MIN_EXCESS = 0.01  # factor_share only when the fund beat T-bills by > 1% a year

SUMMARY_KEYS = (
    "ticker",
    "name",
    "kind",
    "category",
    "expense_ratio",
    "window",
    "short_history",
    "stale",
    "excess_annual",
    "alpha_annual",
    "alpha_t",
    "alpha_p",
    "r2",
    "factor_share",
    "verdict_short",
)


# -- numbers and text ----------------------------------------------------------------------
def num(x: float) -> float | None:
    """``x`` rounded to 6 decimals for JSON; None if it is not a finite number."""
    x = float(x)
    if not math.isfinite(x):
        return None
    return round(x, DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0


def month(period: pd.Period) -> str:
    """``"YYYY-MM"`` for a monthly period."""
    return pd.Period(period, freq="M").strftime("%Y-%m")


def signed(x: float, spec: str) -> str:
    """``format(x, spec)`` with a typographic minus (−) for negative numbers.

    A number that rounds to zero is written without a sign ("0.0", not "+0.0" or "−0.0"),
    so a rounded alpha can never seem to disagree in sign with its t-statistic.
    """
    text = format(x, spec)
    if not any(c in "123456789" for c in text):
        text = format(x * 0, spec.replace("+", "")).replace("-", "")
    return text.replace("-", "−")


def pct(x: float, spec: str = "+.1f") -> str:
    """A decimal as a percentage number, without the % sign: 0.0123 -> "+1.2"."""
    return signed(100 * x, spec)


def years(months: int) -> str:
    """A window's length in years to one decimal, halves rounded up: 75 months -> "6.3".

    Integer arithmetic, so the site's ``years()`` in ``web/lib/format.ts`` gives the same.
    """
    tenths = (10 * months + 6) // 12
    return f"{tenths // 10}.{tenths % 10}"


# -- one fitted model ----------------------------------------------------------------------
def model_fit(a: Attribution) -> dict[str, Any]:
    """The ``ModelFit`` record: loadings, alpha, premia and the attribution, per year.

    Each number is rounded separately, so the alpha contribution absorbs the rounding
    (a few millionths) to keep the published contributions summing to ``excess_annual``.
    """
    factors = list(a.factors)
    excess = num(a.excess_annual)
    contributions = {f: num(a.contributions[f]) for f in factors}
    contributions["alpha"] = num(excess - sum(contributions.values()))
    return {
        "model": a.model,
        "factors": factors,
        "nobs": a.nobs,
        "maxlags": a.maxlags,
        "alpha_annual": num(a.alpha_annual),
        "alpha_se_annual": num(12 * a.bse["alpha"]),
        "alpha_t": num(a.alpha_t),
        "alpha_p": num(a.alpha_p),
        "betas": {
            f: {"coef": num(a.params[f]), "se": num(a.bse[f]), "t": num(a.tvalues[f])}
            for f in factors
        },
        "premia": {f: num(a.premia[f]) for f in factors},
        "contributions": contributions,
        "excess_annual": excess,
        "r2": num(a.r2),
        "r2_adj": num(a.r2_adj),
        "tracking_error": num(a.tracking_error),
        "information_ratio": num(a.information_ratio),
    }


def window(a: Attribution) -> dict[str, Any]:
    return {"start": month(a.start), "end": month(a.end), "months": a.nobs}


def factor_share(excess_annual: float, alpha_annual: float) -> float | None:
    """The share of the average excess return that was factor exposure: 1 - alpha/excess.

    Defined only when the fund beat T-bills by more than 1% a year, and not clipped: a fund
    with negative alpha shows more than 100%.
    """
    if excess_annual <= SHARE_MIN_EXCESS:
        return None
    return num(1 - alpha_annual / excess_annual)


def fee(fit: Mapping[str, Any], expense_ratio: float) -> dict[str, Any]:
    """Alpha after fees, before fees (alpha + expense ratio), its 95% interval, break-even fee."""
    net, se = fit["alpha_annual"], fit["alpha_se_annual"]
    gross = num(net + expense_ratio)
    return {
        "expense_ratio": num(expense_ratio),
        "alpha_net": net,
        "alpha_gross": gross,
        "alpha_ci95": [num(net - Z95 * se), num(net + Z95 * se)],
        "breakeven_fee": gross,
    }


def growth(a: Attribution) -> dict[str, Any]:
    """Growth of $1 over the fit window.

    ``months[0]`` is the month before the window, where every series is 1.0; each later
    entry is the value at the end of that month. ``fund`` compounds the fund's total
    return, ``replica`` T-bills plus the fund's factor exposure (sum of beta_k f_k), and
    ``tbills`` the risk-free rate alone.
    """
    if a.rf is None:
        raise ValueError(f"{a.name}: growth of $1 needs the risk-free rate")
    rf = a.rf.loc[a.excess.index]
    gross = {
        "fund": 1 + a.excess + rf,
        "replica": 1 + rf + a.replicating,
        "tbills": 1 + rf,
    }
    out: dict[str, Any] = {"months": [month(a.start - 1), *(month(m) for m in a.excess.index)]}
    for name, series in gross.items():
        out[name] = [1.0, *(num(v) for v in series.cumprod())]
    return out


def growth_returns(growth: Mapping[str, Any]) -> dict[str, float]:
    """The monthly fund returns a published growth series implies: consecutive ratios - 1."""
    fund = growth["fund"]
    return {m: fund[i] / fund[i - 1] - 1 for i, m in enumerate(growth["months"]) if i > 0}


def rolling(
    excess: pd.Series, factors: pd.DataFrame, window: int = ROLLING_WINDOW
) -> dict[str, Any]:
    """Alpha (per year), loadings and R² on each trailing ``window`` of months."""
    roll = rolling_exposures(excess, factors, window=window)
    return {
        "window": window,
        "months": [month(m) for m in roll.index],
        "alpha_annual": [num(v / 100) for v in roll["alpha %/yr"]],  # unbundle gives percent
        "betas": {f: [num(v) for v in roll[f]] for f in factors.columns},
        "r2": [num(v) for v in roll["R²"]],
    }


# -- verdicts ------------------------------------------------------------------------------
def verdict_short(kind: str, alpha_t: float) -> str:
    """The one-phrase verdict: passive funds are judged on design, the rest on t(alpha)."""
    if kind in PASSIVE_KINDS:
        return "as designed"
    if alpha_t >= 2:
        return "skill"
    if alpha_t <= -2:
        return "trails its factors"
    return "no detectable alpha"


def _robustness_differs(fit: Mapping[str, Any], robust: Mapping[str, Any]) -> bool:
    """True when the robustness alpha flips sign or crosses |t| = 2 against the headline."""
    a, a5 = fit["alpha_annual"], robust["alpha_annual"]
    t, t5 = fit["alpha_t"], robust["alpha_t"]
    return (a < 0) != (a5 < 0) or (abs(t) >= 2) != (abs(t5) >= 2)


def verdict(
    ticker: str,
    kind: str,
    fit: Mapping[str, Any],
    robust: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """``(verdict_short, verdict)`` from the headline (Carhart) ``ModelFit`` record.

    ``robust`` is the Fama-French five factors plus momentum fit; when its alpha tells a
    different story (a flipped sign, or |t| on the other side of 2) a sentence saying so
    is appended.
    """
    a, t = fit["alpha_annual"], fit["alpha_t"]
    n = years(fit["nobs"])
    short = verdict_short(kind, t)
    if short == "as designed":
        top = max(fit["factors"], key=lambda f: abs(fit["contributions"][f]))
        text = (
            f"As designed: mostly {FACTOR_LABELS.get(top, top).lower()} exposure "
            f"(β = {signed(fit['betas'][top]['coef'], '.2f')}, R² = {fit['r2']:.2f}). "
            f"What is left after fees is {pct(a)}% a year (t = {signed(t, '.2f')})."
        )
    elif short == "skill":
        text = (
            f"After fees, {ticker} earned {pct(a)}% a year more than its factor exposure "
            f"explains (t = {signed(t, '.2f')}) over {n} years: evidence of skill."
        )
    elif short == "trails its factors":
        text = (
            f"After fees, {ticker} trailed its factor exposure by {pct(abs(a), '.1f')}% a year "
            f"(t = {signed(t, '.2f')}) over {n} years: "
            "its fee cost more than the manager added."
        )
    else:
        text = (
            f"{ticker}'s alpha after fees, {pct(a)}% a year, is statistically "
            f"indistinguishable from zero (t = {signed(t, '.2f')}) over {n} years"
        )
        share = factor_share(fit["excess_annual"], a)
        if share is not None:
            text += (
                f"; {signed(round(100 * share), 'd')}% of its return was factor exposure "
                "an index fund sells for a few basis points"
            )
        text += "."
    if robust is not None and _robustness_differs(fit, robust):
        text += (
            " With profitability and investment factors added, alpha is "
            f"{pct(robust['alpha_annual'])}% a year (t = {signed(robust['alpha_t'], '.2f')})."
        )
    return short, text


def model_verdict(ticker: str, kind: str, models: Mapping[str, Any]) -> tuple[str, str]:
    """:func:`verdict` from a fund record's ``models``.

    When the robustness fit is itself a Carhart fit (the offline sample has no RMW or CMA)
    there is no robustness sentence.
    """
    fit, robust = models[HEADLINE_MODEL], models[ROBUSTNESS_MODEL]
    return verdict(ticker, kind, fit, robust if robust["model"] != fit["model"] else None)


# -- the records ---------------------------------------------------------------------------
def fund_record(
    fund: Fund,
    headline: Attribution,
    robust: Attribution,
    roll: Mapping[str, Any],
    *,
    stale: bool = False,
) -> dict[str, Any]:
    """The full ``funds/<TICKER>.json`` record for a freshly fitted fund.

    ``headline`` is the Carhart fit and ``robust`` the robustness fit, both over the same
    window; ``roll`` is :func:`rolling` over the fund's longer history. When ``robust`` is
    itself a Carhart fit (the offline sample has no RMW or CMA), it is stored under the
    robustness key with its own model name and the verdict has no robustness sentence.
    """
    fit = model_fit(headline)
    robust_fit = model_fit(robust)
    models = {HEADLINE_MODEL: fit, ROBUSTNESS_MODEL: robust_fit}
    short, text = model_verdict(fund.ticker, fund.kind, models)
    win = window(headline)
    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": fund.ticker,
        "name": fund.name,
        "kind": fund.kind,
        "category": fund.category,
        "expense_ratio": num(fund.expense_ratio),
        "expense_ratio_as_of": fund.er_as_of,
        "expense_ratio_source": fund.er_source,
        "note": fund.note,
        "window": win,
        "short_history": win["months"] < WINDOW_MONTHS,
        "stale": stale,
        "excess_annual": fit["excess_annual"],
        "alpha_annual": fit["alpha_annual"],
        "alpha_t": fit["alpha_t"],
        "alpha_p": fit["alpha_p"],
        "r2": fit["r2"],
        "factor_share": factor_share(fit["excess_annual"], fit["alpha_annual"]),
        "verdict_short": short,
        "verdict": text,
        "models": models,
        "fee": fee(fit, fund.expense_ratio),
        "growth": growth(headline),
        "rolling": dict(roll),
    }


def summary(record: Mapping[str, Any]) -> dict[str, Any]:
    """The ``FundSummary`` that ``index.json`` lists: the headline fields of a fund record."""
    return {k: record[k] for k in SUMMARY_KEYS}
