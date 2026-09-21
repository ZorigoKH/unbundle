import io
import zipfile

import numpy as np
import pandas as pd
import pytest
from linearmodels.datasets import french

import unbundle.factors as factors_mod
from unbundle import FACTOR_SETS, load_factors, load_sample, parse_french_csv, resolve_model
from unbundle.factors import fetch_french


def test_parses_the_monthly_block_and_ignores_the_rest(fixture_text):
    frame = parse_french_csv(fixture_text("F-F_Research_Data_Factors.CSV"))
    assert list(frame.columns) == ["MktRF", "SMB", "HML", "RF"]
    assert isinstance(frame.index, pd.PeriodIndex) and frame.index.freqstr == "M"
    assert frame.index[0] == pd.Period("2024-01", "M") and len(frame) == 6  # annual block ignored
    np.testing.assert_allclose(frame.loc["2024-01"].to_numpy(), [0.01, -0.02, 0.03, 0.004])
    np.testing.assert_allclose(frame.loc["2024-02", "HML"], -0.0125)
    assert frame.loc["2024-03", "HML"] == 0.0
    assert np.isnan(frame.loc["2024-04", "SMB"])  # -99.99 is missing, not -100%


def test_momentum_file_with_padded_header_and_minus_999(fixture_text):
    frame = parse_french_csv(fixture_text("F-F_Momentum_Factor.CSV"))
    assert list(frame.columns) == ["Mom"]  # ",Mom   " stripped
    assert frame.index[0] == pd.Period("2024-02", "M") and len(frame) == 6
    assert np.isnan(frame.loc["2024-04", "Mom"])
    np.testing.assert_allclose(frame.loc["2024-03", "Mom"], -0.0225)


def test_rejects_files_that_are_not_ken_french_csvs():
    with pytest.raises(ValueError, match="no header row"):
        parse_french_csv("just some text\nwith no header\n")
    with pytest.raises(ValueError, match="no monthly rows"):
        parse_french_csv("title\n\n,Mkt-RF,RF\n\nAnnual\n")


def _zipped(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, text)
    return buf.getvalue()


def test_fetch_downloads_once_then_reads_the_cache(tmp_path, monkeypatch, fixture_text):
    calls = []
    payload = _zipped(
        "F-F_Research_Data_Factors.CSV", fixture_text("F-F_Research_Data_Factors.CSV")
    )

    def fake_download(url, timeout):
        calls.append(url)
        return payload

    monkeypatch.setattr(factors_mod, "_download", fake_download)
    first = fetch_french("ff3", cache_dir=tmp_path)
    second = fetch_french("ff3", cache_dir=tmp_path)
    assert len(calls) == 1 and calls[0].endswith("F-F_Research_Data_Factors_CSV.zip")
    pd.testing.assert_frame_equal(first, second)
    assert (tmp_path / "french_ff3.csv").exists()
    fetch_french("ff3", cache_dir=tmp_path, max_age_days=0)  # stale cache -> download again
    assert len(calls) == 2
    with pytest.raises(ValueError, match="unknown Ken French file"):
        fetch_french("ff7", cache_dir=tmp_path)


def test_load_factors_from_french_joins_momentum(tmp_path, monkeypatch, fixture_text):
    files = {
        "F-F_Research_Data_Factors_CSV.zip": (
            "F-F_Research_Data_Factors.CSV",
            "F-F_Research_Data_Factors.CSV",
        ),
        "F-F_Momentum_Factor_CSV.zip": ("F-F_Momentum_Factor.CSV", "F-F_Momentum_Factor.CSV"),
    }

    def fake_download(url, timeout):
        member, fixture = files[url.rsplit("/", 1)[1]]
        return _zipped(member, fixture_text(fixture))

    monkeypatch.setattr(factors_mod, "_download", fake_download)
    monkeypatch.setenv("UNBUNDLE_CACHE", str(tmp_path))
    frame = load_factors("carhart", source="french")
    assert list(frame.columns) == ["MktRF", "SMB", "HML", "Mom", "RF"]
    # inner join on months both files have, and months with a missing value dropped
    assert [str(p) for p in frame.index] == ["2024-02", "2024-03", "2024-05", "2024-06"]
    assert list(load_factors("carhart", source="french", start="2024-05").index.astype(str)) == [
        "2024-05",
        "2024-06",
    ]


def test_bundled_sample_is_the_linearmodels_snapshot_exactly():
    ours = load_sample()
    ref = french.load()
    assert ours.shape == (819, 35)
    assert str(ours.index[0]) == "1949-01" and str(ours.index[-1]) == "2017-03"
    ref_values = ref.drop(columns=["dates"])[ours.columns].to_numpy()
    np.testing.assert_allclose(ours.to_numpy(), ref_values, rtol=1e-5, atol=1e-8)


def test_sample_factors_and_model_names():
    frame = load_factors("carhart", source="sample", start="1963-07", end="1963-12")
    assert list(frame.columns) == ["MktRF", "SMB", "HML", "Mom", "RF"] and len(frame) == 6
    assert resolve_model("FF-3") == FACTOR_SETS["ff3"] == ("MktRF", "SMB", "HML")
    with pytest.raises(ValueError, match="no RMW, CMA"):
        load_factors("ff5", source="sample")
    with pytest.raises(ValueError, match="unknown model"):
        resolve_model("apt")
    with pytest.raises(ValueError, match="source must be"):
        load_factors("capm", source="bloomberg")


def test_a_page_that_is_not_a_zip_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(factors_mod, "_download", lambda url, timeout: b"<html>busy</html>")
    with pytest.raises(RuntimeError, match="did not arrive as a zipped CSV"):
        fetch_french("ff3", cache_dir=tmp_path)
