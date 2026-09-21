"""Charts as plain SVG strings - no plotting library.

Three charts, all in the *emphasis* form: the thing the reader is here for (alpha, the
fund) in the accent blue, everything that is context (factor exposure, the factor-only
replica) in one de-emphasis gray.

* :func:`attribution_svg` - where the average excess return came from: one horizontal bar
  per factor (beta x factor premium) and one for alpha, from a zero baseline.
* :func:`growth_svg` - growth of $1 in the fund against $1 in T-bills plus the same factor
  exposure. The widening gap is compounded alpha.
* :func:`rolling_svg` - small multiples of rolling loadings, one panel per factor.

Colors come from a palette mapping. ``LIGHT`` and ``DARK`` hold hex values for standalone
files; ``CSS`` points every role at a CSS custom property so an HTML page can theme them.
"""

from __future__ import annotations

import html
import json
import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from .factors import FACTOR_LABELS

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'

LIGHT = {
    "surface": "#fcfcfb",
    "ink": "#0b0b0b",
    "ink2": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "base": "#c3c2b7",
    "accent": "#2a78d6",
    "context": "#898781",
}
DARK = {
    "surface": "#1a1a19",
    "ink": "#ffffff",
    "ink2": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "base": "#383835",
    "accent": "#3987e5",
    "context": "#898781",
}
CSS = {role: f"var(--{role})" for role in LIGHT}

BAR = 20  # bar thickness, px (spec: <= 24)
RADIUS = 4  # rounded data-end


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _minus(s: str) -> str:
    """Typographic minus sign for negative numbers."""
    return s.replace("-", "−")


def _text(x, y, s, *, fill, size=12, anchor="start", weight=400, extra=""):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}"{extra}>{_e(s)}</text>'
    )


def _line(x1, y1, x2, y2, stroke):
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="1"/>'
    )


def _polyline(points: str, stroke: str) -> str:
    return (
        f'<polyline points="{points}" fill="none" stroke="{stroke}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )


def _dot(cx, cy, fill, ring):
    """An 8px end marker; the 2px ring in the surface color lifts it off the line."""
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{fill}" '
        f'stroke="{ring}" stroke-width="2"/>'
    )


def _hover(x0, top, x1, bottom, data: dict) -> str:
    """Transparent hit area; the report's script reads data-chart to draw the crosshair."""
    return (
        f'<rect class="hover" x="{x0:.1f}" y="{top:.1f}" width="{x1 - x0:.1f}" '
        f'height="{bottom - top:.1f}" fill="transparent" '
        f"data-chart='{_e(json.dumps(data))}'/>"
    )


def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    """Round tick values covering [lo, hi] (1-2-5 steps)."""
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(target, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    first = math.floor(lo / step + 1e-9)
    last = math.ceil(hi / step - 1e-9)
    return [round(k * step, 10) for k in range(first, last + 1)]


def log_ticks(lo: float, hi: float) -> list[float]:
    """Round growth-of-$1 ticks for a log axis: 1-2-5 or powers of ten, 3-7 of them."""
    for mults in ((1,), (1, 3), (1, 2, 5), (1, 1.5, 2, 3, 5, 7)):
        ticks = [
            m * 10**k
            for k in range(math.floor(math.log10(lo)) - 1, math.ceil(math.log10(hi)) + 1)
            for m in mults
            if lo <= m * 10**k <= hi
        ]
        if len(ticks) >= 3:
            return ticks[:: max(1, len(ticks) // 7)]
    return [lo, hi]


def _money(v: float) -> str:
    if v >= 100:
        return f"${v:,.0f}"
    if v >= 10:
        return f"${v:.0f}"
    return f"${v:g}"


def _bar_path(x0: float, x1: float, y: float, h: float, r: float = RADIUS) -> str:
    """A horizontal bar square at the baseline x0 and rounded at the data end x1."""
    length = abs(x1 - x0)
    r = min(r, length, h / 2)
    if length < 0.5:
        return ""
    s = 1 if x1 > x0 else -1
    return (
        f"M{x0:.2f},{y:.2f} H{x1 - s * r:.2f} Q{x1:.2f},{y:.2f} {x1:.2f},{y + r:.2f} "
        f"V{y + h - r:.2f} Q{x1:.2f},{y + h:.2f} {x1 - s * r:.2f},{y + h:.2f} H{x0:.2f} Z"
    )


def _open(width: float, height: float, pal: dict, label: str, standalone: bool) -> list[str]:
    ns = ' xmlns="http://www.w3.org/2000/svg"' if standalone else ""
    parts = [
        f'<svg{ns} viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}" role="img" aria-label="{_e(label)}" '
        f"font-family='{FONT}' "
        f'style="max-width:100%;height:auto;font-variant-numeric:tabular-nums">'
    ]
    if standalone:
        parts.append(f'<rect width="100%" height="100%" rx="12" fill="{pal["surface"]}"/>')
    return parts


# -- attribution ------------------------------------------------------------------------
def _attribution_rows(a) -> list[tuple[str, float, str]]:
    """(label, contribution in %/yr, how it was computed) for each bar."""
    rows = []
    for f in a.factors:
        detail = f"beta {a.betas[f]:.2f} × premium {100 * a.premia[f]:.2f}%/yr"
        rows.append((FACTOR_LABELS.get(f, f), 100 * float(a.contributions[f]), _minus(detail)))
    detail = f"t = {a.alpha_t:.2f}, p = {a.alpha_p:.3f}"
    rows.append(("Alpha", 100 * float(a.alpha_annual), _minus(detail)))
    return rows


def attribution_svg(
    attributions,
    *,
    pal: dict = LIGHT,
    width: float = 720,
    titles: Sequence[str] | None = None,
    heading: str | None = None,
    standalone: bool = True,
) -> str:
    """Horizontal bars of beta x premium per factor plus alpha, in %/yr.

    Pass one :class:`~unbundle.model.Attribution` or several; several are drawn as small
    multiples on a shared scale, so the alpha bars compare directly.
    """
    attrs = attributions if isinstance(attributions, (list, tuple)) else [attributions]
    rows = [_attribution_rows(a) for a in attrs]
    values = [v for r in rows for _, v, _ in r]
    lo, hi = min(0.0, min(values)), max(0.0, max(values))

    pad = 16
    label_w = 92
    head_h = 46 if heading else 8
    title_h = 40
    row_h = BAR + 12
    n_rows = len(rows[0])
    plot_h = n_rows * row_h
    axis_h = 22
    height = head_h + title_h + plot_h + axis_h + pad
    gap = 28
    panel_w = (width - 2 * pad - label_w - gap * (len(attrs) - 1)) / len(attrs)
    tip_room = 44  # value labels sit outside the bar ends

    out = _open(width, height, pal, heading or "Return attribution", standalone)
    if heading:
        out.append(_text(pad, pad + 14, heading, fill=pal["ink"], size=15, weight=600))

    top = head_h + title_h
    for i, label in enumerate(r[0] for r in rows[0]):
        y = top + i * row_h + row_h / 2 + 4
        weight = 600 if label == "Alpha" else 400
        out.append(
            _text(pad, y, label, fill=pal["ink" if label == "Alpha" else "ink2"], weight=weight)
        )

    for p, (a, prow) in enumerate(zip(attrs, rows, strict=True)):
        x_left = pad + label_w + p * (panel_w + gap) + tip_room
        x_right = pad + label_w + p * (panel_w + gap) + panel_w - tip_room

        def sx(v, xl=x_left, xr=x_right):
            return xl + (v - lo) / (hi - lo) * (xr - xl)

        title = titles[p] if titles else a.name
        cx = (x_left + x_right) / 2
        out.append(
            _text(cx, head_h + 14, title, fill=pal["ink"], size=13, weight=600, anchor="middle")
        )
        sub = f"{100 * a.excess_annual:.1f}%/yr over T-bills · alpha t = {a.alpha_t:.2f}"
        out.append(_text(cx, head_h + 30, sub, fill=pal["muted"], size=11, anchor="middle"))

        # every bar carries its value, so the axis is just the zero baseline
        x0 = sx(0.0)
        out.append(_line(x0, top - 4, x0, top + plot_h, pal["base"]))
        hit_x, hit_w = x_left - tip_room, x_right - x_left + 2 * tip_room
        for i, (label, v, detail) in enumerate(prow):
            y = top + i * row_h + (row_h - BAR) / 2
            role = "accent" if label == "Alpha" else "context"
            color = pal[role]
            path = _bar_path(x0, sx(v), y, BAR)
            value = _minus(f"{v:+.2f}%/yr")
            # <title> is the no-script tooltip; the report's script upgrades it from data-*
            out.append(
                f'<g class="mark" tabindex="0" data-label="{_e(label)}" data-value="{_e(value)}" '
                f'data-detail="{_e(detail)}" data-color="{role}">'
                f"<title>{_e(f'{label}: {value} ({detail})')}</title>"
                f'<rect x="{hit_x:.1f}" y="{y - 6:.1f}" width="{hit_w:.1f}" '
                f'height="{BAR + 12}" fill="transparent"/>'
                + (f'<path d="{path}" fill="{color}"/>' if path else "")
                + "</g>"
            )
            end = sx(v)
            anchor, dx = ("start", 6) if v >= 0 else ("end", -6)
            out.append(
                _text(
                    end + dx,
                    y + BAR / 2 + 4,
                    _minus(f"{v:+.1f}"),
                    fill=pal["ink" if label == "Alpha" else "ink2"],
                    size=12,
                    anchor=anchor,
                    weight=600 if label == "Alpha" else 400,
                )
            )
    out.append(
        _text(
            width - pad,
            height - 8,
            "percentage points per year; bars sum to the excess return",
            fill=pal["muted"],
            size=10,
            anchor="end",
        )
    )
    out.append("</svg>")
    return "".join(out)


# -- line charts --------------------------------------------------------------------------
def _year_ticks(index: pd.PeriodIndex, n: int = 6) -> list[int]:
    years = sorted({p.year for p in index})
    span = years[-1] - years[0]
    step = next(s for s in (1, 2, 5, 10, 20, 25, 50) if span / s <= n)
    return [y for y in range(math.ceil(years[0] / step) * step, years[-1] + 1, step)]


def growth_svg(
    a,
    *,
    pal: dict = LIGHT,
    width: float = 720,
    height: float = 320,
    heading: str | None = None,
    standalone: bool = True,
) -> str:
    """Growth of $1: the asset against T-bills plus the same factor loadings and no alpha."""
    base = a.rf if a.rf is not None else pd.Series(0.0, index=a.excess.index)
    fund = (1 + a.excess + base).cumprod()
    replica = (1 + a.replicating + base).cumprod()
    start = a.excess.index[0] - 1
    fund = pd.concat([pd.Series({start: 1.0}), fund])
    replica = pd.concat([pd.Series({start: 1.0}), replica])
    idx = pd.PeriodIndex(fund.index, freq="M")

    pad, left, right = 16, 52, 150
    head_h = 34 if heading else 12
    top, bottom = head_h + 8, height - 30
    lo = min(fund.min(), replica.min()) * 0.92
    hi = max(fund.max(), replica.max()) * 1.08
    ticks = log_ticks(lo, hi)
    x0, x1 = pad + left, width - right
    n = len(idx) - 1

    def sx(i):
        return x0 + i / n * (x1 - x0)

    def sy(v):
        return bottom - (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo)) * (
            bottom - top
        )

    fund_label = a.name
    replica_label = "Factors only"
    out = _open(width, height, pal, heading or f"Growth of $1: {a.name}", standalone)
    if heading:
        out.append(_text(pad, pad + 14, heading, fill=pal["ink"], size=15, weight=600))
    for t in ticks:
        y = sy(t)
        if bottom - y > 8:  # the baseline already marks the bottom tick
            out.append(_line(x0, y, x1, y, pal["grid"]))
        out.append(_text(x0 - 8, y + 4, _money(t), fill=pal["muted"], size=11, anchor="end"))
    for yr in _year_ticks(idx):
        pos = idx.get_indexer([pd.Period(f"{yr}-01", "M")])[0]
        if pos < 0:
            continue
        x = sx(pos)
        out.append(_text(x, bottom + 18, str(yr), fill=pal["muted"], size=11, anchor="middle"))
    out.append(_line(x0, bottom, x1, bottom, pal["base"]))

    def line(series, color):
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(series.to_numpy()))
        return _polyline(pts, color)

    out.append(line(replica, pal["context"]))
    out.append(line(fund, pal["accent"]))
    # end markers + direct labels (legend role: the two series are named at their ends)
    ends = [
        (fund.iloc[-1], pal["accent"], fund_label, pal["ink"]),
        (replica.iloc[-1], pal["context"], replica_label, pal["ink2"]),
    ]
    ys = [sy(v) for v, *_ in ends]
    if abs(ys[0] - ys[1]) < 30:  # keep end labels apart without detaching them
        mid = (ys[0] + ys[1]) / 2
        ys = [mid - 15, mid + 15] if ys[0] <= ys[1] else [mid + 15, mid - 15]
    for (v, color, label, ink), ly in zip(ends, ys, strict=True):
        y = sy(v)
        out.append(_dot(x1, y, color, pal["surface"]))
        if abs(ly - y) > 1:
            out.append(_line(x1 + 6, y, x1 + 12, ly, pal["base"]))
        out.append(
            _text(
                x1 + 14, ly - 1, label, fill=ink, size=12, weight=600 if ink == pal["ink"] else 400
            )
        )
        out.append(_text(x1 + 14, ly + 13, f"{_money(v)}", fill=pal["muted"], size=11))
    data = {
        "x0": x0,
        "x1": x1,
        "top": top,
        "bottom": bottom,
        "labels": [str(p) for p in idx],
        "series": [
            {"name": fund_label, "values": [round(float(v), 4) for v in fund], "color": "accent"},
            {
                "name": replica_label,
                "values": [round(float(v), 4) for v in replica],
                "color": "context",
            },
        ],
        "fmt": "money",
    }
    if not standalone:
        out.append(_hover(x0, top, x1, bottom, data))
    out.append("</svg>")
    return "".join(out)


def rolling_svg(
    rolling: pd.DataFrame,
    factors: Sequence[str],
    *,
    pal: dict = LIGHT,
    width: float = 720,
    window: int = 36,
    standalone: bool = True,
) -> str:
    """Small multiples of rolling loadings on a shared scale, then rolling alpha full width."""
    cols = 2
    pad, gap, panel_h = 16, 24, 140
    panel_w = (width - 2 * pad - gap * (cols - 1)) / cols
    layout = []  # (title, column, x, y, w)
    for k, f in enumerate(factors):
        r, c = divmod(k, cols)
        layout.append(
            (
                FACTOR_LABELS.get(f, f),
                f,
                pad + c * (panel_w + gap),
                pad + r * (panel_h + gap),
                panel_w,
            )
        )
    alpha_y = pad + math.ceil(len(factors) / cols) * (panel_h + gap)
    layout.append(
        (f"Alpha, %/yr ({window}-month window)", "alpha %/yr", pad, alpha_y, width - 2 * pad)
    )
    height = alpha_y + panel_h + 8
    beta = rolling.loc[:, list(factors)].to_numpy()
    b_lo, b_hi = min(0.0, np.nanmin(beta)), max(0.0, np.nanmax(beta))
    b_ticks = nice_ticks(b_lo, b_hi, 3)
    a_vals = rolling["alpha %/yr"].to_numpy()
    a_ticks = nice_ticks(min(0.0, np.nanmin(a_vals)), max(0.0, np.nanmax(a_vals)), 3)
    idx = rolling.index
    n = len(idx) - 1 if len(idx) > 1 else 1
    out = _open(width, height, pal, f"Rolling {window}-month loadings", standalone)
    for title, col, px, py, pw in layout:
        left = 36
        x0, x1 = px + left, px + pw - 8
        top, bottom = py + 26, py + panel_h - 20
        ticks = a_ticks if col == "alpha %/yr" else b_ticks
        lo, hi = ticks[0], ticks[-1]

        def sx(i, x0=x0, x1=x1):
            return x0 + i / n * (x1 - x0)

        def sy(v, lo=lo, hi=hi, top=top, bottom=bottom):
            return bottom - (v - lo) / (hi - lo) * (bottom - top)

        out.append(_text(px, py + 14, title, fill=pal["ink"], size=12, weight=600))
        for t in ticks:
            y = sy(t)
            stroke = pal["base"] if t == 0 else pal["grid"]
            out.append(_line(x0, y, x1, y, stroke))
            out.append(
                _text(x0 - 6, y + 4, _minus(f"{t:g}"), fill=pal["muted"], size=10, anchor="end")
            )
        yt = _year_ticks(pd.PeriodIndex(idx, freq="M"), 4 if pw < width / 2 else 8)
        for yr in yt:
            pos = idx.get_indexer([pd.Period(f"{yr}-01", "M")])[0]
            if pos >= 0:
                out.append(
                    _text(
                        sx(pos), bottom + 14, str(yr), fill=pal["muted"], size=10, anchor="middle"
                    )
                )
        vals = rolling[col].to_numpy()
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vals) if np.isfinite(v))
        out.append(_polyline(pts, pal["accent"]))
        last = vals[-1]
        out.append(_dot(sx(n), sy(last), pal["accent"], pal["surface"]))
        out.append(
            _text(
                x1, py + 14, _minus(f"latest {last:+.2f}"), fill=pal["ink2"], size=11, anchor="end"
            )
        )
        if not standalone:
            data = {
                "x0": x0,
                "x1": x1,
                "top": top,
                "bottom": bottom,
                "labels": [str(p) for p in idx],
                "series": [
                    {"name": title, "values": [round(float(v), 4) for v in vals], "color": "accent"}
                ],
                "fmt": "num",
            }
            out.append(_hover(x0, top, x1, bottom, data))
    out.append("</svg>")
    return "".join(out)
