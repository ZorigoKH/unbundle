"""Regenerate the README figures in docs/ from the bundled data.

    python scripts/figures.py

Each chart is written twice, for GitHub's light and dark themes; the README picks one with
<picture>. The numbers in the titles are asserted here, so a figure can't drift from the
data it claims to show.
"""

from pathlib import Path

from unbundle import FactorModel, load_factors, load_sample, plot

DOCS = Path(__file__).resolve().parent.parent / "docs"
NAMES = {"Enrgy": "Energy", "BusEq": "Business equipment", "Hlth": "Health care"}


def main() -> None:
    data = load_sample().loc["1963-07":, list(NAMES)].rename(columns=NAMES)
    factors = load_factors("carhart", source="sample", start="1963-07")
    res = FactorModel(data, factors, "carhart").fit()

    energy, tech, health = res["Energy"], res["Business equipment"], res["Health care"]
    assert round(100 * energy.excess_annual, 1) == round(100 * tech.excess_annual, 1) == 7.3
    grown = (1 + health.excess + health.rf).prod()
    replica = (1 + health.replicating + health.rf).prod()
    assert (round(grown), round(replica)) == (470, 60)

    DOCS.mkdir(exist_ok=True)
    for mode, pal in (("light", plot.LIGHT), ("dark", plot.DARK)):
        figures = {
            "attribution": plot.attribution_svg(
                [energy, tech],
                pal=pal,
                heading="Same 7.3% a year. Only one of them had alpha.",
            ),
            "growth": plot.growth_svg(
                health,
                pal=pal,
                heading="$1 in health care grew to $470. Its factor exposure alone: $60.",
            ),
        }
        for name, svg in figures.items():
            path = DOCS / f"{name}-{mode}.svg"
            path.write_text(svg + "\n", encoding="utf-8")
            print(f"wrote {path.relative_to(DOCS.parent)}")


if __name__ == "__main__":
    main()
