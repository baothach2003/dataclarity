// The dashboard on Insights (report.json 2.10, 2.11; docs/DASHBOARD_DESIGN.md sections 1-3 and 10; Thach's D7 and
// his layout of 2026-10-15): pictures and figures, almost no text - the same block report.html draws
// (stages/report/html_dashboard.py). Row 1 the KPI tiles (label, figure, arrow, change); row 2 one short line;
// row 3 the chart cards in report.json's order; row 4 full-width bands - next month, the checked chips, the next
// step. A note stands where its figure is, as a marker (NoteMarker). Every long text is in Technical details
// (DashboardWords). The page decides no order and words no figure.

import type { ReactNode } from 'react'
import type { Chart, NoteCode } from '../types/report.ts'
import type { Chip, Dashboard, NextMonthBand, Tile, Widget } from '../types/reportDashboard.ts'
import type { Front } from '../types/reportFront.ts'
import { DashboardBars, DashboardParts } from './DashboardBars.tsx'
import { FrontSalesChart } from './FrontSalesChart.tsx'
import { FrontWaterfall } from './FrontWaterfall.tsx'
import { NoteMarker } from './NoteMarker.tsx'

const ARROWS: Record<NonNullable<Tile['direction']>, string> = { up: '▲', down: '▼', same: '●' }
const ARROW_WORDS: Record<NonNullable<Tile['direction']>, string> = {
  up: 'higher than last month',
  down: 'lower than last month',
  same: 'the same as last month',
}
// A chip's mark (report.html's _CHIP_MARKS): the check mark for "checked, not the reason".
const CHIP_MARKS: Record<Chip['status'], string> = {
  checked: '✓',
  matches: '●',
  moved: '↕',
  'other way': '⇄',
  "can't tell": '?',
  caution: '!',
}

interface DashboardSectionProps {
  dashboard: Dashboard
  front: Front
  // report.json's charts.revenue_trend, drawn by the trend widget.
  salesChart: Chart | undefined
  // Each note's sentence by its code (the report's own notes).
  noteTexts: ReadonlyMap<NoteCode, string>
}

function TileCard({ tile, noteTexts }: { tile: Tile; noteTexts: ReadonlyMap<NoteCode, string> }) {
  const arrow = tile.direction !== null && (
    <span className="tile__arrow" role="img" aria-label={ARROW_WORDS[tile.direction]}>
      {ARROWS[tile.direction]}
    </span>
  )
  const change = tile.change ?? (tile.was !== null ? `was ${tile.was}` : null)
  return (
    <div className="tile" data-testid={`tile-${tile.id}`}>
      <div className="tile__label">{tile.label}</div>
      {/* A figure, or the two words "not shown": its reason stands behind the marker. */}
      <div className="tile__value">{tile.now ?? 'not shown'}</div>
      {change !== null && (
        <div className="tile__change">
          {arrow} {change}
        </div>
      )}
      <NoteMarker about={tile.label} codes={tile.notes} asides={tile.reason ? [tile.reason] : []} texts={noteTexts} />
    </div>
  )
}

function ChartCard({ widget, front, salesChart, noteTexts }: { widget: Widget } & Omit<DashboardSectionProps, 'dashboard'>) {
  const title = widget.title ?? ''
  let asides = widget.caption
  let body: ReactNode
  switch (widget.id) {
    case 'trend':
      body = <FrontSalesChart chart={salesChart} title={title} notes={[]} showTitle={false} />
      break
    case 'waterfall':
      if (front.waterfall === null) {
        return null
      }
      // Its caption and note stand behind the card's marker.
      asides = [front.waterfall.caption, ...(front.waterfall.note ? [front.waterfall.note] : []), ...widget.caption]
      body = <FrontWaterfall waterfall={front.waterfall} inCard />
      break
    case 'customers':
    case 'products':
    case 'category':
    case 'breakdown_1':
    case 'breakdown_2':
    case 'returns':
      // Only a chart this page can draw: a widget of another shape is left out, never drawn as bars.
      if (!widget.chart || !['bars', 'diverging', 'parts'].includes(widget.chart)) {
        return null
      }
      body =
        widget.chart === 'parts' ? (
          <DashboardParts bars={widget.bars} title={title} />
        ) : (
          <DashboardBars bars={widget.bars} title={title} diverging={widget.chart === 'diverging'} />
        )
      break
    default:
      // A widget id this page does not know (a later, additive one) is left out.
      return null
  }
  return (
    <section className="card dashboard-widget" aria-label={title} data-testid={`widget-${widget.id}`}>
      <div className="dashboard-widget__head">
        <h2 className="front-card__title">{title}</h2>
        <NoteMarker about={title} codes={widget.notes} asides={asides} texts={noteTexts} />
      </div>
      <div className="dashboard-widget__body">
        {body}
      </div>
    </section>
  )
}

function NextMonth({ band, noteTexts }: { band: NextMonthBand; noteTexts: ReadonlyMap<NoteCode, string> }) {
  const line =
    band.figure !== null
      ? `${band.month ?? ''}: about ${band.figure} · likely ${band.low ?? ''} to ${band.high ?? ''}`
      : `Next month: ${band.reason ?? ''}`
  return (
    <section className="band" data-testid="band-next-month" aria-label="Next month">
      <h2 className="band__title">Next month</h2>
      <p className="band__line">{line}</p>
      <NoteMarker about="next month" codes={band.notes} asides={band.asides} texts={noteTexts} />
    </section>
  )
}

function Checked({ chips, notes, noteTexts }: { chips: Chip[]; notes: NoteCode[]; noteTexts: ReadonlyMap<NoteCode, string> }) {
  return (
    <section className="band" data-testid="band-checked" aria-label="Checked">
      <h2 className="band__title">Checked</h2>
      <ul className="chips">
        {chips.map((chip) => (
          <li key={chip.label} className={`chip chip--${chip.status.replaceAll(' ', '-').replaceAll("'", '')}`} data-status={chip.status}>
            <span aria-hidden="true">{CHIP_MARKS[chip.status]}</span> {chip.label}
            {chip.status === 'checked' ? (
              <span className="visually-hidden"> checked</span>
            ) : (
              <span className="chip__status"> {chip.status}</span>
            )}
          </li>
        ))}
      </ul>
      <NoteMarker about="what was checked" codes={notes} asides={[]} texts={noteTexts} />
    </section>
  )
}

function NextSteps({ steps, notes, noteTexts }: { steps: string[]; notes: NoteCode[]; noteTexts: ReadonlyMap<NoteCode, string> }) {
  return (
    <section className="band" data-testid="band-next-steps" aria-label="Next step">
      <h2 className="band__title">Next step</h2>
      <ul className="band__list">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
      <NoteMarker about="the next step" codes={notes} asides={[]} texts={noteTexts} />
    </section>
  )
}

export function DashboardSection({ dashboard, front, salesChart, noteTexts }: DashboardSectionProps) {
  const checked = dashboard.checked ?? []
  const steps = dashboard.next_steps ?? []
  return (
    <div className="dashboard" data-testid="dashboard">
      <div className="tiles">
        {dashboard.tiles.map((tile) => (
          <TileCard key={tile.id} tile={tile} noteTexts={noteTexts} />
        ))}
      </div>
      {dashboard.headline && (
        <div className="dashboard-headline" data-testid="dashboard-headline">
          <span className="dashboard-headline__text">{dashboard.headline.text}</span>
          <NoteMarker about="these sales figures" codes={dashboard.headline.notes} asides={dashboard.headline.asides} texts={noteTexts} />
        </div>
      )}
      <div className="dashboard-widgets">
        {dashboard.widgets
          .filter((widget) => widget.kind === 'chart')
          .map((widget) => (
            <ChartCard key={widget.id} widget={widget} front={front} salesChart={salesChart} noteTexts={noteTexts} />
          ))}
      </div>
      {dashboard.next_month && <NextMonth band={dashboard.next_month} noteTexts={noteTexts} />}
      {checked.length > 0 && <Checked chips={checked} notes={dashboard.checked_notes ?? []} noteTexts={noteTexts} />}
      {steps.length > 0 && <NextSteps steps={steps} notes={dashboard.next_steps_notes ?? []} noteTexts={noteTexts} />}
    </div>
  )
}
