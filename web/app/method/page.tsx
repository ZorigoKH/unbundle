import type { Metadata } from "next";
import Link from "next/link";

import { getMeta } from "@/lib/data";
import { month } from "@/lib/format";
import { REPO_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "method",
  description:
    "How unbundle live splits a fund's return into factor exposure and alpha after fees, and " +
    "what the numbers cannot tell you.",
};

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="mt-14 scroll-mt-6 text-lg font-medium">
      {children}
    </h2>
  );
}

const CONTENTS = [
  ["regression", "the regression"],
  ["attribution", "the attribution identity"],
  ["newey-west", "standard errors"],
  ["why-carhart", "why Carhart"],
  ["fees", "fees, gross alpha and the break-even fee"],
  ["replica", "the replica is not literally free"],
  ["selection", "selection bias"],
  ["data", "data caveats"],
  ["sources", "sources and licensing"],
  ["updates", "update schedule and checks"],
] as const;

export default function Method() {
  const meta = getMeta();
  const years = meta.window_months / 12;
  return (
    <article className="max-w-3xl">
      <header className="pt-10 sm:pt-16">
        <h1 className="text-3xl font-medium tracking-tight sm:text-4xl">method</h1>
        <p className="mt-5 text-lg leading-snug sm:text-xl">
          How the numbers are made, in plain English, and what they cannot tell you.
        </p>
      </header>

      <nav aria-label="contents" className="mt-8 text-sm">
        <ol className="list-decimal space-y-1 pl-7 text-muted marker:text-line">
          {CONTENTS.map(([id, label]) => (
            <li key={id}>
              <a href={`#${id}`}>{label}</a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="space-y-4 [&_p]:leading-relaxed">
        <H2 id="regression">the regression</H2>
        <p>
          For each fund, take its monthly total return, subtract the one-month T-bill rate, and
          regress that excess return on the monthly returns of four factor portfolios from the
          Kenneth R. French Data Library:
        </p>
        <pre className="formula">
          {`r − rf = α + β_mkt·MktRF + β_smb·SMB + β_hml·HML + β_mom·Mom + ε`}
        </pre>
        <p>
          <strong className="font-medium">MktRF</strong> is the whole US stock market over
          T-bills; <strong className="font-medium">SMB</strong> (small minus big) is small
          companies over large; <strong className="font-medium">HML</strong> (high minus low) is
          cheap &ldquo;value&rdquo; stocks over expensive &ldquo;growth&rdquo; stocks;{" "}
          <strong className="font-medium">Mom</strong> is last year&rsquo;s winners over its
          losers. The betas say how much of each the fund carries. A fund with β_mkt = 1.1 and
          β_hml = −0.3 behaves like 1.1× the market with a growth tilt.
        </p>
        <p>
          The headline fit uses the last {meta.window_months} months ({years} years) ending{" "}
          {month(meta.through)}. A fund with a shorter record uses all of it if it has at least{" "}
          {meta.min_months} months, and is marked &ldquo;short history&rdquo;; with fewer, it is
          left out.
        </p>

        <H2 id="attribution">the attribution identity</H2>
        <p>
          Averaging both sides of the regression over the window splits the fund&rsquo;s average
          excess return exactly:
        </p>
        <pre className="formula">
          {`mean(r − rf) = α + Σ β_k · mean(f_k)        (× 12 for a year)`}
        </pre>
        <p>
          Each term β_k · mean(f_k) is that factor&rsquo;s <em>contribution</em>: the loading
          times what the factor paid over those months (its <em>premium</em>). The contributions
          and alpha add up to the excess return with nothing left over, which is why the bars on
          each fund page sum to its return over T-bills. Annual figures are 12 times the monthly
          means.
        </p>
        <p>
          The <em>factor share</em> on the front page is 1 − α ÷ excess return: the part of the
          return over T-bills that factor exposure accounts for. It is shown only when the fund
          beat T-bills by more than 1% a year, because dividing by a number near zero is
          meaningless. Above 100% means alpha was negative: the factors explain more than the
          whole return.
        </p>
        <p>
          The <em>rolling</em> panels repeat the Carhart fit on every 36-month window of the
          fund&rsquo;s history since 1990 (or since it started), to show whether its exposures
          drifted.
        </p>

        <H2 id="newey-west">standard errors</H2>
        <p>
          Monthly fund returns are not independent draws: volatility clusters, and residuals can
          be autocorrelated. Ordinary standard errors would then overstate how precise alpha is.
          Every standard error here is Newey–West (heteroskedasticity- and
          autocorrelation-consistent), with the Newey &amp; West (1994) lag rule floor(4·(T/100)
          <sup>2/9</sup>): 4 lags for 120 months.
        </p>
        <p>
          The t-statistic is alpha divided by that standard error. A |t| of 2 or more is roughly
          significant at the 5% level, and that is the line the verdicts use: t ≥ 2 is
          &ldquo;skill&rdquo;, t ≤ −2 &ldquo;trails its factors&rdquo;, anything in between
          &ldquo;no detectable alpha&rdquo;. The 95% interval is alpha ± 1.96 standard errors.
          Ten years of monthly data is short: an interval several percent a year wide is normal,
          and &ldquo;indistinguishable from zero&rdquo; is not the same as &ldquo;zero&rdquo;.
        </p>

        <H2 id="why-carhart">why Carhart</H2>
        <p>
          The Carhart (1997) four-factor model, the Fama–French three factors plus momentum, is
          the standard benchmark for judging mutual funds (Fama &amp; French 2010 report it
          alongside the three-factor model). Its factors are the tilts most active equity funds actually take, and it
          is simple enough to read. As a robustness check, each fund page also shows the fit with
          the Fama–French profitability (RMW) and investment (CMA) factors added; when the
          answer changes sign or crosses |t| = 2, the verdict says so.
        </p>
        <p>
          For index, factor and sector funds, the verdict is &ldquo;as designed&rdquo;: they are
          meant to deliver factor exposure, and any &ldquo;alpha&rdquo; describes how their index
          differs from the model (a sector fund&rsquo;s industry bet, say), not a manager&rsquo;s
          skill.
        </p>

        <H2 id="fees">fees, gross alpha and the break-even fee</H2>
        <p>
          Yahoo&rsquo;s adjusted prices reflect what investors in the fund actually got, so they
          are net of the fund&rsquo;s expense ratio, and every alpha on this site is{" "}
          <em>after fees</em>. Adding the expense ratio back gives the gross alpha: what the
          manager added before charging for it. That gross alpha is also the break-even fee, the
          fee at which an investor would have done exactly as well as with T-bills plus the same
          factor exposure. A negative gross alpha means no fee, not even zero, would have been
          worth paying.
        </p>
        <p>
          Expense ratios are the current net figures from each fund&rsquo;s own site or
          prospectus, with the date and source on its page. Fees change over a decade, so the
          gross figure is an approximation. Sales loads, advisory fees and taxes are not in the
          returns: two American Funds share classes here are shown at NAV, without their
          front-end load.
        </p>

        <H2 id="replica">the replica is not literally free</H2>
        <p>
          &ldquo;T-bills plus the same factor exposure&rdquo; is a benchmark, not a product. The
          French factors are long-short portfolios that cost nothing to hold on paper: no fees,
          no trading costs, no taxes, no shorting costs, and no money needed up front. Nobody can
          buy them at those terms.
        </p>
        <p>
          What an investor can buy is close. The market factor is roughly a total-market index
          fund at 0.03% a year; small-cap, value and momentum tilts are available in factor funds
          for about 0.05% to 0.30%. Those funds only approximate the factors (they are long-only,
          and their definitions differ), which is why they appear here too, with their own
          alphas. Read an alpha as &ldquo;beyond what cheap exposure would have given you, to
          within a few basis points&rdquo;, not to the decimal.
        </p>

        <H2 id="selection">selection bias</H2>
        <p>
          These are <strong className="font-medium">famous funds chosen by the author</strong>,
          not a random sample. Funds become famous by doing well, and funds that did badly tend
          to be merged or closed, so a list like this leans toward past winners. It says nothing
          about active management in general: for that, see studies of the whole fund universe,
          such as Fama &amp; French (2010). Nothing here is investment advice.
        </p>

        <H2 id="data">data caveats</H2>
        <ul className="list-disc space-y-2 pl-5 marker:text-line">
          <li>
            Returns are computed from Yahoo Finance month-end adjusted closes, which fold in
            splits and distributions. For mutual funds, large year-end capital-gains
            distributions are sometimes adjusted imperfectly, which can put a spurious jump in
            one month. A fund with a monthly return beyond ±60% or a missing month inside its
            window is held back: it keeps its previous numbers, marked stale.
          </li>
          <li>
            Where the fund&rsquo;s own filings show that Yahoo&rsquo;s adjustment is wrong (for
            example, a distribution the fund never paid), that month&rsquo;s return is replaced
            before anything is fitted. Each correction is listed with its source in{" "}
            <a href={`${REPO_URL}/blob/main/live/overrides.csv`}>live/overrides.csv</a> and noted
            on the fund&rsquo;s page.
          </li>
          <li>
            Each fund is one share class (named on its page). Other classes of the same fund
            have different fees and slightly different returns.
          </li>
          <li>
            Berkshire Hathaway is an operating company, not a fund: it has no expense ratio,
            and its costs are already inside its returns.
          </li>
          <li>
            JPMorgan Equity Premium Income sells index call options, so its market beta is
            structurally below 1; a linear factor model describes an options strategy only
            roughly.
          </li>
          <li>
            Funds are renamed and reorganized; each page notes the changes that matter. A fund
            whose data could not be refreshed keeps its previous numbers and is marked stale.
          </li>
        </ul>

        <H2 id="sources">sources and licensing</H2>
        <p>
          Factor returns and the T-bill rate come from the{" "}
          <a href="https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html">
            Kenneth R. French Data Library
          </a>
          , which Professor French makes freely available; thank you. Fund prices come from
          Yahoo Finance, whose terms restrict redistributing its data, so this site shows only
          statistics derived from those prices and growth of $1 normalized to the start of the
          window, never the prices themselves. The code, including the pipeline that builds every
          number here, is open source (MIT) on <a href={REPO_URL}>GitHub</a>, and you can rerun
          it yourself.
        </p>

        <H2 id="updates">update schedule and checks</H2>
        <p>
          A scheduled job refreshes the data twice a month (on the 5th and the 20th). The
          window ends at the latest month that both the factor library and most funds have:
          currently {month(meta.through)}. The French library usually publishes a month&rsquo;s
          factors some weeks after it ends, so the site trails the calendar by one to two months.
        </p>
        <p>
          Before anything is published, the pipeline checks itself against known answers:
          broad index funds (SPY, VTI) must have a market beta close to 1 with R² above 0.95, a
          small-cap index a positive size loading, value and growth indexes loadings of the
          right sign on value, and a momentum fund a positive momentum loading. If those checks
          fail, if more than a fifth of the funds fail to download, or if too many past returns
          change, nothing is published and the previous data stays up.
        </p>
        <p className="text-sm text-muted">
          References: Carhart, M. (1997), &ldquo;On Persistence in Mutual Fund
          Performance,&rdquo; <em>Journal of Finance</em> 52(1). Fama, E. and French, K. (2010),
          &ldquo;Luck versus Skill in the Cross-Section of Mutual Fund Returns,&rdquo;{" "}
          <em>Journal of Finance</em> 65(5). Newey, W. and West, K. (1994), &ldquo;Automatic Lag
          Selection in Covariance Matrix Estimation,&rdquo; <em>Review of Economic Studies</em>{" "}
          61(4).
        </p>
      </div>

      <nav className="mt-16 text-sm">
        <Link href="/">← all funds</Link>
      </nav>
    </article>
  );
}
