// The waterfall's geometry (the report redesign's step 5; report.html's html_svg.waterfall_chart): each part
// from where the last ended, last month's sales at zero, then the whole change - drawn from report.json's
// front.waterfall, whose bars are diagnosis.json's bridge (Q17: never a split the bridge withholds). Kept a
// plain function, as chartData.ts is: jsdom never draws the SVG, so the rule is tested here. Only geometry
// is added up; every figure printed is stage 5's own text.

import type { Factor, Waterfall } from '../types/reportFront.ts'

export interface WaterfallRow {
  // null: the whole change, the last bar.
  factor: Factor | null
  label: string
  // Low to high: Recharts draws an array value as a floating bar.
  range: [number, number]
  shown: number
  worth: string
}

function span(from: number, to: number): [number, number] {
  return from <= to ? [from, to] : [to, from]
}

export function waterfallRows(waterfall: Waterfall): WaterfallRow[] {
  const rows: WaterfallRow[] = []
  let level = 0
  for (const bar of waterfall.bars) {
    rows.push({ factor: bar.factor, label: bar.label, range: span(level, level + bar.shown), shown: bar.shown, worth: bar.worth })
    level += bar.shown
  }
  const current = waterfall.current_label.split(' ').slice(0, -2).join(' ')
  rows.push({
    factor: null,
    label: `Change to ${current}`,
    range: span(0, waterfall.shown_change),
    shown: waterfall.shown_change,
    worth: waterfall.change_text,
  })
  return rows
}
