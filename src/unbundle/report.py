"""A one-file HTML tearsheet: open it in any browser, send it to anyone.

Everything is inline - styles, SVG charts, a few lines of script for the hover readouts -
so the file works offline and has no dependencies. Light and dark follow the viewer's
system setting.
"""

from __future__ import annotations

import html
from datetime import date

import pandas as pd

from . import plot
from .factors import FACTOR_LABELS
from .model import Attribution, Results
from .rolling import rolling_exposures


def _theme(pal: dict, *, page: str, ring: str, scheme: str) -> str:
    """One color scheme as CSS custom properties, from the same palette the charts use."""
    tokens = {**pal, "page": page, "ring": ring}
    return f"color-scheme:{scheme};" + ";".join(f"--{k}:{v}" for k, v in tokens.items())


_LIGHT = _theme(plot.LIGHT, page="#f9f9f7", ring="rgba(11,11,11,.10)", scheme="light")
_DARK = _theme(plot.DARK, page="#0d0d0d", ring="rgba(255,255,255,.10)", scheme="dark")

# Dark follows the system unless the page is pinned with <html data-theme="light|dark">.
THEME = (
    f":root{{{_LIGHT}}}\n"
    f'@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{{_DARK}}}}}\n'
    f':root[data-theme="dark"]{{{_DARK}}}\n'
)

STYLE = (
    THEME
    + """
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink)}
.ub{font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:32px 16px 48px}
.wrap{max-width:780px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:18px;margin:40px 0 4px}
h3{font-size:14px;margin:24px 0 8px;color:var(--ink2);font-weight:600}
.lede{color:var(--ink2);margin:0 0 24px}
.card,.tile{background:var(--surface);border-radius:12px;box-shadow:0 0 0 1px var(--ring)}
.card{padding:16px;margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{padding:14px 16px}
.tile .k{color:var(--ink2);font-size:12px}
.tile .v{font-size:26px;font-weight:600;margin-top:2px}
.tile .s{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13px}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left}
th{color:var(--ink2);font-weight:600}
tr.em td{font-weight:600}
.scroll{overflow-x:auto}
details summary{cursor:pointer;color:var(--ink2);font-size:13px;margin-top:8px}
.note{color:var(--muted);font-size:12px;margin-top:6px}
svg .mark:hover path,svg .mark:focus path{opacity:.8}
.tip{position:fixed;z-index:9;display:none;pointer-events:none;padding:8px 10px;
  font-size:12px;background:var(--surface);color:var(--ink);border-radius:8px;
  box-shadow:0 0 0 1px var(--ring),0 4px 16px rgba(0,0,0,.12)}
.tip .d{color:var(--muted);margin-bottom:4px}
.tip .r{display:flex;align-items:center;gap:8px;white-space:nowrap}
.tip .r b{font-weight:600}
.tip .key{width:12px;height:2px;border-radius:1px}
footer{color:var(--muted);font-size:12px;margin-top:40px;padding-top:16px;
  border-top:1px solid var(--grid)}
"""
)

# Hover readouts. Bars get the styled tooltip in place of their native <title> one; line
# charts get a crosshair that snaps to the nearest month and lists every series. Text is
# only ever set with textContent.
SCRIPT = r"""
(() => {
  const root = document.querySelector(".ub");
  const tip = document.createElement("div");
  tip.className = "tip";
  root.appendChild(tip);

  const row = (role, value, name) => {
    const r = document.createElement("div");
    r.className = "r";
    const key = document.createElement("span");
    key.className = "key";
    key.style.background = "var(--" + role + ")";
    const b = document.createElement("b");
    b.textContent = value;
    const t = document.createElement("span");
    t.textContent = name;
    r.append(key, b, t);
    return r;
  };
  const show = (head, rows, x, y) => {
    const h = document.createElement("div");
    h.className = "d";
    h.textContent = head;
    tip.replaceChildren(h, ...rows);
    tip.style.display = "block";
    tip.style.left = Math.min(x + 14, innerWidth - tip.offsetWidth - 8) + "px";
    tip.style.top = Math.min(y + 14, innerHeight - tip.offsetHeight - 8) + "px";
  };
  const hide = () => {
    tip.style.display = "none";
  };

  document.querySelectorAll("g.mark").forEach((g) => {
    const d = g.dataset;
    const title = g.querySelector("title");
    if (title) {
      g.setAttribute("aria-label", title.textContent);
      title.remove();
    }
    const rows = () => [row(d.color, d.value, d.detail)];
    g.addEventListener("pointermove", (e) => show(d.label, rows(), e.clientX, e.clientY));
    g.addEventListener("pointerleave", hide);
    g.addEventListener("focus", () => {
      const b = g.getBoundingClientRect();
      show(d.label, rows(), b.left + b.width / 2, b.top + b.height / 2);
    });
    g.addEventListener("blur", hide);
  });

  const fmt = (v, f) =>
    f === "money"
      ? "$" + (v >= 100 ? Math.round(v).toLocaleString() : v.toFixed(2))
      : (v < 0 ? "\u2212" : "+") + Math.abs(v).toFixed(2);

  document.querySelectorAll("rect.hover").forEach((r) => {
    const d = JSON.parse(r.dataset.chart);
    const svg = r.ownerSVGElement;
    const n = d.labels.length - 1;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("y1", d.top);
    line.setAttribute("y2", d.bottom);
    line.setAttribute("stroke", "var(--base)");
    line.style.display = "none";
    line.style.pointerEvents = "none";
    svg.insertBefore(line, r);
    r.addEventListener("pointermove", (e) => {
      const p = svg.createSVGPoint();
      p.x = e.clientX;
      p.y = e.clientY;
      const q = p.matrixTransform(svg.getScreenCTM().inverse());
      const i = Math.max(0, Math.min(n, Math.round(((q.x - d.x0) / (d.x1 - d.x0)) * n)));
      const x = d.x0 + (i / n) * (d.x1 - d.x0);
      line.setAttribute("x1", x);
      line.setAttribute("x2", x);
      line.style.display = "";
      const rows = d.series.map((s) => row(s.color, fmt(s.values[i], d.fmt), s.name));
      show(d.labels[i], rows, e.clientX, e.clientY);
    });
    r.addEventListener("pointerleave", () => {
      hide();
      line.style.display = "none";
    });
  });
})();
"""


def _e(x: object) -> str:
    return html.escape(str(x), quote=True)


def _pct(v: float, digits: int = 2, signed: bool = False) -> str:
    s = f"{100 * v:+.{digits}f}%" if signed else f"{100 * v:.{digits}f}%"
    return s.replace("-", "−")


def _num(v: float, digits: int = 2) -> str:
    return f"{v:.{digits}f}".replace("-", "−")


def _row(cells, cls: str = "", tag: str = "td") -> str:
    attr = f' class="{cls}"' if cls else ""
    return f"<tr{attr}>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"


def _table(rows: list[str]) -> str:
    return f'<div class="scroll"><table>{"".join(rows)}</table></div>'


def _tiles(a: Attribution) -> str:
    tiles = [
        ("Excess return", _pct(a.excess_annual, 1), "per year over T-bills"),
        (
            "Alpha",
            _pct(a.alpha_annual, 1, signed=True),
            f"t = {_num(a.alpha_t)}, p = {a.alpha_p:.3f}",
        ),
        ("Explained by factors", f"{100 * a.r2:.0f}%", "of the monthly variance (R²)"),
        (
            "Information ratio",
            _num(a.information_ratio),
            f"tracking error {_pct(a.tracking_error, 1)}",
        ),
    ]
    return (
        '<div class="tiles">'
        + "".join(
            f'<div class="tile"><div class="k">{_e(k)}</div><div class="v">{_e(v)}</div>'
            f'<div class="s">{_e(s)}</div></div>'
            for k, v, s in tiles
        )
        + "</div>"
    )


COEF_HEAD = ["", "Loading", "Std err (NW)", "t", "Premium %/yr", "Contribution %/yr"]


def _coef_table(a: Attribution) -> str:
    rows = [_row(map(_e, COEF_HEAD), tag="th")]
    for name, r in a.to_frame().iterrows():
        is_alpha = name == "alpha"
        scale = 1200 if is_alpha else 1  # alpha is shown in %/yr, loadings as they are
        label = "Alpha (%/yr)" if is_alpha else FACTOR_LABELS.get(name, name)
        premium = "" if pd.isna(r["premium %/yr"]) else _num(r["premium %/yr"])
        cells = [
            _e(label),
            _num(scale * r["coef"]),
            _num(scale * r["std err (NW)"]),
            _num(r["t"]),
            premium,
            _num(r["contribution %/yr"]),
        ]
        rows.append(_row(cells, "em" if is_alpha else ""))
    rows.append(_row(["Excess return", "", "", "", "", _num(100 * a.excess_annual)], "em"))
    return _table(rows)


def _series_table(frame: pd.DataFrame, fmt) -> str:
    rows = [_row(["Month", *map(_e, frame.columns)], tag="th")]
    rows += [
        _row([_e(i), *(fmt(v) for v in r)])
        for i, r in zip(frame.index, frame.to_numpy(), strict=True)
    ]
    return _table(rows)


def _asset_section(a: Attribution, window: int) -> str:
    bars = plot.attribution_svg(a, pal=plot.CSS, titles=[a.name], standalone=False)
    growth_chart = plot.growth_svg(a, pal=plot.CSS, standalone=False)
    parts = [
        f"<h2>{_e(a.name)}</h2>",
        f'<p class="lede">{_e(a.model)} model · {a.start} to {a.end} · {a.nobs} months · '
        f"Newey-West standard errors, {a.maxlags} lags</p>",
        _tiles(a),
        "<h3>Where the return came from</h3>",
        f'<div class="card">{bars}</div>',
        f'<div class="card">{_coef_table(a)}</div>',
        "<h3>Growth of $1 against the same factor exposure</h3>",
        f'<div class="card">{growth_chart}',
        '<p class="note">Gray line: T-bills plus the fund\'s own factor loadings, month by '
        "month, with no alpha. The gap between the lines is compounded alpha plus noise.</p>"
        "</div>",
    ]
    base = a.rf if a.rf is not None else 0.0
    growth = pd.DataFrame(
        {
            a.name: (1 + a.excess + base).cumprod(),
            "Factors only": (1 + a.replicating + base).cumprod(),
        }
    )
    parts.append(
        "<details><summary>Growth of $1, table</summary>"
        + _series_table(growth.round(4), lambda v: f"{v:,.3f}")
        + "</details>"
    )
    if a.nobs >= window + 12:
        roll = rolling_exposures(a.excess, a.factor_returns, window=window)
        chart = plot.rolling_svg(roll, a.factors, pal=plot.CSS, window=window, standalone=False)
        parts += [
            f"<h3>Rolling {window}-month loadings</h3>",
            f'<div class="card">{chart}',
            '<p class="note">A loading that drifts means the strategy changed, whatever the '
            "full-sample alpha says.</p></div>",
            "<details><summary>Rolling loadings, table</summary>"
            + _series_table(roll.round(3), _num)
            + "</details>",
        ]
    return "".join(parts)


def _summary_section(results: Results) -> str:
    table = results.table()
    cols = ["months", "excess %/yr", "alpha %/yr", "t(alpha)", "R²", "IR"]
    head = ["", "Months", "Excess %/yr", "Alpha %/yr", "t(alpha)", "R²", "IR"]
    rows = [_row(map(_e, head), tag="th")]
    rows += [
        _row([_e(name), *(str(int(r[c])) if c == "months" else _num(r[c]) for c in cols)])
        for name, r in table.iterrows()
    ]
    out = ["<h2>Summary</h2>", f'<div class="card">{_table(rows)}</div>']
    common = results.excess.dropna()
    if common.shape[1] >= 2 and common.shape[0] > common.shape[1] + len(results.factors) + 1:
        test = results.alpha_test()
        worst, worst_alpha = test.max_abs_alpha
        out.append(
            '<div class="card"><b>Are all the alphas zero?</b> '
            f"On the {test.nobs} months every asset has data: "
            f"GRS F{test.grs_df} = {_num(test.grs)} (p = {test.grs_pvalue:.3g}); "
            f"HAC Wald χ²({test.n_assets}) = {_num(test.wald)} (p = {test.wald_pvalue:.3g}). "
            f"Mean |alpha| {_pct(test.mean_abs_alpha, 2)}/yr, "
            f"largest {_e(worst)} {_pct(worst_alpha, 2, signed=True)}/yr.</div>"
        )
    return "".join(out)


def html_report(
    results: Results, *, title: str | None = None, window: int = 36, source: str = ""
) -> str:
    """Render :class:`~unbundle.model.Results` as a self-contained HTML page."""
    names = list(results)
    heading = title or ("unbundle: " + ", ".join(names[:4]) + (" …" if len(names) > 4 else ""))
    body = [
        f"<h1>{_e(heading)}</h1>",
        '<p class="lede">How much of the return was exposure to known factors you could buy '
        "cheaply, and how much was left over.</p>",
    ]
    if len(names) > 1:
        body.append(_summary_section(results))
    body += [_asset_section(results[n], window) for n in names]
    body.append(
        "<footer>Time-series regressions of monthly excess returns on traded factor returns; "
        "Newey-West (Bartlett) standard errors with floor(4(T/100)^(2/9)) lags; attribution "
        "= loading × the factor's average return over the same months, plus alpha, which sums "
        f"exactly to the average excess return. {_e(source)} Generated {date.today():%Y-%m-%d} "
        "by unbundle.</footer>"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_e(heading)}</title><style>{STYLE}</style></head>"
        f"<body><div class='ub'><div class='wrap'>{''.join(body)}</div></div>"
        f"<script>{SCRIPT}</script></body></html>"
    )
