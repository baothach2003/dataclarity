import { describe, expect, it } from 'vitest'
import { makeReport } from '../pages/insightsFixture.ts'
import type { Chart } from '../types/report.ts'
import { cautionsToSay, forecastRows, revenueRows } from './chartData.ts'

const REPORT = makeReport()
const REVENUE = REPORT.charts.find((chart) => chart.id === 'revenue_trend') as Chart
const FORECAST = REPORT.charts.find((chart) => chart.id === 'forecast') as Chart

// The rows the charts are drawn from (jsdom never draws the SVG, so the rules
// live here, tested): a month not drawn stays a gap - never a zero, never a
// join (CONTRACTS 11; the 6E3 review #3).
describe('revenueRows', () => {
  it('keeps a null month null, labelled by its month', () => {
    const rows = revenueRows({ ...REVENUE, series: [{ name: 'revenue', x: ['2026-04', '2026-05', '2026-06'], y: [101200, null, 96152] }] })

    expect(rows).toEqual([
      { month: 'April 2026', revenue: 101200 },
      { month: 'May 2026', revenue: null },
      { month: 'June 2026', revenue: 96152 },
    ])
  })

  it('has nothing to draw for an empty series, or one with no figure (the 6E3 review #14)', () => {
    expect(revenueRows({ ...REVENUE, series: [] })).toEqual([])
    expect(revenueRows({ ...REVENUE, series: [{ name: 'revenue', x: [], y: [] }] })).toEqual([])
    expect(revenueRows({ ...REVENUE, series: [{ name: 'revenue', x: ['2026-05'], y: [null] }] })).toEqual([])
  })
})

// The forecast is drawn from the chart's own series, as report.html draws it -
// nothing when the chart has no month (the 6E3 review #7).
describe('forecastRows', () => {
  it('pairs each month with its point, low and high', () => {
    expect(forecastRows(FORECAST)).toEqual([
      { month: 'July 2026', point: 99662, band: [90100, 109200] },
      { month: 'August 2026', point: 99662, band: [88900, 110400] },
      { month: 'September 2026', point: 99662, band: [87500, 111800] },
    ])
  })

  it('draws nothing from a chart with no month', () => {
    expect(forecastRows({ ...FORECAST, series: FORECAST.series.map((s) => ({ ...s, x: [], y: [] })) })).toEqual([])
  })
})

describe('cautionsToSay', () => {
  it("says each caution once - not when the chart's note already says it", () => {
    expect(cautionsToSay({ ...REVENUE, note: 'About 5 days in the current month have no sales, so it is drawn as it stands.' })).toEqual([])
    expect(cautionsToSay(REVENUE)).toEqual(['About 5 days in the current month have no sales.'])
  })

  it('says a caution repeated in the list once', () => {
    expect(cautionsToSay({ ...REVENUE, cautions: ['A gap.', 'A gap.'] })).toEqual(['A gap.'])
  })
})
