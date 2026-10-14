// The dashboard on Insights (report.json 2.10; docs/DASHBOARD_DESIGN.md; Thach's D7): the KPI tiles, the caution
// lines under them, then report.json's widgets in the order stage 5 decided - the same block report.html draws
// (stages/report/html_dashboard.py). The page decides no order and words no figure: each tile prints stage 5's
// text, each chart draws report.json's bars or its own chart, each text widget is the front section's own part.

import type { ReactNode } from 'react'
import type { NoteCode, Chart } from '../types/report.ts'
import type { Dashboard, Tile, Widget } from '../types/reportDashboard.ts'
import type { Front } from '../types/reportFront.ts'
import { DashboardBars, DashboardParts } from './DashboardBars.tsx'
import { FrontReadWith } from './FrontReadWith.tsx'
import {
  FrontCannotKnowBody,
  FrontCard,
  FrontChangeBody,
  FrontCheckedBody,
  FrontNextMonthBody,
  FrontNextStepsBody,
  FrontSummaryBody,
} from './FrontSection.tsx'
import { FrontSalesChart } from './FrontSalesChart.tsx'

const ARROWS: Record<NonNullable<Tile['direction']>, string> = { up: '▲', down: '▼', same: '●' }
const ARROW_WORDS: Record<NonNullable<Tile['direction']>, string> = {
  up: 'higher than last month',
  down: 'lower than last month',
  same: 'the same as last month',
}
const TEXT_TITLES: Partial<Record<Widget['id'], string>> = {
  summary: 'In short',
  checklist: 'What was checked',
  next_steps: 'What to do next',
  next_month: 'Next month',
  cannot_know: 'What this report cannot know',
}

interface DashboardSectionProps {
  dashboard: Dashboard
  front: Front
  // report.json's charts.revenue_trend, drawn by the trend widget.
  salesChart: Chart | undefined
  // "November 2024": the month a tile's "was" is about.
  previousMonth: string
  onOpenNote: (code: NoteCode) => void
}

function TileCard({ tile, previousMonth, onOpenNote }: { tile: Tile; previousMonth: string; onOpenNote: (code: NoteCode) => void }) {
  const arrow = tile.direction !== null && (
    <span className="tile__arrow" role="img" aria-label={ARROW_WORDS[tile.direction]}>
      {ARROWS[tile.direction]}
    </span>
  )
  return (
    <div className="tile" data-testid={`tile-${tile.id}`}>
      <p className="tile__label">{tile.label}</p>
      {tile.now !== null && <p className="tile__value">{tile.now}</p>}
      {tile.change !== null && (
        <p className="tile__change">
          {arrow} {tile.change}
        </p>
      )}
      {tile.change === null && tile.was !== null && (
        <p className="tile__change">
          {arrow} {`was ${tile.was} in ${previousMonth}`}
        </p>
      )}
      {tile.reason !== null && <p className="tile__change">{tile.reason}</p>}
      <FrontReadWith codes={tile.notes} onOpen={onOpenNote} />
    </div>
  )
}

function WidgetCard({ widget, front, salesChart, onOpenNote }: { widget: Widget } & Omit<DashboardSectionProps, 'dashboard' | 'previousMonth'>) {
  const title = widget.title ?? TEXT_TITLES[widget.id] ?? ''
  const notes = <FrontReadWith codes={widget.notes} onOpen={onOpenNote} />
  // Every widget's caption after its body, as report.html's _widget prints it.
  const captions = widget.caption.map((line, index) => (
    // Two lines may read alike; their place is their identity.
    <p className="front__small" key={index}>
      {line}
    </p>
  ))
  let body: ReactNode
  switch (widget.id) {
    case 'summary':
      body = <FrontSummaryBody front={front} onOpenNote={onOpenNote} withCaution={false} />
      break
    case 'checklist':
      body = <FrontCheckedBody front={front} onOpenNote={onOpenNote} />
      break
    case 'next_steps':
      body = <FrontNextStepsBody front={front} onOpenNote={onOpenNote} />
      break
    case 'next_month':
      body = <FrontNextMonthBody front={front} onOpenNote={onOpenNote} />
      break
    case 'cannot_know':
      body = <FrontCannotKnowBody front={front} />
      break
    case 'trend':
      // The chart; its part-month and gap sentences are the caption, printed even when no month can be drawn.
      body = <FrontSalesChart chart={salesChart} title={title} notes={[]} showTitle={false} />
      break
    case 'waterfall':
      body = <FrontChangeBody front={front} onOpenNote={onOpenNote} />
      break
    case 'customers':
    case 'products':
    case 'category':
    case 'breakdown_1':
    case 'breakdown_2':
    case 'returns':
      // Only a chart this page can draw: a widget of another shape is left out, never drawn as bars.
      if (widget.kind !== 'chart' || !widget.chart || !['bars', 'diverging', 'parts'].includes(widget.chart)) {
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
  const isTextPart = widget.kind === 'text' || widget.id === 'waterfall'
  return (
    <FrontCard title={title} className={`dashboard-widget dashboard-widget--${widget.kind}`}>
      <div data-testid={`widget-${widget.id}`} className="dashboard-widget__body">
        {body}
        {captions}
        {/* A text part and the waterfall print their own notes line (the front's); a chart prints the widget's. */}
        {!isTextPart && notes}
      </div>
    </FrontCard>
  )
}

export function DashboardSection({ dashboard, front, salesChart, previousMonth, onOpenNote }: DashboardSectionProps) {
  return (
    <>
      <div className="dashboard-tiles">
        <div className="tiles">
          {dashboard.tiles.map((tile) => (
            <TileCard key={tile.id} tile={tile} previousMonth={previousMonth} onOpenNote={onOpenNote} />
          ))}
        </div>
        {dashboard.not_shown.map((line, index) => (
          // Two lines may read alike; their place is their identity.
          <p className="front__small" key={index}>
            {line}
          </p>
        ))}
        {dashboard.caution.map((line, index) => (
          <p className="front__caution" key={index}>
            {line}
          </p>
        ))}
      </div>
      <div className="dashboard-widgets">
        {dashboard.widgets.map((widget) => (
          <WidgetCard key={widget.id} widget={widget} front={front} salesChart={salesChart} onOpenNote={onOpenNote} />
        ))}
      </div>
    </>
  )
}
