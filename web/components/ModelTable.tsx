import { dec, factorLabel, modelLabel, pct, pval, spct, tstat } from "@/lib/format";
import type { ModelFit } from "@/lib/types";

/** Every estimate of one model fit, as a table: the accessible version of the charts. */
export function ModelTable({ fit, headline }: { fit: ModelFit; headline: boolean }) {
  const cell = "num px-2 py-1.5 text-right";
  return (
    <div>
      <h3 className="text-sm">
        {modelLabel(fit.model)}
        <span className="text-muted">{headline ? " · headline" : " · robustness check"}</span>
      </h3>
      <div className="table-scroll mt-2 border-y border-line">
        <table className="w-full min-w-[34rem] border-collapse text-sm">
          <caption className="sr-only">
            {modelLabel(fit.model)} estimates: loadings with Newey–West standard errors and
            t-statistics, annual factor premia, and each factor&rsquo;s contribution to the annual
            excess return.
          </caption>
          <thead>
            <tr className="border-b border-line text-xs text-muted">
              <th scope="col" className="py-2 pr-2 text-left font-normal">
                <span className="sr-only">term</span>
              </th>
              <th scope="col" className="px-2 py-2 text-right font-normal">
                β
              </th>
              <th scope="col" className="px-2 py-2 text-right font-normal">
                NW se
              </th>
              <th scope="col" className="px-2 py-2 text-right font-normal">
                t
              </th>
              <th scope="col" className="px-2 py-2 text-right font-normal">
                premium %/yr
              </th>
              <th scope="col" className="py-2 pl-2 text-right font-normal">
                contribution %/yr
              </th>
            </tr>
          </thead>
          <tbody>
            {fit.factors.map((f) => {
              const b = fit.betas[f]!;
              return (
                <tr key={f} className="border-b border-line">
                  <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                    {factorLabel(f)}
                  </th>
                  <td className={cell}>{dec(b.coef)}</td>
                  <td className={cell}>{dec(b.se)}</td>
                  <td className={cell}>{tstat(b.t)}</td>
                  <td className={cell}>{spct(fit.premia[f]!, 2)}</td>
                  <td className={`${cell} pr-0`}>{spct(fit.contributions[f]!, 2)}</td>
                </tr>
              );
            })}
            <tr className="border-b border-line">
              <th scope="row" className="py-1.5 pr-2 text-left font-normal">
                alpha
              </th>
              <td className={`${cell} text-muted`}>—</td>
              <td className={cell}>{pct(fit.alpha_se_annual, { digits: 2 })}</td>
              <td className={cell}>{tstat(fit.alpha_t)}</td>
              <td className={`${cell} text-muted`}>—</td>
              <td className={`${cell} pr-0`}>{spct(fit.contributions.alpha!, 2)}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" className="py-1.5 pr-2 text-left font-normal text-muted">
                excess return
              </th>
              <td colSpan={4} />
              <td className={`${cell} pr-0 font-medium`}>{spct(fit.excess_annual, 2)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
        {[
          ["alpha p-value", pval(fit.alpha_p)],
          ["R²", dec(fit.r2, 3)],
          ["adjusted R²", dec(fit.r2_adj, 3)],
          ["tracking error", `${pct(fit.tracking_error, { digits: 2 })}/yr`],
          ["information ratio", dec(fit.information_ratio)],
          ["months · NW lags", `${fit.nobs} · ${fit.maxlags}`],
        ].map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-line py-1">
            <dt className="text-muted">{k}</dt>
            <dd className="num">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
