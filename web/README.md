# unbundle live: the website

A static Next.js site that shows, for each fund in `live/funds.csv`, how much of its last
ten years' return was factor exposure and how much was alpha after fees. Every number on it
comes from the JSON in `web/data`, which the Python pipeline in `live/` writes.

## How data flows

```
live/funds.csv ──┐
Yahoo prices ────┼─> python -m live.build --out web/data ─> web/data/*.json ─> next build ─> web/out/
Ken French ──────┘   (fit, verdicts, checks; atomic write)     (committed)        (static HTML)
```

1. **`python -m live.build --out web/data`** (repository root) downloads monthly prices and
   factors, fits the Carhart and five-factor-plus-momentum models, runs the control-group
   and sanity checks, and writes `meta.json`, `index.json` and `funds/<TICKER>.json`. It
   writes nothing if a check fails, and a rerun on the same data produces identical bytes.
2. **`python -m live.validate web/data`** checks the schema and invariants (contributions
   sum to the excess return, growth series length, and so on).
3. **`npm run build`** (in `web/`) reads those files at build time in `lib/data.ts`. Each
   file is checked again by hand-written validators (`assertMeta`, `assertSummary`,
   `assertFund`) that throw on a missing or ill-typed field, so bad data fails the build
   instead of producing a broken page.
4. Next writes a fully static site to **`web/out/`**: `index.html`, `method.html` and one
   `fund/<TICKER>.html` per fund. Any static host can serve it.

The scheduled workflow `.github/workflows/live-data.yml` runs steps 1 and 2 on the 5th and
20th of each month and commits changed data; `.github/workflows/web.yml` typechecks and
builds the site whenever `web/` changes.

## Develop

Node 20.9 or later.

```bash
cd web
npm ci
npm run dev         # http://localhost:3000
npm run typecheck   # next typegen && tsc --noEmit
npm run build       # static export to out/
```

To preview the export, serve `out/` with any static file server that maps `/method` to
`method.html` (for example `npx serve out`).

## Layout

```
app/
  layout.tsx            header, footer (data-through date), fonts, metadata
  page.tsx              /: intro, verdict tally, sortable table, fee-vs-alpha scatter
  fund/[ticker]/page.tsx  one page per fund (generateStaticParams over index.json)
  method/page.tsx       the math and caveats
  globals.css           design tokens (light and dark) and chart roles
components/
  FundTable.tsx         sortable, filterable table (client)
  ModelTable.tsx        every estimate of one model fit
  charts/               hand-written SVG charts, no chart library
lib/
  types.ts              the JSON schema as TypeScript types
  data.ts               build-time loading and validation
  format.ts             percent, t-stat, month and label formatting
  scale.ts              scales and ticks for the charts
data/                   written by live.build; do not edit by hand
```

Charts are client components only so they can measure their width (text stays at its real
size on a phone) and offer hover, tap and keyboard readouts; the static HTML already
contains every chart. Each has an `aria-label` summary and its numbers nearby in text or a
table.

Prices come from Yahoo Finance, whose terms restrict redistribution, so the site publishes
only derived statistics and growth of $1 normalized to the start of each window.
