// The rows the Insights charts are drawn from (report.json's charts), kept here as plain functions -
// jsdom never draws the SVG, so the rules are tested on these (the 6E3 review #3). A month not drawn
// stays null: a gap, never a zero and never joined across (CONTRACTS 11).

import { monthLabel } from './reportFormat.ts'
import type { Chart } from '../types/report.ts'

export interface RevenueRow {
  month: string
  revenue: number | null
}

export interface ForecastRow {
  month: string
  point: number
  // Low to high, one range area (Recharts draws an array value as a range).
  band: [number, number]
}

/** revenue_trend's one series, month by month; nothing to draw when no month has a figure. */
export function revenueRows(chart: Chart): RevenueRow[] {
  const series = chart.series.at(0)
  if (!series) {
    return []
  }
  const rows = series.x.map((month, index) => ({ month: monthLabel(month), revenue: series.y[index] ?? null }))
  return rows.some((row) => row.revenue !== null) ? rows : []
}

/** The forecast chart's own point, low and high series, month by month - as report.html draws it (the
 * 6E3 review #7): a month missing any of the three is not drawn. */
export function forecastRows(chart: Chart): ForecastRow[] {
  const named = (name: string) => chart.series.find((series) => series.name === name)
  const point = named('point')
  const low = named('low')
  const high = named('high')
  if (!point || !low || !high) {
    return []
  }
  const rows: ForecastRow[] = []
  point.x.forEach((month, index) => {
    const value = point.y[index]
    const lower = low.y[low.x.indexOf(month)]
    const upper = high.y[high.x.indexOf(month)]
    if (typeof value === 'number' && typeof lower === 'number' && typeof upper === 'number') {
      rows.push({ month: monthLabel(month), point: value, band: [lower, upper] })
    }
  })
  return rows
}

/** Each caution said once: not when the chart's note already says it (stage 5, 5B review 2 #11), and
 * not twice from the list. */
export function cautionsToSay(chart: Chart): string[] {
  const note = chart.note?.toLowerCase()
  const said = chart.cautions.filter((caution) => !(note && note.includes(caution.replace(/\.+$/, '').toLowerCase())))
  return [...new Set(said)]
}
