import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { readDiagnosis } from '../domain/diagnosisView.ts'
import { makeDiagnosis } from '../pages/diagnosisFixture.ts'
import { makeReport, SAME_DAY_TEXT } from '../pages/insightsFixture.ts'
import type { ReportContract } from '../types/report.ts'
import { CausesSection } from './CausesSection.tsx'

afterEach(() => {
  cleanup()
})

function show(report: ReportContract = makeReport(), diagnosis: unknown = makeDiagnosis()) {
  return render(<CausesSection causes={report.layer_2_causes} numbers={report.layer_1_numbers} view={readDiagnosis(diagnosis)} />)
}

function rows() {
  return within(screen.getByRole('table', { name: 'Every hypothesis tested, the ruled-out ones included' }))
    .getAllByRole('row')
    .slice(1)
}

function cells(row: HTMLElement): (string | null)[] {
  return [...row.querySelectorAll('th, td')].slice(0, 4).map((cell) => cell.textContent)
}

// PROJECT_PLAN 6E, layer 2, with the design gap decisions: the code's own
// headline (no AI narrative), the full hypothesis table in place of the
// two-column card - verdicts, not-testable, the table's note - and no signals
// table (it stays in the downloadable report). As stage 5 words it, computing
// nothing.
describe('CausesSection', () => {
  it("leads with the engine's own headline", () => {
    show()

    expect(screen.getByRole('heading', { name: 'Why it happened' })).toBeDefined()
    expect(screen.getByText(/The best-supported explanation: revenue lost to lapsed customers changed/)).toBeDefined()
  })

  it('lists every hypothesis tested with its verdict, contribution and share', () => {
    show()

    expect(rows().map(cells)).toEqual([
      ['C2 Revenue lost to lapsed customers changed', 'supported', '-9,000.00', '-112%'],
      ['B1 Customers bought more often', 'moved against the change (+1,792.00)', '1,792.00', '22%'],
      ['P2 Sales mix shifted towards cheaper products', 'ruled out', '-300.00', '-4%'],
      ["T2 Last year's change between the same two months explains the change", 'ruled out', '-16,816.80', '-210%'],
      ['P1 Like-for-like prices changed', 'ruled out', '0.00', '0%'],
      ['R1 The change is concentrated in one product or category', 'ruled out', '', ''],
      ['D1 Days with no sales (missing data or a closure) explain the change', 'ruled out', '', ''],
      ['T3 The change is routine variation', 'inconclusive', '', ''],
      ['P5 Charges paid by customers changed', 'not testable', '', ''],
    ])
    // Each row is headed by its hypothesis, and each details control named by it (the 6E2 review #12).
    expect(rows()[0]?.querySelector('th')?.getAttribute('scope')).toBe('row')
    expect(screen.getAllByText('Details')[0]?.getAttribute('aria-label')).toBe('Rule and evidence for C2')
  })

  it('shows each rule and its evidence key by key, a product nobody confirmed marked', () => {
    show()
    const [, , , , , r1] = rows()

    expect(within(r1).getByText('the top member holds less than half of the change')).toBeDefined()
    expect(within(r1).getByText('top_member: Gift wrap (suggested: charge, not confirmed)')).toBeDefined()
    expect(within(r1).getByText('top_member_share: 0.12')).toBeDefined()
  })

  it('says the AI narration is unavailable', () => {
    show()

    expect(screen.getByText('The AI narration is unavailable for this report')).toBeDefined()
  })

  it("shows the table's note above it", () => {
    const report = makeReport()
    report.layer_2_causes.hypotheses_note = 'The change is within the usual movement, so no hypothesis is singled out.'
    show(report)
    const note = screen.getByText(report.layer_2_causes.hypotheses_note)
    const table = screen.getByRole('table', { name: 'Every hypothesis tested, the ruled-out ones included' })

    expect(note.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('lists what this data cannot test, and the classes nobody confirmed', () => {
    show()

    expect(screen.getByText('Marketing and promotions: no campaign data; discounts booked as lines are P4, a discount column is not canonical')).toBeDefined()
    const classes = screen.getByRole('table', { name: 'Classes suggested for these products that nobody confirmed in Review' })
    expect(within(classes).getByText('Gift wrap')).toBeDefined()
    expect(within(classes).getByText('charge')).toBeDefined()
  })

  it('shows no signals table (Thach, 2026-10-03: it stays in the downloadable report)', () => {
    const report = makeReport()
    report.layer_2_causes.signals = [{ series: 'revenue', label: 'Revenue', mode: 'level', signal: 'within' }]
    show(report)

    expect(screen.queryByText(/Where this month sits/)).toBeNull()
    expect(screen.queryByText('within the limits')).toBeNull()
  })

  // Rule 1 (the design gap review): the trust gate blocked the run - the causes
  // are replaced by the reason. The data checks it did run are the badge's.
  it('replaces the causes with the reason when the run is blocked', () => {
    const report = makeReport()
    report.layer_2_causes.headline = { ...report.layer_2_causes.headline, rule: 1, hypothesis_id: null, lens: null, message: 'The data cannot be diagnosed: prices shifted by a factor of 100.' }
    show(report)

    expect(screen.getByText('The data cannot be diagnosed: prices shifted by a factor of 100.')).toBeDefined()
    expect(screen.getByText('No cause was tested: the data trust check blocked this run. The data checks are in the badge above.')).toBeDefined()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText(/Marketing and promotions/)).toBeNull()
  })

  // The 6E2 review (#13): a pointer by note code matched no visible label - the
  // notes are shown where the diagnosis is, as text.
  it("shows the diagnosis's notes", () => {
    const report = makeReport()
    report.layer_2_causes.notes = report.layer_1_numbers.notes.slice(0, 1)
    show(report)

    expect(screen.getByRole('heading', { name: 'Notes on the diagnosis' })).toBeDefined()
    expect(screen.getByText(SAME_DAY_TEXT)).toBeDefined()
  })

  it('repeats beside the customer causes that unconfirmed walk-ins count as customers', () => {
    const report = makeReport()
    report.layer_1_numbers.unconfirmed_placeholders_reason = '"Guest" may stand for walk-in customers; nobody confirmed it, so it is counted as a customer.'
    show(report)

    expect(screen.getByText(report.layer_1_numbers.unconfirmed_placeholders_reason)).toBeDefined()
  })
})
