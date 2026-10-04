import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { makeReport, SAME_DAY_TEXT } from '../pages/insightsFixture.ts'
import type { Kpi } from '../types/report.ts'
import { KpiCard } from './KpiCard.tsx'

afterEach(() => {
  cleanup()
})

const NUMBERS = makeReport().layer_1_numbers
const [REVENUE, ORDERS, CUSTOMERS, , RETURN_RATE] = NUMBERS.kpis as [Kpi, Kpi, Kpi, Kpi, Kpi]
const PERIOD = NUMBERS.period

// The KPI card (FIGMA_DESIGN_NOTES 1:570) with the design gap decisions: the
// change on revenue only, every other card its previous value (CONTRACTS 11:
// "no other change is computed"); a null figure shows its reason, never a zero;
// notes are a marker that reveals them, not inline text.
describe('KpiCard', () => {
  it("shows revenue's value, its change and the previous month's value", () => {
    render(<KpiCard kpi={REVENUE} period={PERIOD} notes={NUMBERS.notes} />)

    expect(screen.getByText('Revenue')).toBeDefined()
    expect(screen.getByText('96,152.00')).toBeDefined()
    expect(screen.getByText('-7.7%')).toBeDefined()
    expect(screen.getByText('vs May 2026')).toBeDefined()
    expect(screen.getByText('May 2026: 104,160.00')).toBeDefined()
    expect(document.querySelector('.kpi-card__change--down svg')).not.toBeNull()
  })

  // The 6E1 review (#3): the arrow is a sign - none on a change that prints as zero.
  it('shows no arrow or colour on a change that prints as zero', () => {
    render(<KpiCard kpi={{ ...REVENUE, change_pct: 0.04 }} period={PERIOD} notes={[]} />)

    expect(screen.getByText('0.0%')).toBeDefined()
    expect(document.querySelector('.kpi-card__change--flat')).not.toBeNull()
    expect(document.querySelector('.kpi-card__change svg')).toBeNull()
  })

  it('shows any other figure beside its previous value, with no change', () => {
    render(<KpiCard kpi={ORDERS} period={PERIOD} notes={NUMBERS.notes} />)

    expect(screen.getByText('2,380')).toBeDefined()
    expect(screen.getByText('May 2026: 2,604')).toBeDefined()
    expect(screen.queryByText(/%/)).toBeNull()
  })

  // The 6E1 review (#16): stage 5 gives the change the current month's own reason.
  it('shows a withheld figure as its reason, once, never a zero', () => {
    const reason = 'No line counted in revenue is dated in 2026-06: a closed month or missing data, which the file cannot tell apart.'
    render(
      <KpiCard
        kpi={{ ...REVENUE, current: null, change_pct: null, current_reason: reason, change_reason: reason }}
        period={PERIOD}
        notes={[]}
      />,
    )

    expect(screen.getAllByText(reason)).toHaveLength(1)
    expect(screen.queryByText('0.00')).toBeNull()
  })

  it('never shows a previous value or a change beside an incomplete previous month', () => {
    const reason = 'The file starts on 2026-05-12, after 2026-05 began.'
    const period = { ...PERIOD, previous_complete: false, previous_incomplete_reason: reason }
    const kpi: Kpi = { ...REVENUE, previous: null, change_pct: null, previous_reason: reason, change_reason: reason }
    render(<KpiCard kpi={kpi} period={period} notes={[]} />)

    expect(screen.getByText('May 2026: not compared (see below)')).toBeDefined()
    expect(screen.queryByText(/104,160/)).toBeNull()
    expect(screen.queryByText(/%/)).toBeNull()
  })

  it('shows a previous figure withheld for its own reason', () => {
    const kpi: Kpi = { ...ORDERS, previous: null, previous_reason: 'No line in 2026-05 names an order.' }
    render(<KpiCard kpi={kpi} period={PERIOD} notes={[]} />)

    expect(screen.getByText('May 2026: No line in 2026-05 names an order.')).toBeDefined()
  })

  it('reveals the notes it names from a marker, every measure with its orders and keys', () => {
    render(<KpiCard kpi={RETURN_RATE} period={PERIOD} notes={NUMBERS.notes} />)
    const marker = screen.getByRole('button', { name: 'Notes on Return rate' })
    const panel = document.getElementById(marker.getAttribute('aria-controls') ?? '')

    // The panel the marker controls always exists; it is hidden until opened (6E1 review #11).
    expect(panel?.hidden).toBe(true)
    expect(marker.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(marker)
    expect(marker.getAttribute('aria-expanded')).toBe('true')
    expect(panel?.hidden).toBe(false)
    expect(screen.getByText(SAME_DAY_TEXT)).toBeDefined()
    expect(screen.getByText('returns, June 2026: 12 lines, -480.00, 7 orders')).toBeDefined()
    expect(screen.getByText('sales, June 2026: 12 lines, 480.00')).toBeDefined()
    expect(screen.getByText('returns_unchecked, June 2026: 3 lines')).toBeDefined()
    expect(screen.getByText('returns, May 2026: 9 lines, -300.00, 7 orders')).toBeDefined()
  })

  it("shows no previous month's measure when that month is not compared", () => {
    const period = { ...PERIOD, previous_complete: false, previous_incomplete_reason: 'cut short' }
    render(<KpiCard kpi={{ ...RETURN_RATE, previous: null, previous_reason: 'cut short' }} period={period} notes={NUMBERS.notes} />)
    fireEvent.click(screen.getByRole('button', { name: 'Notes on Return rate' }))

    expect(screen.getByText('returns, June 2026: 12 lines, -480.00, 7 orders')).toBeDefined()
    expect(screen.queryByText(/May 2026: 9 lines/)).toBeNull()
  })

  it('has no marker when it names no note', () => {
    render(<KpiCard kpi={REVENUE} period={PERIOD} notes={NUMBERS.notes} />)

    expect(screen.queryByRole('button')).toBeNull()
  })

  // The design gap review's ADD 6: unconfirmed walk-in candidates are marked
  // beside the customer figure; the reason is said under the KPI row.
  it('marks the customer figure when walk-in candidates were not confirmed', () => {
    render(<KpiCard kpi={CUSTOMERS} period={PERIOD} notes={NUMBERS.notes} unconfirmedWalkIns />)

    expect(screen.getByText('includes possible walk-ins not confirmed (see below)')).toBeDefined()
  })
})
