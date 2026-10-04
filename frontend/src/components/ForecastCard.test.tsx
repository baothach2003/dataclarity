import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { makeReport, SAME_DAY_TEXT } from '../pages/insightsFixture.ts'
import type { Chart, ForecastView } from '../types/report.ts'
import { ForecastCard } from './ForecastCard.tsx'

afterEach(() => {
  cleanup()
})

const REPORT = makeReport()
const FORECAST = REPORT.layer_3_actions.forecast
const CHART = REPORT.charts.find((chart) => chart.id === 'forecast') as Chart

const PERIOD = REPORT.layer_1_numbers.period

function show(forecast: ForecastView = FORECAST, chart: Chart | undefined = CHART, period = PERIOD) {
  return render(<ForecastCard forecast={forecast} chart={chart} notes={REPORT.layer_1_numbers.notes} period={period} />)
}

// The design gap review: the forecast is MONTHLY, 3 months ahead, with an 80%
// band (not "weekly"), its method, the notes below; "Insufficient History"
// (frame 4:1814) counts complete MONTHS, not "periods". As stage 5 tells it
// (html_report._actions).
describe('ForecastCard', () => {
  it('names the method and the months it learned from, and gives each month with its band', () => {
    show()

    expect(screen.getByRole('heading', { name: 'Revenue forecast' })).toBeDefined()
    expect(screen.getByText('Method: weighted moving average of the last 3 complete months (weights 1, 2, 3), no seasonality claimed. Learned from 3 complete months.')).toBeDefined()
    const table = screen.getByRole('table', { name: "Low and high: the 80% band, from the method's own past errors" })
    expect(within(table).getAllByRole('row').slice(1).map((row) => [...row.querySelectorAll('th, td')].map((cell) => cell.textContent))).toEqual([
      ['July 2026', '99,662.00', '90,100.00', '109,200.00'],
      ['August 2026', '99,662.00', '88,900.00', '110,400.00'],
      ['September 2026', '99,662.00', '87,500.00', '111,800.00'],
    ])
    expect(screen.getByRole('img', { name: 'Revenue forecast, drawn with its 80% band: the table gives every figure' })).toBeDefined()
    expect(screen.getByText('Caution: About 5 days in the current month have no sales.')).toBeDefined()
  })

  it('shows its own notes, once', () => {
    show({ ...FORECAST, history_note: 'The history has a gap: 2026-02 has no line counted in revenue.', season_note: 'No season is claimed: fewer than two years of history.' })

    expect(screen.getAllByText('The history has a gap: 2026-02 has no line counted in revenue.')).toHaveLength(1)
    expect(screen.getByText('No season is claimed: fewer than two years of history.')).toBeDefined()
  })

  // "The dates the file covers": lines dated after the upload are in no figure,
  // so "the file ends" could be false (the 6E3 review #10).
  it('never compares a month the file already holds with the forecast', () => {
    const period = { ...PERIOD, data_end: '2026-07-12' }
    show({ ...FORECAST, first_month_in_file: true, partial_first_month_until: '2026-07-12' }, CHART, period)
    expect(screen.getByText("The dates the file covers end on 2026-07-12, part-way through July 2026: that month's revenue so far is not compared with the forecast.")).toBeDefined()
    cleanup()

    show({ ...FORECAST, first_month_in_file: true, partial_first_month_until: null }, CHART, period)
    expect(screen.getByText("The file already holds a line for July 2026: its revenue so far is not compared with the forecast.")).toBeDefined()
  })

  it('says how many complete months it had and needs when the history is too short', () => {
    show({ ...FORECAST, insufficient_history: true, months_used: 2, points: [], history_note: null }, undefined)

    expect(screen.getByText('Not enough history to forecast yet')).toBeDefined()
    expect(screen.getByText('There is too little history for a forecast: 2 complete months, and 3 are needed.')).toBeDefined()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('counts one complete month as one', () => {
    show({ ...FORECAST, insufficient_history: true, months_used: 1, points: [] }, undefined)

    expect(screen.getByText('There is too little history for a forecast: 1 complete month, and 3 are needed.')).toBeDefined()
  })

  // The design gap review's Forecast CHANGE: its season_years, which a reader
  // decides on - never the note's sentence (CONTRACTS 9; the 6E3 review #2).
  it('says how many years a claimed season is read from', () => {
    show({ ...FORECAST, season_years: 3, method: 'weighted moving average of the last 3 complete months (weights 1, 2, 3), with a monthly seasonality index' })

    expect(screen.getByText('The season is read from 3 years of history.')).toBeDefined()
  })

  it('skips a blank note (contracts/forecast.py: a blank note is no note)', () => {
    show({ ...FORECAST, season_note: '   ' })

    expect([...document.querySelectorAll('.insights-reason')].every((p) => p.textContent.trim() !== '')).toBe(true)
  })

  it('shows the notes naming revenue beside the forecast (CONTRACTS 11)', () => {
    show(FORECAST, { ...CHART, notes: ['same_day_cancellations'] })

    expect(screen.getByText('Notes on these figures (1)')).toBeDefined()
    expect(screen.getByText(SAME_DAY_TEXT)).toBeDefined()
  })
})
