import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { makeReport, SAME_DAY_TEXT } from '../pages/insightsFixture.ts'
import type { Chart, Numbers } from '../types/report.ts'
import { RevenueChartCard } from './RevenueChartCard.tsx'

afterEach(() => {
  cleanup()
})

const REPORT = makeReport()
const CHART = REPORT.charts.find((chart) => chart.id === 'revenue_trend') as Chart

// null: a report that draws no chart (undefined would take the default).
function show(chart: Chart | null = CHART, numbers: Numbers = REPORT.layer_1_numbers) {
  return render(<RevenueChartCard chart={chart ?? undefined} numbers={numbers} notes={numbers.notes} />)
}

function tableRows() {
  return within(screen.getByRole('table', { name: 'Revenue by month' }))
    .getAllByRole('row')
    .slice(1)
    .map((row) => [...row.querySelectorAll('th, td')].map((cell) => cell.textContent))
}

// The design gap review's ADD 8: revenue by month - months drawn whole only
// when complete, a gap with its reason (never a zero or a join) - as report.json
// draws it (charts.revenue_trend) and stage 5 tells it (html_report._chart).
describe('RevenueChartCard', () => {
  it('draws the chart and gives its figures as a table', () => {
    show()

    expect(screen.getByRole('heading', { name: 'Revenue by month' })).toBeDefined()
    expect(screen.getByRole('img', { name: 'Revenue by month, drawn as a line: the table below gives every figure' })).toBeDefined()
    expect(tableRows()).toEqual([
      ['April 2026', '101,200.00', 'yes'],
      ['May 2026', '104,160.00', 'yes'],
      ['June 2026', '96,152.00', 'yes'],
    ])
  })

  it("says each caution once - not when the gap's own note already says it", () => {
    show({ ...CHART, note: 'About 5 days in the current month have no sales, so it is drawn as it stands.' })

    expect(screen.getByText('About 5 days in the current month have no sales, so it is drawn as it stands.')).toBeDefined()
    expect(screen.queryByText(/^Caution:/)).toBeNull()
    cleanup()

    show()
    expect(screen.getByText('Caution: About 5 days in the current month have no sales.')).toBeDefined()
  })

  it('tells a month with no revenue and the compared month not compared by their reasons, never as 0', () => {
    const numbers: Numbers = {
      ...REPORT.layer_1_numbers,
      period: { ...REPORT.layer_1_numbers.period, previous_complete: false, previous_incomplete_reason: 'cut short' },
      revenue_by_month: [
        { period: '2026-04', revenue: null, revenue_reason: 'a closed month or missing data, which the file cannot tell apart', complete: false },
        { period: '2026-05', revenue: 50000, revenue_reason: null, complete: false },
        { period: '2026-06', revenue: 96152, revenue_reason: null, complete: true },
      ],
    }
    show({ ...CHART, series: [{ name: 'revenue', x: ['2026-06'], y: [96152] }] }, numbers)

    expect(tableRows()).toEqual([
      ['April 2026', 'a closed month or missing data, which the file cannot tell apart', 'no'],
      ['May 2026', 'not compared (see above)', 'no'],
      ['June 2026', '96,152.00', 'yes'],
    ])
  })

  it('says so, with no empty chart, when there is no month to draw', () => {
    show({ ...CHART, series: [{ name: 'revenue', x: [], y: [] }], note: 'No complete month with revenue to draw.' })

    expect(screen.getByText('No complete month with revenue to draw.')).toBeDefined()
    expect(screen.queryByRole('img')).toBeNull()
  })

  // contracts/report.py allows a report with no revenue chart; the months stand
  // in the table, as report.html keeps its month table (the 6E3 review #6).
  it('still gives every month as a table when the report draws no chart', () => {
    show(null)

    expect(screen.getByRole('heading', { name: 'Revenue by month' })).toBeDefined()
    expect(screen.queryByRole('img')).toBeNull()
    expect(tableRows()).toHaveLength(3)
  })

  it('shows the notes naming revenue beside the chart', () => {
    const numbers = REPORT.layer_1_numbers
    show({ ...CHART, notes: ['same_day_cancellations'] }, numbers)

    expect(screen.getByText('Notes on these figures (1)')).toBeDefined()
    expect(screen.getByText(SAME_DAY_TEXT)).toBeDefined()
  })
})
