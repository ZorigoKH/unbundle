import type { Metadata } from "next";
import Link from "next/link";

import { AlphaScatter, type ScatterPoint } from "@/components/charts/AlphaScatter";
import { FundTable } from "@/components/FundTable";
import { getFund, getIndex, getMeta } from "@/lib/data";
import { KIND_LABELS, PASSIVE_KINDS, modelLabel, month, share, spct } from "@/lib/format";

export function generateMetadata(): Metadata {
  const meta = getMeta();
  return {
    description:
      `For ${meta.funds} well-known equity funds and ETFs, how much of the last ` +
      `${meta.window_months / 12} years' return was cheap factor exposure and how much was ` +
      `alpha after fees. Data through ${month(meta.through)}.`,
  };
}

function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
}

export default function Home() {
  const meta = getMeta();
  const { funds } = getIndex();
  const years = meta.window_months / 12;

  const active = funds.filter((f) => !PASSIVE_KINDS.includes(f.kind));
  const tally = {
    skill: active.filter((f) => f.verdict_short === "skill").length,
    none: active.filter((f) => f.verdict_short === "no detectable alpha").length,
    trails: active.filter((f) => f.verdict_short === "trails its factors").length,
  };
  const medianShare = median(
    active.flatMap((f) => (f.factor_share === null ? [] : [f.factor_share])),
  );

  const points: ScatterPoint[] = funds.map((f) => {
    const [lo, hi] = getFund(f.ticker).fee.alpha_ci95;
    return {
      ticker: f.ticker,
      name: f.name,
      kind: KIND_LABELS[f.kind],
      active: !PASSIVE_KINDS.includes(f.kind),
      er: f.expense_ratio,
      alpha: f.alpha_annual,
      lo,
      hi,
      t: f.alpha_t,
    };
  });
  const byAlpha = [...points].sort((a, b) => a.alpha - b.alpha);
  const excludesZero = points.filter((p) => p.lo > 0 || p.hi < 0).length;
  const scatterLabel =
    `Scatter plot of expense ratio against Carhart alpha after fees for ${points.length} funds, ` +
    `with 95% intervals. Alphas run from ${spct(byAlpha[0]!.alpha)} a year ` +
    `(${byAlpha[0]!.ticker}) to ${spct(byAlpha.at(-1)!.alpha)} (${byAlpha.at(-1)!.ticker}); ` +
    `${excludesZero} of ${points.length} intervals exclude zero.`;

  return (
    <>
      <section className="pt-10 sm:pt-16">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">unbundle</h1>
        <p className="mt-5 max-w-3xl text-xl leading-snug sm:text-2xl">
          How much of a fund&rsquo;s return could you have bought for a few basis points?
        </p>
        <div className="mt-6 max-w-2xl space-y-4 text-muted">
          <p>
            Most of what a stock fund earns is exposure to a few well-known factors: the market
            as a whole, small companies, cheap &ldquo;value&rdquo; stocks and recent winners
            (momentum). Index funds sell market exposure for a few hundredths of a percent a
            year, and factor funds sell size, value and momentum tilts for a few tenths.
          </p>
          <p>
            What is left once that exposure is accounted for, after fees, is alpha: the only part
            worth paying an active manager for. For {meta.funds} well-known funds, this site
            splits the last {years} years of monthly returns into those two parts and asks
            whether the alpha is distinguishable from zero.{" "}
            <Link href="/method">How it works</Link>.
          </p>
        </div>
        <p className="mt-6 text-sm text-muted">
          data through {month(meta.through)} · {modelLabel(meta.headline_model)} model ·
          Newey–West standard errors · last {years} years
        </p>
      </section>

      <section aria-labelledby="tally" className="mt-14">
        <h2 id="tally" className="text-sm text-muted">
          the {active.length} actively managed portfolios, after fees
        </h2>
        <ul className="mt-4 grid grid-cols-1 border-y border-line sm:grid-cols-3">
          {[
            { n: tally.skill, label: "show skill", sub: "alpha t ≥ 2" },
            { n: tally.none, label: "no detectable alpha", sub: "−2 < t < 2" },
            { n: tally.trails, label: "trail their factors", sub: "alpha t ≤ −2" },
          ].map((s, i) => (
            <li
              key={s.label}
              className={`flex items-baseline gap-4 py-4 sm:block sm:px-5 sm:py-5 ${
                i > 0 ? "border-t border-line sm:border-t-0 sm:border-l" : "sm:pl-0"
              }`}
            >
              <span className="text-3xl sm:text-4xl">{s.n}</span>
              <span className="sm:mt-2 sm:block">
                {s.label} <span className="block text-xs text-muted">{s.sub}</span>
              </span>
            </li>
          ))}
        </ul>
        {medianShare !== null && (
          <p className="mt-4 max-w-2xl text-sm text-muted">
            For the median active portfolio, factor exposure explains{" "}
            <span className="num text-fg">{share(medianShare)}</span> of its return over
            T-bills. Above 100% means alpha after fees was negative.
          </p>
        )}
      </section>

      <section aria-labelledby="all-funds" className="mt-14">
        <h2 id="all-funds" className="text-lg font-medium">
          all funds
        </h2>
        <p className="mt-1 mb-5 max-w-2xl text-sm text-muted">
          Alpha after fees is the part of a fund&rsquo;s return over T-bills that the four
          factors do not explain, net of its expense ratio, in % a year. Pick a fund for the full
          breakdown.
        </p>
        <FundTable funds={funds} />
        <dl className="mt-5 grid max-w-3xl gap-3 text-xs text-muted sm:grid-cols-2">
          <div>
            <dt className="inline text-fg">t </dt>
            <dd className="inline">
              alpha divided by its Newey–West standard error; beyond ±2 is roughly significant at
              the 5% level.
            </dd>
          </div>
          <div>
            <dt className="inline text-fg">R² </dt>
            <dd className="inline">share of the monthly ups and downs the factors explain.</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="inline text-fg">factor share </dt>
            <dd className="inline">
              1 − alpha ÷ excess return: how much of the return over T-bills was factor exposure.
              Shown only when the fund beat T-bills by more than 1% a year.
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="fees-vs-alpha" className="mt-16">
        <h2 id="fees-vs-alpha" className="text-lg font-medium">
          fees versus alpha
        </h2>
        <p className="mt-1 mb-5 max-w-2xl text-sm text-muted">
          Each dot is a fund: what it charges against what it delivered beyond its factor
          exposure, after that charge. Vertical lines are 95% intervals; one that crosses zero
          means the alpha cannot be told apart from none at all. {excludesZero} of{" "}
          {points.length} intervals exclude zero.
        </p>
        <AlphaScatter points={points} label={scatterLabel} />
      </section>
    </>
  );
}
