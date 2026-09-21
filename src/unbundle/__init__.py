"""unbundle: split a fund's returns into cheap factor exposure and the alpha you pay for."""

from .factors import (
    FACTOR_LABELS,
    FACTOR_SETS,
    TEST_ASSETS,
    fetch_french,
    load_factors,
    load_sample,
    parse_french_csv,
    resolve_model,
)
from .model import Attribution, FactorModel, Results, newey_west_lags
from .pricing import AlphaTest, alpha_test, grs_test, hac_wald
from .returns import excess_returns, fetch_yahoo, prices_to_returns, read_returns_csv

__version__ = "0.1.0"
__all__ = [
    "FACTOR_LABELS",
    "FACTOR_SETS",
    "TEST_ASSETS",
    "AlphaTest",
    "Attribution",
    "FactorModel",
    "Results",
    "alpha_test",
    "excess_returns",
    "fetch_french",
    "fetch_yahoo",
    "grs_test",
    "hac_wald",
    "load_factors",
    "load_sample",
    "newey_west_lags",
    "parse_french_csv",
    "prices_to_returns",
    "read_returns_csv",
    "resolve_model",
]
