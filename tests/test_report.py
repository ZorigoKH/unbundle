"""The HTML tearsheet: one file, no network, both themes."""

import re

import pytest

from unbundle import FactorModel, load_factors, plot
from unbundle.report import html_report


@pytest.fixture(scope="module")
def results(sample):
    factors = load_factors("carhart", source="sample")
    return FactorModel(sample[["Hlth", "Enrgy"]], factors, "carhart").fit()


def test_report_is_one_self_contained_file(results):
    page = html_report(results, source="Test data.")
    assert page.startswith("<!doctype html>")
    assert "<svg" in page and 'rect class="hover"' in page and "<script>" in page
    assert "Are all the alphas zero?" in page  # two assets: the joint test is shown
    urls = re.findall(r"(?:src|href)=[\"']?(https?://[^\"' >]+)", page)
    assert urls == []  # nothing loads from the network
    assert "Hlth" in page and "Enrgy" in page and "prefers-color-scheme:dark" in page


def test_theme_comes_from_the_chart_palettes(results):
    page = html_report(results)
    for pal in (plot.LIGHT, plot.DARK):
        assert f"--accent:{pal['accent']}" in page and f"--surface:{pal['surface']}" in page
    assert ':root[data-theme="dark"]' in page  # a page can also be pinned to one theme


def test_one_asset_skips_the_joint_test(sample):
    factors = load_factors("ff3", source="sample")
    one = FactorModel(sample[["Hlth"]], factors, "ff3").fit()
    page = html_report(one)
    assert "Are all the alphas zero?" not in page and "Summary" not in page
    assert "Hlth" in page
