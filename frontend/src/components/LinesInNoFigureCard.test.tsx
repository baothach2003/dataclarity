import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { makeReport } from '../pages/insightsFixture.ts'
import type { Numbers } from '../types/report.ts'
import { LinesInNoFigureCard } from './LinesInNoFigureCard.tsx'

afterEach(() => {
  cleanup()
})

const NUMBERS = makeReport().layer_1_numbers

function rows(name: string) {
  return within(screen.getByRole('table', { name }))
    .getAllByRole('row')
    .slice(1)
    .map((row) => [...row.querySelectorAll('th, td')].map((cell) => cell.textContent))
}

const WITH_LINES: Numbers = {
  ...NUMBERS,
  undated_lines: 14,
  undated_lines_reason: '14 lines carry no date the file can read, so no month counts them.',
  unmeasurable: [
    { scope: 'file', reason: 'no price', lines: 609 },
    { scope: 'current', reason: 'no quantity', lines: 19 },
    { scope: 'previous', reason: 'no price', lines: 24 },
  ],
  non_product: [
    { line_class: 'charge', lines: 40, amount: 600, amount_current: 210, amount_previous: 190, reason: 'a charge the customer paid stays in revenue but is no order' },
  ],
  outside_revenue: [
    { line_class: 'stock_in', scope: 'file', sign: 'positive', lines: 12, amount: 8400, lines_without_amount: 2 },
    { line_class: 'stock_in', scope: 'previous', sign: 'positive', lines: 3, amount: 2100, lines_without_amount: 0 },
  ],
}

// The design gap review's ADD 9: the lines no figure counts, and the money of
// the classes that is not product revenue - each with its reason, never
// dropped silently (CONTRACTS 6) - as stage 5 tells them (html_report._other_lines).
describe('LinesInNoFigureCard', () => {
  it('is not shown when every line is in a figure', () => {
    render(<LinesInNoFigureCard numbers={NUMBERS} />)

    expect(screen.queryByRole('heading')).toBeNull()
  })

  it('lists the undated, the unmeasurable, the classes given and the lines outside revenue', () => {
    render(<LinesInNoFigureCard numbers={WITH_LINES} />)

    expect(screen.getByRole('heading', { name: 'Lines in no figure, and where their money went' })).toBeDefined()
    expect(screen.getByText('14 lines carry no date the file can read, so no month counts them.')).toBeDefined()
    expect(rows('Lines that cannot be measured')).toEqual([
      ['whole file', 'no price', '609'],
      ['June 2026', 'no quantity', '19'],
      ['May 2026', 'no price', '24'],
    ])
    expect(rows('Lines of the classes you gave')).toEqual([
      ['charge', '40', '600.00', '210.00', '190.00', 'a charge the customer paid stays in revenue but is no order'],
    ])
    expect(rows('Lines outside revenue')).toEqual([
      ['stock_in', 'whole file', 'positive', '12', '8,400.00', '2'],
      ['stock_in', 'May 2026', 'positive', '3', '2,100.00', '0'],
    ])
  })

  // The design gap review's ADD 9 lists them here; why is said beside the dates
  // covered, at the top (the 6E3 review #5).
  it('counts the lines dated after the upload among the lines in no figure', () => {
    render(<LinesInNoFigureCard numbers={{ ...NUMBERS, future_lines: 3, future_lines_reason: '3 lines are dated after the upload.' }} />)

    expect(screen.getByText('3 lines are dated after the upload, so no figure counts them; why is said beside the dates the file covers, at the top.')).toBeDefined()
  })

  it("never shows a previous month's lines or amounts when that month is not compared", () => {
    const numbers: Numbers = { ...WITH_LINES, period: { ...WITH_LINES.period, previous_complete: false, previous_incomplete_reason: 'cut short' } }
    render(<LinesInNoFigureCard numbers={numbers} />)

    expect(rows('Lines that cannot be measured').map((row) => row[0])).toEqual(['whole file', 'June 2026'])
    expect(rows('Lines of the classes you gave')[0]?.[4]).toBe('not compared (see above)')
    expect(rows('Lines outside revenue').map((row) => row[1])).toEqual(['whole file'])
  })

  it("says a withheld month's amount is withheld, never its 0", () => {
    const numbers: Numbers = {
      ...WITH_LINES,
      kpis: WITH_LINES.kpis.map((kpi) => ({ ...kpi, current: null, current_reason: 'No line counted in revenue is dated in 2026-06.' })),
      non_product: WITH_LINES.non_product.map((row) => ({ ...row, amount_current: 0 })),
    }
    render(<LinesInNoFigureCard numbers={numbers} />)

    expect(rows('Lines of the classes you gave')[0]?.[3]).toBe("withheld, with the current month's figures")
  })
})
