"""The SVG charts: well-formed, themed, one mark per number."""

import xml.etree.ElementTree as ET

import pytest

from unbundle import FactorModel, load_factors, plot


@pytest.fixture(scope="module")
def results(sample):
    factors = load_factors("carhart", source="sample")
    return FactorModel(sample[["Hlth", "Enrgy"]], factors, "carhart").fit()


def test_standalone_svgs_are_well_formed(results):
    a = results["Hlth"]
    roll = results.rolling("Hlth", window=36)
    for pal in (plot.LIGHT, plot.DARK):
        for svg in (
            plot.attribution_svg([a, results["Enrgy"]], pal=pal, heading="t"),
            plot.growth_svg(a, pal=pal, heading="t"),
            plot.rolling_svg(roll, a.factors, pal=pal),
        ):
            root = ET.fromstring(svg)
            assert root.tag.endswith("svg")
            assert pal["accent"] in svg and "var(--" not in svg


def test_attribution_draws_one_bar_per_component(results):
    svg = plot.attribution_svg(results["Hlth"], pal=plot.LIGHT)
    assert svg.count('class="mark"') == len(results["Hlth"].factors) + 1
    assert "Alpha: +4.36%/yr" in svg  # the tooltip carries the exact value


def test_tick_helpers_cover_the_data():
    ticks = plot.nice_ticks(-1.3, 1.3, 3)
    assert ticks[0] <= -1.3 and ticks[-1] >= 1.3
    flat = plot.nice_ticks(0, 0)  # a constant series still gets a usable axis
    assert flat[0] <= 0 and flat[-1] >= 1 and len(flat) >= 2
    logs = plot.log_ticks(0.9, 480)
    assert logs[0] >= 0.9 and logs[-1] <= 480 and len(logs) >= 3
