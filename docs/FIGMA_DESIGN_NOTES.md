# DataClarity - Figma Design Notes

> **Status: DESIGN COMPLETE (sessions 1-3). Pending before Phase 6: PNG exports in `design/mockups/`, sticky scroll set in Figma, Return rate KPI decision.**
> Frontend phases (6A-6F) MUST NOT start until this file has real values.
> Claude Code: read this file and open the referenced frame before building any
> page. Never invent layout, spacing or colors.

## 1. How this file is used (workflow)

1. Thach designs each screen as a frame in Figma (Figma Pro).
2. For each frame: right-click -> **Copy link to selection**. The URL contains
   `?node-id=123-456`. Record that node id in the table in section 3.
3. Export the frame as PNG (2x) into `design/mockups/<ScreenName>.png` in the
   repo, so Claude Code can view the actual image, not just a description.
4. Fill the design tokens in section 4 from the Figma variables/styles panel.
5. In a frontend session, the prompt says: "Build page X per
   `docs/FIGMA_DESIGN_NOTES.md` frame `<name>`, mockup at
   `design/mockups/<name>.png`". Claude Code reads the token values from this
   file and the layout from the PNG.

Optional: if the Figma MCP connector is available in the session, Claude Code can
read the frame directly by node id instead of the PNG. The PNG export is the
reliable fallback and should exist either way.

## 2. File

- Figma file link: https://www.figma.com/design/DYhLQp7bxoa5HqfvIFNTej
- Figma file key: `DYhLQp7bxoa5HqfvIFNTej`
- Page ids: Tokens `0:1`, Components `1:2`, Screens `1:3`
- Pages in the file: `Screens`, `Components`, `Tokens`
- Mockup exports live in: `design/mockups/`

## 3. Frames per screen

| # | Screen | Figma frame name | Node id | Purpose / notes |
|---|---|---|---|---|
| 1 | Upload | `Upload` | `7:851` | idle state. drag-over and uploading states in spec frame `7:919` |
| 2 | Analyzing (stage 1) | `Upload - Analyzing` | `7:955` | 3-step indicator, step 2 active |
| 3 | Review | `Review` | `3:2` | column table + preview + action bar. Disabled Confirm spec `3:1090` |
| 4 | Review - edit action | `Review - Edit Action` | `10:1109` | qty_sold action list (legal actions only), fix_negative params popover, expanded AI rationale |
| 5 | Review - low confidence | `Review - Flags` | `10:1449` | "Needs attention (3)" filter, confidence < 0.70 rows only |
| 6 | Review - not inventory | `Review - Not Inventory` | `10:1789` | warning banner, mapping disabled, generic cleaning (roster file example) |
| 7 | Results | `Results` | `7:1098` | 6 summary tiles, 12-action log (one expanded), downloads, 2 CTAs |
| 8 | Analyzing (stages 2-4) | `Insights - Analyzing` | `7:1032` | Computing metrics / Diagnosing causes / Forecasting; header shows Diagnose active |
| 9 | Insights | `Insights` | `4:1489` | KPI cards, diverging-bar decomposition, diagnosis + ruled out, 3 recommendations, forecast. Insufficient history spec `4:1814` |
| 10 | Dashboard | `Dashboard` | `8:1057` | KPI cards, 30-day trend + product selector, top-5 bar, low-stock table. Empty + loading spec `13:2403` |
| 11 | Error states | `Errors` | `13:2144` | all 12 SPECS section 10 cases with code + HTTP status |

Link format: `https://www.figma.com/design/DYhLQp7bxoa5HqfvIFNTej?node-id=<id with - instead of :>`
(e.g. Review = `node-id=3-2`).

## 4. Design tokens (become CSS variables in `frontend/src/styles/tokens.css`)

Source of truth in Figma: Variables collection `Color` and `Dimension`, Text styles
`type/*`, Effect styles `shadow/*`. Every variable has a WEB code syntax set to
`var(--<group>-<name>)`, e.g. `bg/page` -> `var(--bg-page)`.

- Background: #F7F8FA . Surface / card: #FFFFFF . Subtle (table header, disabled): #F0F2F5
- Primary text: #1A1D21 . Secondary text: #6B7280
- Accent (primary action): #2563EB . Accent pressed: #1D4ED8 . Accent subtle (selected row): #EFF6FF . Text on accent: #FFFFFF
- Hover: no dedicated token. Primary/danger hover = base color at 90% opacity; secondary/ghost hover = bg/subtle
- Severity colors - low: #6B7280 . medium: #D97706 . high: #DC2626 (badge background = same color at 12% opacity, text = full color)
- Stock status - healthy: #16A34A . warning: #F59E0B . critical: #DC2626
- Preview diff - changed: #FEF3C7 . removed: #FEE2E2 (+ strikethrough) . added: #DCFCE7
- Low-confidence row background: severity/medium at 8% opacity
- Border: #E5E7EB . Divider: #E5E7EB (same token, no separate divider color)
- Font family: Inter, system-ui, sans-serif . Monospace (impact arithmetic): "Roboto Mono", ui-monospace, monospace
- Type scale (size / line-height / weight):
  H1 28/36 SemiBold . H2 20/28 SemiBold . H3 16/24 SemiBold . Body 14/20 Regular .
  Label 13/18 Medium . Caption 12/16 Regular . Metric 32/40 SemiBold
- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48
- Corner radius: card 10 . button 10 . badge / input / dropdown 6 . modal / drop zone 16 . pills (priority, step) fully rounded
- Shadow card: 0 2px 8px rgba(0,0,0,0.06) . popover: 0 8px 24px rgba(0,0,0,0.12)

## 5. Components (built, page `Components`)

| Component set | Node id | Variants |
|---|---|---|
| Button | `1:165` | type = primary / secondary / ghost / danger x state = default / hover / pressed / disabled |
| Dropdown | `1:321` | state = default / hover / open / disabled / error |
| Issue badge | `1:215` | severity = low / medium / high. Text format `<issue> · <count>` |
| Column row | `1:535` | state = default / hover / user-edited / low-confidence / ignored. Cell widths 160/90/210/180/200/220/100 (rebalanced so `categorical_nominal` and `transaction_date` fit) |
| KPI card | `1:570` | delta = up / down / flat / none |
| Recommendation card | `1:638` | confidence = high / medium / low (dots + text label) |
| Notice | `1:271` | tone = info / warning / error / success, optional actions |
| Progress stepper | `1:702` | type = 3-step / 5-stage |
| Step | `1:655` | state = pending / active / done |
| Confidence meter | `1:334` | level = high / medium / low (bar + numeric value) |
| Table header cell | `1:347` | sort = none / asc / desc |
| Icons | `1:166`-`1:205` | check, chevron-down, alert-triangle, info, x-circle, check-circle, arrow-up, arrow-down, minus, loader, file (16px, stroke 2) |

Open issues:
- KPI card delta color is tied to direction (up = green). Kept by decision (Thach),
  so Return rate +0.5 pp currently shows green. Known limitation.
- Contrast: severity/medium (#D97706, ~3.1:1) and status/healthy (#16A34A, ~3.3:1)
  are below WCAG AA 4.5:1 for 12-13px text. Kept by design decision; revisit if
  readability complaints come up.

## 6. Sample data used in mockups (internally consistent, reuse in test fixtures)

- Review: 12,480 rows x 14 columns; 37 exact duplicate rows; qty_sold missing 142
  (1.1%, required field so rows are dropped, never imputed); cust missing 980 (7.9%,
  >= 5% so filled with "Unknown"); supplier missing 54 (0.43%, < 5% so mode).
  Rows after cleaning: 12,480 - 37 - 142 = 12,301. Overall missing 0.7%.
- Semantic types use the 8 SPECS 4.2 values only; mappings use the 11 canonical
  fields only (region, brand, unit_cost, internal_notes -> ignore).
- Insights, June vs May 2026: customers 1,240 -> 1,112; orders per customer
  2.10 -> 2.14 (orders 2,604 -> 2,380); AOV $40.00 -> $40.40; revenue
  $104,160 -> $96,152 (-$8,008, -7.7%).
  Sequential substitution: customers -$10,752, frequency +$1,792, AOV +$952
  (sum = -$8,008).
- Forecast: 13 weekly actuals, WMA forecast ~$22.1k/week, no seasonality
  (fewer than two cycles, SPECS 7.5).

## 7. Preview pane (revised, 2026-09-22)

`design/mockups/Review.png` was re-exported with a redesigned preview pane, but
this file was not updated alongside it until now - written from that PNG plus
the frame `Review` (`3:2`) it replaces. Supersedes the two-table Before/After
layout the first build of this section implied.

- **One table**, not two side by side. A pinned `Row` column on the left holds
  the source row number (1-based in the file, not the sample's position). A
  dropped row shows a short reason next to its number in the severity/high
  color (e.g. "No qty", "Duplicate") when one can be determined - see below.
- **Only columns with at least one changed cell in the displayed sample are
  shown by default.** The rest are named above the table ("Hidden: sku,
  comments (no changes in sample)") behind a "Show unchanged columns (N)"
  button; when opened, they are appended after the changed columns, in
  `columns_after` order.
- **Diff styling**, all on the one value shown (there is no separate Before
  column any more): changed cell = `diff/changed` fill + dotted underline on
  the value; filled-in cell (was missing, now has a value) = `diff/added` fill
  + dotted underline; dropped row = `diff/removed` fill + strikethrough on
  every cell. The dotted underline is the required non-color signal (SPECS
  section 11: color is never the only signal) for a changed/filled cell; the
  strikethrough is that signal for a dropped row.
- **The original value on hover AND on keyboard focus** (`tabindex="0"`,
  `aria-describedby`, not hover-only): "Before: `<value>`" then the action
  that ran on that column (e.g. "Parse dates"). Every underlined cell is
  reachable by Tab.
- **Numbers**: right-aligned, tabular numerals, a whole number written as a
  float shows without the trailing ".0".
- **Row count chip**: the projected full-file count ("Rows 12,480 → 12,301
  (full file, projected)"), never the displayed sample size - `rows_in_file`
  and `rows_after` already describe the whole file even when the preview
  itself sampled it (`stages/ingest/preview.py`).

Not carried over from the mockup, because `PreviewResult`
(`docs/CONTRACTS.md` section 8) does not carry the data (CLAUDE.md 3.2: not
invented client-side):
- The mockup's `parsed 97.5% -> 100%` framing for a datetime column's delta
  chip. The delta chips keep the missing-% / unique-count framing from the
  previous build (`ColumnDelta` has no separate "parsed" figure).
- The exact per-row reason text ("No qty", "Duplicate") is not returned by
  the API (a dropped `PreviewRow`'s `changed` is empty). The frontend instead
  *derives* a reason from data it already has - the currently-submitted plan
  plus the row's own "before" values - which is not the same as inventing
  one:
  - "Duplicate" when `remove_exact_duplicates` is in the plan's
    `dataset_actions` and another row in the displayed sample has identical
    "before" values (execution order runs this before any column action, so
    a true duplicate is caught first regardless of what else is wrong with
    the row: `docs/AI_PIPELINE.md` section 6).
  - Otherwise "No `<field>`" when a column mapped to a required canonical
    field (`product_name`, `transaction_date`, `quantity`) has
    `drop_rows_missing` as its action and that row's "before" value for it is
    blank.
  - Otherwise "Dropped", with no further reason claimed (a duplicate whose
    pair fell outside the displayed 20 rows, or a non-required column with
    `drop_rows_missing`, are both real cases this cannot always resolve from
    what is on screen).

## 8. Handoff notes for developers

- Header and action bar on Review are fixed on scroll (set in Figma Prototype tab).
- Tinted fills (badge 12%, notice 8%, low-confidence row 8%) are the variable color
  at reduced opacity, not separate tokens. In CSS use color-mix or rgba.
- Results primary CTA is Run full analysis; Import to dashboard is secondary (guide
  asked for two primaries; one primary per screen keeps the next step obvious).
- Dashboard status thresholds used in mockups: critical <= 3 days, warning <= 14
  days to predicted stock-out. Not defined in SPECS; confirm before building.
- Return rate KPI: SPECS does not define how returns are identified
  (transaction_type is in|out = stock movement). Decide before Phase 6.

## 9. Design principles (agreed)

- Clarity over aesthetics: internal-tool feel, scannable tables, minimal clicks
- The Review screen is where the user spends most of their time: optimize for
  reading many columns quickly and editing with the fewest interactions
- The Insights page must make the causal chain visible: number -> cause -> action
- English UI copy only
