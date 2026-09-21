"""Command line: ``unbundle demo``, ``unbundle fund SPY ARKK``, ``unbundle csv returns.csv``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import __version__
from .factors import FACTOR_SETS, SAMPLE_SOURCE, TEST_ASSETS, load_factors, load_sample
from .model import FactorModel, Results
from .pricing import alpha_test
from .report import html_report
from .returns import fetch_yahoo, read_returns_csv

INDUSTRY_NAMES = {
    "NoDur": "Consumer non-durables",
    "Durbl": "Consumer durables",
    "Manuf": "Manufacturing",
    "Enrgy": "Energy",
    "Chems": "Chemicals",
    "BusEq": "Business equipment",
    "Telcm": "Telecoms",
    "Utils": "Utilities",
    "Shops": "Retail",
    "Hlth": "Health care",
    "Money": "Finance",
    "Other": "Other",
}


def _m(x: float) -> str:
    return f"{x:+.2f}".replace("-", "−")


def _table(results: Results) -> str:
    factors = results.factors
    head = (
        f"{'':<22}{'months':>7}{'excess':>9}{'alpha':>9}{'t':>7}"
        + "".join(f"{('b_' + f):>9}" for f in factors)
        + f"{'R²':>7}"
    )
    lines = [head, "-" * len(head)]
    for name, a in results.items():
        lines.append(
            f"{name[:21]:<22}{a.nobs:>7}{100 * a.excess_annual:>8.2f}%{100 * a.alpha_annual:>8.2f}%"
            f"{a.alpha_t:>7.2f}" + "".join(f"{a.betas[f]:>9.2f}" for f in factors) + f"{a.r2:>7.2f}"
        )
    lines.append("excess and alpha are %/yr; t is Newey-West")
    return "\n".join(lines)


def _write_report(
    results: Results, path: str, *, window: int, source: str, title: str | None = None
) -> None:
    Path(path).write_text(
        html_report(results, window=window, source=source, title=title), encoding="utf-8"
    )
    print(f"\nreport written to {path}")


def cmd_demo(args: argparse.Namespace) -> int:
    data = load_sample().loc["1963-07":]
    rf = data["RF"]
    print("unbundle demo - Ken French data, Jul 1963 to Mar 2017 (bundled, no network)\n")
    print("1. Does each factor model price the classic test portfolios?")
    print("   GRS tests all alphas = 0 at once; mean |alpha| says how much is left over.\n")
    head = f"   {'test assets':<16}{'model':<9}{'GRS':>7}{'p':>10}{'mean |a|':>10}  largest |alpha|"
    print(head)
    print("   " + "-" * (len(head) - 3))
    for assets, cols in TEST_ASSETS.items():
        excess = data[list(cols)].sub(rf, axis=0)
        for model in ("capm", "ff3", "carhart"):
            factors = data[list(FACTOR_SETS[model])]
            t = alpha_test(excess, factors)
            worst, worst_alpha = t.max_abs_alpha
            print(
                f"   {assets:<16}{model:<9}{t.grs:>7.2f}{t.grs_pvalue:>10.1e}"
                f"{100 * t.mean_abs_alpha:>9.2f}%  {worst} {100 * worst_alpha:+.1f}%/yr"
            )
        print()
    print("2. Same return, different stories - Carhart attribution of three industries\n")
    picks = ["Enrgy", "BusEq", "Hlth"]
    frame = data[picks].rename(columns=INDUSTRY_NAMES)
    factors = load_factors("carhart", source="sample", start="1963-07")
    results = FactorModel(frame, factors, "carhart").fit()
    for a in results.values():
        print(a.summary(), "\n")
    if args.report:
        _write_report(
            results,
            args.report,
            window=60,
            source=f"Data: {SAMPLE_SOURCE}.",
            title="unbundle demo: three industries, 1963–2017",
        )
    return 0


def _fit_and_print(returns: pd.DataFrame, args: argparse.Namespace, source: str) -> int:
    factors = load_factors(args.model, start=args.start, end=args.end)
    results = FactorModel(returns, factors, args.model).fit()
    print(_table(results))
    for a in results.values():
        print("\n" + a.summary())
    if len(results) >= 2:
        common = results.excess.dropna()
        if len(common) > common.shape[1] + len(results.factors) + 1:
            print("\n", results.alpha_test(), sep="")
    if args.report:
        _write_report(results, args.report, window=args.window, source=source)
    return 0


def cmd_fund(args: argparse.Namespace) -> int:
    returns = fetch_yahoo(args.tickers, start=args.start, end=args.end)
    return _fit_and_print(
        returns,
        args,
        "Prices: Yahoo Finance, split- and dividend-adjusted. "
        "Factors: Kenneth R. French Data Library.",
    )


def cmd_csv(args: argparse.Namespace) -> int:
    returns = read_returns_csv(args.path, date_col=args.date_col, percent=args.percent)
    if args.start or args.end:
        returns = returns.loc[args.start : args.end]
    return _fit_and_print(returns, args, "Factors: Kenneth R. French Data Library.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="unbundle",
        description=(
            "Split a fund's returns into factor exposure you could buy cheaply "
            "and the alpha left over."
        ),
    )
    p.add_argument("--version", action="version", version=f"unbundle {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="offline demo on the bundled Ken French sample")
    demo.add_argument("--report", metavar="PATH", help="also write an HTML tearsheet")
    demo.set_defaults(func=cmd_demo)

    def common(q: argparse.ArgumentParser) -> None:
        q.add_argument(
            "--model",
            default="carhart",
            choices=sorted(FACTOR_SETS),
            help="factor model (default carhart)",
        )
        q.add_argument("--start", help="first month, e.g. 2015-01")
        q.add_argument("--end", help="last month, e.g. 2024-12")
        q.add_argument("--report", metavar="PATH", help="write an HTML tearsheet")
        q.add_argument(
            "--window", type=int, default=36, help="rolling window in months (default 36)"
        )

    fund = sub.add_parser(
        "fund", help="live: Yahoo prices + Ken French factors (needs unbundle[live])"
    )
    fund.add_argument("tickers", nargs="+", help="tickers, e.g. SPY ARKK BRK-B")
    common(fund)
    fund.set_defaults(func=cmd_fund)

    csv = sub.add_parser("csv", help="your own monthly returns from a CSV file")
    csv.add_argument(
        "path", help="CSV: a date column, then one column of monthly returns per asset"
    )
    csv.add_argument("--date-col", help="name of the date column (default: the first column)")
    csv.add_argument("--percent", action="store_true", help="returns are in percent, not decimals")
    common(csv)
    csv.set_defaults(func=cmd_csv)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, ImportError, OSError) as exc:
        print(f"unbundle: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
