import type { Metadata } from "next";
import Link from "next/link";

import { AttributionChart, type AttributionRow } from "@/components/charts/AttributionChart";
import { FeeStrip } from "@/components/charts/FeeStrip";
import { GrowthChart } from "@/components/charts/GrowthChart";
import { RollingPanels, type RollingSeries } from "@/components/charts/RollingPanels";
import { ModelTable } from "@/components/ModelTable";
import { getFund, getMeta, getTickers } from "@/lib/data";
import {
  KIND_LABELS,
  PASSIVE_KINDS,
  date,
  dec,
  dollars,
  er,
  factorLabel,
  modelLabel,
  month,
  monthIndex,
  pct,
  pval,
  showsPositive,
  spct,
  tstat,
  windowLabel,
  years,
} from "@/lib/format";
import { type Fund, ROLLING_FACTORS } from "@/lib/types";

export const dynamicParams = false;

export function generateStaticParams() {
  return getTickers().map((ticker) => ({ ticker }));
}

export async function generateMetadata(props: PageProps<"/fund/[ticker]">): Promise<Metadata> {
  const { ticker } = await props.params;
  const f = getFund(decodeURIComponent(ticker));
  return {
    title: `${f.ticker} · ${f.name}`,
    description: f.verdict,
  };
}

function Section({
  id,
  title,
  intro,
  children,
}: {
  id: string;
  title: string;
  intro?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mt-16">
      <h2 id={id} className="text-lg font-medium">
        {title}
      </h2>
      {intro && <p className="mt-1 max-w-2xl text-sm text-muted">{intro}</p>}
      <div className={intro ? "mt-6" : "mt-3"}>{children}</div>
    </section>
  );
}

function Tile({ label, value, sub, accent }: {
  label: string;
  value: string;
  sub: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="border-b border-line py-4 last:border-b-0 sm:border-b-0 sm:border-l sm:px-5 sm:first:border-l-0 sm:first:pl-0">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-2xl sm:text-3xl ${accent ? "text-accent-ink" : ""}`}>{value}</p>
      <p className="mt-1 text-xs text-muted">{sub}</p>
    </div>
  );
}

function robustness(f: Fund, robustModel: string): React.ReactNode {
  const c = f.models.carhart;
  const r = f.models.ff5mom;
  if (robustModel !== "ff5mom" || r.model !== "ff5mom") {
    return "The six-factor robustness fit is not available in this build of the data.";
  }
  const crosses = Math.abs(c.alpha_t) >= 2 !== Math.abs(r.alpha_t) >= 2;
  const flips = Math.sign(c.alpha_annual) !== Math.sign(r.alpha_annual);
  const conclusion = crosses
    ? "Whether the alpha is statistically significant depends on the model."
    : flips && Math.abs(c.alpha_t) < 2
      ? "The sign flips, but neither estimate is distinguishable from zero."
      : flips
        ? "The sign of the alpha depends on the model."
        : "The conclusion does not change.";
  return (
    <>
      With the profitability and investment factors added ({modelLabel("ff5mom")}), alpha after
      fees is <span className="num text-fg">{spct(r.alpha_annual)}</span> a year (t ={" "}
      <span className="num">{tstat(r.alpha_t)}</span>, R² {dec(r.r2)}), against{" "}
      <span className="num text-fg">{spct(c.alpha_annual)}</span> (t = {tstat(c.alpha_t)}, R²{" "}
      {dec(c.r2)}) with the Carhart model. {conclusion}
    </>
  );
}

function feeNote(f: Fund): string {
  const { breakeven_fee: b, expense_ratio: fee, alpha_net: net } = f.fee;
  // Two decimals throughout, like the break-even fee: these gaps are often a few hundredths.
  const two = (x: number) => pct(x, { digits: 2 });
  const passive = PASSIVE_KINDS.includes(f.kind);
  const lead = passive
    ? `For an index, factor or sector fund, “alpha” measures how its holdings differed from ` +
      `the four-factor model, not a manager's skill. `
    : "";
  if (fee === 0) {
    return (
      lead +
      `${f.ticker} charges no expense ratio (its costs are already inside its returns), so ` +
      `alpha before and after fees is the same ${spct(net, 2)} a year.`
    );
  }
  if (b <= 0) {
    return (
      lead +
      `Break-even fee: none. Even at a fee of zero, ${f.ticker} would have trailed T-bills ` +
      `plus the same factor exposure by ${two(Math.abs(b))} a year; its ${er(fee)} fee ` +
      `widened the gap to ${two(Math.abs(net))}.`
    );
  }
  const behind = two(Math.abs(net));
  const verdict =
    b > fee
      ? `The fee took ${pct(fee / b, { digits: 0 })} of the value added; investors kept ` +
        `${spct(net, 2)} a year.`
      : Number(behind.slice(0, -1)) === 0
        ? "The fee about equalled the value added, so investors came out roughly even."
        : `The fee was larger than the value added, so investors ended up ${behind} a year ` +
          "behind.";
  return (
    lead +
    `Break-even fee: ${two(b)} a year, the fee at which investors would have done ` +
    `exactly as well as with T-bills plus the same factor exposure. ${f.ticker} charges ` +
    `${er(fee)}. ${verdict}`
  );
}

function sentence(s: string): string {
  const t = s.trim();
  if (!t) return t;
  const cap = t[0]!.toUpperCase() + t.slice(1);
  return /[.!?]$/.test(cap) ? cap : `${cap}.`;
}

function isUrl(src: string): boolean {
  return /^https?:\/\//.test(src);
}

function sourceLink(src: string) {
  if (!isUrl(src)) return src;
  return <a href={src}>{new URL(src).hostname.replace(/^www\./, "")}</a>;
}

export default async function FundPage(props: PageProps<"/fund/[ticker]">) {
  const { ticker } = await props.params;
  const f = getFund(decodeURIComponent(ticker));
  const meta = getMeta();
  const c = f.models.carhart;
  const [lo, hi] = f.fee.alpha_ci95;
  const last = f.growth.fund.length - 1;

  const attribution: AttributionRow[] = [
    ...c.factors.map((k) => ({
      key: k,
      label: factorLabel(k),
      beta: c.betas[k]!.coef,
      value: c.contributions[k]!,
    })),
    { key: "alpha", label: "alpha", value: c.contributions.alpha! },
  ];
  const attributionLabel =
    `Attribution of ${f.ticker}'s ${spct(c.excess_annual)} a year over T-bills: ` +
    attribution.map((r) => `${r.label} ${spct(r.value)}`).join(", ") +
    ".";

  const g = f.growth;
  const growthLabel =
    `Growth of $1 from ${month(g.months[0]!)} to ${month(g.months[last]!)}, log scale: ` +
    `${f.ticker} ${dollars(g.fund[last]!)}, T-bills plus the same factor exposure ` +
    `${dollars(g.replica[last]!)}, T-bills ${dollars(g.tbills[last]!)}.`;

  const feeLabel =
    `Before fees ${f.ticker} added ${spct(f.fee.alpha_gross)} a year beyond its factor ` +
    `exposure; the fee was ${er(f.fee.expense_ratio)}; after fees alpha is ` +
    `${spct(f.fee.alpha_net)} with a 95% interval of ${spct(lo)} to ${spct(hi)}.`;

  const r = f.rolling;
  // The panels show at most two decimals; four keep the lines exact and the page lighter.
  const round4 = (xs: number[]) => xs.map((v) => Math.round(v * 1e4) / 1e4);
  const rolling: RollingSeries[] = [
    {
      key: "alpha",
      title: "alpha",
      values: round4(r.alpha_annual),
      reference: 0,
      format: "pct",
      color: "var(--accent)",
    },
    ...ROLLING_FACTORS.map((k) => ({
      key: k,
      title: `${factorLabel(k)} β`,
      values: round4(r.betas[k]),
      reference: k === "MktRF" ? 1 : 0,
      format: "num" as const,
      color: "var(--context)",
    })),
    {
      key: "r2",
      title: "R²",
      values: round4(r.r2),
      reference: null,
      format: "num",
      color: "var(--context)",
    },
  ];
  const yearEnds = r.months
    .map((m, i) => ({ m, i }))
    .filter(({ m, i }) => m.endsWith("-12") || i === r.months.length - 1);

  const short = f.short_history;
  const passive = PASSIVE_KINDS.includes(f.kind);

  return (
    <article>
      <nav className="pt-6 text-sm">
        <Link href="/">← all funds</Link>
      </nav>

      <header className="mt-8">
        <p className="text-sm text-muted">
          {KIND_LABELS[f.kind]} · {f.category}
        </p>
        <h1 className="mt-1 text-3xl font-medium tracking-tight sm:text-4xl">{f.ticker}</h1>
        <p className="mt-1 text-lg">{f.name}</p>
        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-muted">
          <span className="num">{windowLabel(f.window)}</span>
          <span aria-hidden="true">·</span>
          <span>
            expense ratio <span className="num text-fg">{er(f.expense_ratio)}</span>
          </span>
          {short && (
            <span className="border border-line px-2 py-0.5 text-xs text-fg">short history</span>
          )}
          {f.stale && <span className="border border-fg px-2 py-0.5 text-xs text-fg">stale</span>}
        </p>
      </header>

      <p className="mt-10 text-xs text-muted">verdict · {f.verdict_short}</p>
      <p className="mt-2 max-w-3xl text-xl leading-snug sm:text-2xl">{f.verdict}</p>

      <div className="mt-10 grid grid-cols-1 border-y border-line sm:grid-cols-4">
        <Tile
          label="return over T-bills"
          value={spct(f.excess_annual)}
          sub={`a year, ${years(f.window.months)} years`}
        />
        <Tile
          label="alpha after fees"
          value={spct(f.alpha_annual)}
          sub={`95%: ${spct(lo)} to ${spct(hi)}`}
          accent={showsPositive(f.alpha_annual)}
        />
        <Tile
          label="t-stat"
          value={tstat(f.alpha_t)}
          sub={`p = ${pval(f.alpha_p)} · Newey–West, ${c.maxlags} lags`}
        />
        <Tile label="R²" value={dec(f.r2)} sub="of monthly variance explained by factors" />
      </div>

      <Section
        id="attribution"
        title="where the return came from"
        intro={
          <>
            {f.ticker}&rsquo;s average return over T-bills, split by the Carhart model. Each
            factor&rsquo;s share is its loading (β) times that factor&rsquo;s average return over
            the window; alpha is what is left, after fees. In % a year.
          </>
        }
      >
        <AttributionChart rows={attribution} excess={c.excess_annual} label={attributionLabel} />
      </Section>

      <Section
        id="growth"
        title="growth of $1"
        intro={
          <>
            What $1 became over the window (log scale), next to T-bills plus the same factor
            exposure: the fund&rsquo;s own betas applied to the factor returns, with no alpha
            and no fee. The gap between the lines is alpha plus month-to-month noise,
            compounded, so it need not match the annual alpha exactly.
          </>
        }
      >
        <GrowthChart growth={g} ticker={f.ticker} label={growthLabel} />
        <p className="mt-4 text-sm text-muted">
          $1 in {month(g.months[0]!)} became{" "}
          <span className="num text-fg">{dollars(g.fund[last]!)}</span> in {f.ticker},{" "}
          <span className="num text-fg">{dollars(g.replica[last]!)}</span> with T-bills plus the
          same factor exposure, and <span className="num text-fg">{dollars(g.tbills[last]!)}</span>{" "}
          in T-bills by {month(g.months[last]!)}.
        </p>
      </Section>

      <Section
        id="fee"
        title="the fee and the alpha"
        intro={
          <>
            Returns are measured after the fund&rsquo;s fees, so adding the expense ratio back
            gives what the {passive ? "fund" : "manager"} added before charging for it.
          </>
        }
      >
        <FeeStrip
          gross={f.fee.alpha_gross}
          fee={f.fee.expense_ratio}
          net={f.fee.alpha_net}
          ci={f.fee.alpha_ci95}
          label={feeLabel}
        />
        <p className="mt-4 text-sm text-muted">
          95% interval for alpha after fees: <span className="num text-fg">{spct(lo)}</span> to{" "}
          <span className="num text-fg">{spct(hi)}</span> a year.
        </p>
        <p className="mt-2 max-w-3xl text-sm">{feeNote(f)}</p>
      </Section>

      <Section
        id="rolling"
        title={`rolling ${r.window}-month exposures`}
        intro={
          <>
            Each point is a Carhart fit on the {r.window} months ending that month, from{" "}
            {month(r.months[0]!)} (the first full window since 1990 or since the fund started).
            The shaded span is the {f.window.months}-month window used above. Hover or tap to read
            a month.
          </>
        }
      >
        <RollingPanels
          months={r.months}
          series={rolling}
          window={{ start: f.window.start, end: f.window.end }}
          label={`Rolling ${r.window}-month Carhart fits for ${f.ticker}`}
        />
        <details className="mt-6 text-sm">
          <summary className="cursor-pointer text-muted hover:text-fg">
            rolling numbers, one row per year
          </summary>
          <div className="table-scroll mt-3 border-y border-line">
            <table className="w-full min-w-[36rem] border-collapse">
              <caption className="sr-only">
                Rolling {r.window}-month Carhart estimates at each year end and the latest month.
              </caption>
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th scope="col" className="py-2 pr-2 text-left font-normal">
                    36 months to
                  </th>
                  {rolling.map((s) => (
                    <th key={s.key} scope="col" className="px-2 py-2 text-right font-normal">
                      {s.key === "alpha" ? "alpha %/yr" : s.title}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {yearEnds.map(({ m, i }) => (
                  <tr key={m} className="border-b border-line last:border-b-0">
                    <th scope="row" className="num py-1 pr-2 text-left font-normal">
                      {month(m)}
                    </th>
                    {rolling.map((s) => (
                      <td key={s.key} className="num px-2 py-1 text-right">
                        {s.format === "pct" ? spct(s.values[i]!) : dec(s.values[i]!)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Section>

      <Section id="robustness" title="robustness">
        <p className="max-w-3xl text-muted">{robustness(f, meta.robustness_model)}</p>
      </Section>

      <Section
        id="numbers"
        title="the numbers"
        intro="Both fits over the same window. Standard errors are Newey–West (heteroskedasticity and autocorrelation robust); premia and contributions are annualized means."
      >
        <div className="grid grid-cols-1 gap-10">
          <ModelTable fit={f.models.carhart} headline />
          <ModelTable fit={f.models.ff5mom} headline={false} />
        </div>
      </Section>

      <Section id="notes" title="notes">
        <ul className="max-w-3xl list-disc space-y-2 pl-5 text-sm text-muted marker:text-line">
          {f.note && <li>{sentence(f.note)}</li>}
          {f.expense_ratio === 0 && !isUrl(f.expense_ratio_source) ? (
            <li>No expense ratio: its operating costs are already inside its returns.</li>
          ) : (
            <li>
              Expense ratio {er(f.expense_ratio)} (net), as of{" "}
              {/^\d{4}-\d{2}-\d{2}$/.test(f.expense_ratio_as_of)
                ? date(f.expense_ratio_as_of)
                : f.expense_ratio_as_of}
              ; source: {sourceLink(f.expense_ratio_source)}.
            </li>
          )}
          {short && (
            <li>
              Short history: {f.window.months} months in the window instead of{" "}
              {meta.window_months} (the site uses a shorter window only when there are at least{" "}
              {meta.min_months}), so these estimates are noisier.
            </li>
          )}
          {f.stale && (
            <li>
              Stale: the latest data refresh could not update {f.ticker}, so these figures come
              from an earlier build.
            </li>
          )}
          {monthIndex(f.window.end) < monthIndex(meta.through) && (
            <li>
              The window ends in {month(f.window.end)}, before the site&rsquo;s{" "}
              {month(meta.through)}.
            </li>
          )}
          <li>
            Returns are monthly total returns from Yahoo Finance adjusted closes, which are net of
            the fund&rsquo;s expenses. See the <Link href="/method">method</Link> for how the
            numbers are made and what they cannot tell you.
          </li>
        </ul>
      </Section>

      <nav className="mt-16 text-sm">
        <Link href="/">← all funds</Link>
      </nav>
    </article>
  );
}
