"""Factor data: Ken French's data library, parsed, cached, and a bundled offline sample.

Every factor model here is a set of *traded* long-short portfolios, so a fund's
exposure to them is exposure you could have bought directly:

==========  ==========================================================
``capm``    MktRF
``ff3``     MktRF, SMB, HML                      (Fama & French 1993)
``carhart`` MktRF, SMB, HML, Mom                 (Carhart 1997)
``ff5``     MktRF, SMB, HML, RMW, CMA            (Fama & French 2015)
``ff5mom``  MktRF, SMB, HML, RMW, CMA, Mom
==========  ==========================================================

Returns are monthly, in decimals, on a ``PeriodIndex`` of monthly frequency. ``RF`` is
the one-month T-bill rate that turns total returns into excess returns.
"""

from __future__ import annotations

import gzip
import io
import os
import re
import time
import urllib.request
import zipfile
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

FACTOR_SETS: dict[str, tuple[str, ...]] = {
    "capm": ("MktRF",),
    "ff3": ("MktRF", "SMB", "HML"),
    "carhart": ("MktRF", "SMB", "HML", "Mom"),
    "ff5": ("MktRF", "SMB", "HML", "RMW", "CMA"),
    "ff5mom": ("MktRF", "SMB", "HML", "RMW", "CMA", "Mom"),
}

FACTOR_LABELS = {
    "MktRF": "Market",
    "SMB": "Size",
    "HML": "Value",
    "RMW": "Profitability",
    "CMA": "Investment",
    "Mom": "Momentum",
}

FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FRENCH_FILES = {
    "ff3": "F-F_Research_Data_Factors_CSV.zip",
    "ff5": "F-F_Research_Data_5_Factors_2x3_CSV.zip",
    "mom": "F-F_Momentum_Factor_CSV.zip",
}

SAMPLE_SOURCE = (
    "Kenneth R. French Data Library, monthly, Jan 1949 - Mar 2017 "
    "(the snapshot distributed with linearmodels)"
)

TEST_ASSETS: dict[str, tuple[str, ...]] = {
    "size-value": ("S1V1", "S1V3", "S1V5", "S3V1", "S3V3", "S3V5", "S5V1", "S5V3", "S5V5"),
    "size-momentum": ("S1M1", "S1M3", "S1M5", "S3M1", "S3M3", "S3M5", "S5M1", "S5M3", "S5M5"),
    "industries": (
        "NoDur",
        "Durbl",
        "Manuf",
        "Enrgy",
        "Chems",
        "BusEq",
        "Telcm",
        "Utils",
        "Shops",
        "Hlth",
        "Money",
        "Other",
    ),
}

_MISSING = (-99.99, -999.0)
_YYYYMM = re.compile(r"^\d{6}$")


def resolve_model(model: str) -> tuple[str, ...]:
    """The factor names of a model, e.g. ``"carhart"`` -> ``("MktRF", "SMB", "HML", "Mom")``."""
    key = model.lower().replace("-", "").replace("_", "")
    if key not in FACTOR_SETS:
        raise ValueError(f"unknown model {model!r}; choose from {', '.join(FACTOR_SETS)}")
    return FACTOR_SETS[key]


def parse_french_csv(text: str) -> pd.DataFrame:
    """Parse the monthly block of a Ken French data library CSV.

    The files open with free-text lines, then a header row that starts with a comma
    (``,Mkt-RF,SMB,HML,RF``), then one row per month keyed ``YYYYMM``. An annual block
    follows after a blank line and is ignored. Values are percentages; missing values are
    coded -99.99 or -999. Returns decimals on a monthly ``PeriodIndex``, with ``Mkt-RF``
    renamed ``MktRF``.
    """
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().startswith(","))
    except StopIteration:
        raise ValueError("no header row found: not a Ken French data library CSV") from None
    names = [c.strip().replace("-", "") for c in lines[start].split(",")[1:]]
    months, values = [], []
    for line in lines[start + 1 :]:
        cells = [c.strip() for c in line.split(",")]
        if not cells or not _YYYYMM.match(cells[0]):
            break
        months.append(f"{cells[0][:4]}-{cells[0][4:]}")
        values.append([float(v) for v in cells[1 : len(names) + 1]])
    if not months:
        raise ValueError("header found but no monthly rows followed it")
    frame = pd.DataFrame(values, columns=names, index=pd.PeriodIndex(months, freq="M"))
    frame = frame.mask(frame.isin(_MISSING)) / 100.0
    frame.index.name = "month"
    return frame


def _cache_dir(cache_dir: str | os.PathLike | None) -> Path:
    if cache_dir is not None:
        path = Path(cache_dir)
    else:
        path = Path(os.environ.get("UNBUNDLE_CACHE", Path.home() / ".cache" / "unbundle"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _download(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "unbundle (+python urllib)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_french(
    name: str,
    *,
    cache_dir: str | os.PathLike | None = None,
    max_age_days: float = 7.0,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """Download one Ken French file (``"ff3"``, ``"ff5"`` or ``"mom"``), parse it, cache it.

    The parsed table is cached as CSV under ``~/.cache/unbundle`` (override with
    ``cache_dir`` or ``$UNBUNDLE_CACHE``) and reused for ``max_age_days``; the library
    updates monthly.
    """
    if name not in FRENCH_FILES:
        raise ValueError(f"unknown Ken French file {name!r}; choose from {', '.join(FRENCH_FILES)}")
    cached = _cache_dir(cache_dir) / f"french_{name}.csv"
    if cached.exists() and time.time() - cached.stat().st_mtime < max_age_days * 86400:
        frame = pd.read_csv(cached, index_col=0)
        frame.index = pd.PeriodIndex(frame.index, freq="M", name="month")
        return frame
    raw = _download(FRENCH_URL + FRENCH_FILES[name], timeout)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            member = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
            text = archive.read(member).decode("latin-1")
    except (zipfile.BadZipFile, StopIteration) as exc:  # e.g. an HTML error page
        raise RuntimeError(f"{FRENCH_FILES[name]} did not arrive as a zipped CSV") from exc
    frame = parse_french_csv(text)
    out = frame.copy()
    out.index = out.index.astype(str)
    out.to_csv(cached)
    return frame


def load_sample() -> pd.DataFrame:
    """The bundled offline sample: Jan 1949 - Mar 2017, monthly, decimals.

    Columns: the factors ``MktRF, SMB, HML, Mom, RF``; 12 industry portfolios; 9 portfolios
    sorted on size and book-to-market (``S1V1`` small growth ... ``S5V5`` big value); 9
    sorted on size and prior return (``S1M1`` small losers ... ``S5M5`` big winners).
    Portfolio returns are total returns - subtract ``RF`` for excess returns.
    Source: Kenneth R. French Data Library.
    """
    with resources.files("unbundle").joinpath("data/french_sample.csv.gz").open("rb") as fh:
        frame = pd.read_csv(io.BytesIO(gzip.decompress(fh.read())))
    frame.index = pd.PeriodIndex(frame.pop("month"), freq="M", name="month")
    return frame


def load_factors(
    model: str = "carhart",
    *,
    start: str | None = None,
    end: str | None = None,
    source: str = "french",
    cache_dir: str | os.PathLike | None = None,
) -> pd.DataFrame:
    """Monthly factor returns for ``model`` plus ``RF``, in decimals.

    ``source="french"`` downloads (and caches) the current Ken French files;
    ``source="sample"`` uses the bundled 1949-2017 snapshot, which has no RMW/CMA.
    """
    names = resolve_model(model)
    if source == "sample":
        frame = load_sample()
        missing = [n for n in names if n not in frame.columns]
        if missing:
            raise ValueError(
                f"the bundled sample has no {', '.join(missing)}; use source='french' for {model}"
            )
    elif source == "french":
        needs_five = any(n in ("RMW", "CMA") for n in names)
        frame = fetch_french("ff5" if needs_five else "ff3", cache_dir=cache_dir)
        if "Mom" in names:
            frame = frame.join(fetch_french("mom", cache_dir=cache_dir), how="inner")
    else:
        raise ValueError("source must be 'french' or 'sample'")
    out = frame.loc[:, [*names, "RF"]]
    out = out.loc[start:end] if (start or end) else out
    return out.dropna()


def annualize(monthly: float | np.ndarray | pd.Series) -> float | np.ndarray | pd.Series:
    """Monthly arithmetic mean to annual: x 12."""
    return monthly * 12
