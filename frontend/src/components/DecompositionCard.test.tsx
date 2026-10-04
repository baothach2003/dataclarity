import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { readDiagnosis } from '../domain/diagnosisView.ts'
import { makeDiagnosis } from '../pages/diagnosisFixture.ts'
import { makeReport } from '../pages/insightsFixture.ts'
import type { Numbers } from '../types/report.ts'
import { DecompositionCard } from './DecompositionCard.tsx'

afterEach(() => {
  cleanup()
})

const NUMBERS = makeReport().layer_1_numbers

function show(diagnosis: unknown = makeDiagnosis(), numbers: Numbers = NUMBERS, ordersBasis: 'order_id' | 'lines' | null = 'order_id') {
  return render(<DecompositionCard view={readDiagnosis(diagnosis)} numbers={numbers} ordersBasis={ordersBasis} notes={numbers.notes} />)
}

function factorRows() {
  return screen.getAllByTestId('factor').map((row) => [...row.querySelectorAll('[data-cell]')].map((cell) => cell.textContent))
}

// "Where the revenue change came from" (frame 4:1489; the design gap review:
// "matches", with the labels of a file without order numbers, a tree that can
// be null, and a level 2). Stage 3's lever tree as diagnosis.json has it
// (CONTRACTS 11's FE rows): each factor's two months and its contribution; the
// page computes nothing - revenue's two months and change are the KPI's.
describe('DecompositionCard', () => {
  it("shows each factor's two months and its contribution, and revenue's", () => {
    show()

    expect(screen.getByRole('heading', { name: 'Where the revenue change came from' })).toBeDefined()
    // Stage 3 counts BUYERS (a sale row), not the KPI's active customers (the 6E2 review #1).
    expect(factorRows()).toEqual([
      ['Customers who bought', '1,225 → 1,101', '-10,752.00'],
      ['Orders per customer who bought', '2.10 → 2.14', '+1,792.00'],
      ['Average order value', '40.00 → 40.40', '+952.00'],
    ])
    const total = screen.getByTestId('decomposition-total')
    expect(within(total).getByText('Revenue')).toBeDefined()
    expect(within(total).getByText('104,160.00 → 96,152.00')).toBeDefined()
    expect(within(total).getByText('-7.7%')).toBeDefined()
  })

  it('draws each bar to scale, the largest the full half-track, by its sign', () => {
    show()
    const bars = [...document.querySelectorAll<HTMLElement>('.decomposition__bar')]

    expect(bars.map((bar) => bar.style.width)).toEqual(['100%', '16.7%', '8.9%'])
    expect(bars.map((bar) => bar.classList.contains('decomposition__bar--down'))).toEqual([true, false, false])
  })

  // The browser check (Kaggle demo: customers 25 -> 25): a contribution that
  // prints as zero carries no direction - no colour, no bar.
  it('gives a zero contribution no direction', () => {
    const diagnosis = makeDiagnosis()
    const level1 = (diagnosis.tree as { lever: { level1: { factors: { contribution: number }[] } } }).lever.level1
    const [first] = level1.factors
    first.contribution = -0.001
    show(diagnosis)
    const [row] = screen.getAllByTestId('factor')

    expect(row.querySelector('.decomposition__amount')?.className).toBe('decomposition__amount decomposition__amount--flat')
    expect(row.querySelector('.decomposition__amount')?.textContent).toBe('0.00')
    expect(row.querySelector('.decomposition__bar')).toBeNull()
  })

  it('names the factors of a file without order numbers as lines (CONTRACTS 6)', () => {
    show(makeDiagnosis(), NUMBERS, 'lines')

    expect(factorRows().map((row) => row[0])).toEqual(['Customers who bought', 'Lines per customer who bought', 'Average line value'])
  })

  it('is not shown when the order basis is unread - it names no factor by a guess', () => {
    show(makeDiagnosis(), NUMBERS, null)

    expect(screen.queryByRole('heading', { name: 'Where the revenue change came from' })).toBeNull()
  })

  // CLAUDE.md 3.3a and the design gap review's ADD 6: the figures stage 3
  // counted with unconfirmed walk-ins are marked here too; the notes that name
  // these figures stand beside them (the 6E2 review #5).
  it('marks the customer figures that count unconfirmed walk-ins, and shows the notes naming them', () => {
    const numbers = { ...NUMBERS, unconfirmed_placeholders_reason: '"Guest" may stand for walk-in customers.' }
    show(makeDiagnosis(), numbers)
    const [customers] = screen.getAllByTestId('factor')

    expect(customers.textContent).toContain('includes possible walk-ins not confirmed (see above)')
    expect(screen.getByText('Notes on these figures (1)')).toBeDefined()
  })

  it("shows the masked shift's pair, which the headline cites, when its alert is on", () => {
    const diagnosis = makeDiagnosis()
    const tree = diagnosis.tree as { lever: Record<string, unknown> }
    tree.lever = {
      ...tree.lever,
      masked_shift_alert: true,
      masked_shift_pair: {
        formula: 'orders*aov',
        factors: [
          { name: 'orders', value_prev: 2604, value_cur: 2380, contribution: -9000 },
          { name: 'aov', value_prev: 40, value_cur: 40.4, contribution: 8900 },
        ],
      },
    }
    show(diagnosis)

    expect(screen.getByText('The same change as orders × average order value')).toBeDefined()
    expect(factorRows().slice(3)).toEqual([
      ['Orders', '2,604 → 2,380', '-9,000.00'],
      ['Average order value', '40.00 → 40.40', '+8,900.00'],
    ])
  })

  it("says why revenue's change is missing when it is", () => {
    const numbers = { ...NUMBERS, kpis: NUMBERS.kpis.map((kpi) => (kpi.id === 'revenue' ? { ...kpi, change_pct: null, change_reason: 'no change is computed from a month of 0' } : kpi)) }
    show(makeDiagnosis(), numbers)

    expect(within(screen.getByTestId('decomposition-total')).getByText('no change is computed from a month of 0')).toBeDefined()
  })

  it('shows the second level when stage 3 split the average order', () => {
    const diagnosis = makeDiagnosis()
    const tree = diagnosis.tree as { lever: Record<string, unknown> }
    tree.lever.level2 = {
      formula: 'units_per_order*price_per_unit',
      factors: [
        { name: 'units_per_order', value_prev: 3.2, value_cur: 3.3, contribution: 700 },
        { name: 'price_per_unit', value_prev: 12.5, value_cur: 12.24, contribution: 252 },
      ],
    }
    show(diagnosis)

    expect(screen.getByText('Average order value, split')).toBeDefined()
    expect(factorRows().slice(3)).toEqual([
      ['Units per order', '3.20 → 3.30', '+700.00'],
      ['Price per unit', '12.50 → 12.24', '+252.00'],
    ])
  })

  // The design gap review's ADD 12: the calendar effect as a caption.
  // An estimate, signed (the 6E2 review #4).
  it('says what the calendar alone predicts, signed, and the change net of it', () => {
    show()

    expect(screen.getByText('By the calendar alone (which weekdays each month had), revenue would be expected to change by -1,300.00; net of that, the change is -6,708.00.')).toBeDefined()
  })

  it('says nothing of the calendar for a file that records months, not days', () => {
    const diagnosis = makeDiagnosis()
    diagnosis.calendar = { method: 'not_applicable', expected_cur: null, expected_prev: null, calendar_effect: 0, calendar_adjusted_change: -8008 }
    show(diagnosis)

    expect(screen.queryByText(/calendar/)).toBeNull()
  })

  it('is not shown without a tree, or beside a month that is not compared or withheld (CONTRACTS 11)', () => {
    show({ ...makeDiagnosis(), tree: null })
    expect(screen.queryByRole('heading', { name: 'Where the revenue change came from' })).toBeNull()
    cleanup()

    show(makeDiagnosis(), { ...NUMBERS, period: { ...NUMBERS.period, previous_complete: false } })
    expect(screen.queryByRole('heading', { name: 'Where the revenue change came from' })).toBeNull()
    cleanup()

    show(makeDiagnosis(), { ...NUMBERS, kpis: NUMBERS.kpis.map((kpi) => ({ ...kpi, current: null })) })
    expect(screen.queryByRole('heading', { name: 'Where the revenue change came from' })).toBeNull()
  })
})
