import { describe, expect, it } from 'vitest'
import { makeDiagnosis } from '../pages/diagnosisFixture.ts'
import { makeReport } from '../pages/insightsFixture.ts'
import type { HypothesisView } from '../types/report.ts'
import { readDiagnosis, verdictLabel } from './diagnosisView.ts'

const REPORT = makeReport()
const NUMBERS = REPORT.layer_1_numbers
const byId = (id: string) => REPORT.layer_2_causes.hypotheses.find((h) => h.id === id) as HypothesisView

function withLever(lever: Record<string, unknown>): Record<string, unknown> {
  const diagnosis = makeDiagnosis()
  const tree = diagnosis.tree as { lever: Record<string, unknown> }
  tree.lever = { ...tree.lever, ...lever }
  return diagnosis
}

describe('readDiagnosis', () => {
  it("reads the FE fields the page needs: each hypothesis's lens and family, the lever tree, gross sales' direction, the calendar", () => {
    const view = readDiagnosis(makeDiagnosis())

    expect(view.lensById.get('P2')).toBe('product')
    expect(view.familyById.get('D1')).toBe('data_quality')
    expect(view.grossDirection).toBe(-1)
    expect(view.level1?.formula).toBe('customers*frequency*aov')
    expect(view.level1?.factors.map((f) => f.name)).toEqual(['customers', 'frequency', 'aov'])
    expect(view.level2).toBeNull()
    expect(view.maskedShiftPair).toBeNull()
    expect(view.calendar).toEqual({ method: 'weekday_weights', calendarEffect: -1300, calendarAdjustedChange: -6708 })
  })

  // The 6E2 review (#4): with expected_prev 0 the effect is a fallback (ratio 1,
  // calendar_effect.py), not a measurement.
  it('reads no calendar effect when the previous month expected nothing', () => {
    const diagnosis = makeDiagnosis()
    diagnosis.calendar = { method: 'weekday_weights', expected_cur: 0, expected_prev: 0, calendar_effect: 0, calendar_adjusted_change: -8008 }

    expect(readDiagnosis(diagnosis).calendar).toBeNull()
  })

  // The 6E2 review (#15): rule 4's headline cites the orders x AOV pair.
  it('reads the masked-shift pair only when its alert is on', () => {
    const pair = {
      formula: 'orders*aov',
      factors: [
        { name: 'orders', value_prev: 2604, value_cur: 2380, contribution: -9000 },
        { name: 'aov', value_prev: 40, value_cur: 40.4, contribution: 8900 },
      ],
    }

    expect(readDiagnosis(withLever({ masked_shift_alert: true, masked_shift_pair: pair })).maskedShiftPair?.factors.map((f) => f.name)).toEqual(['orders', 'aov'])
    expect(readDiagnosis(withLever({ masked_shift_alert: false, masked_shift_pair: pair })).maskedShiftPair).toBeNull()
  })

  it('reads nothing it cannot trust, rather than fail', () => {
    for (const raw of [undefined, null, 'x', { tree: 'x', hypotheses: 'x', calendar: 3 }, { tree: { lever: { level1: { formula: 'x', factors: [{}] } } } }]) {
      const view = readDiagnosis(raw)
      expect(view.level1).toBeNull()
      expect(view.grossDirection).toBeNull()
      expect(view.calendar).toBeNull()
      expect(view.lensById.size).toBe(0)
    }
  })
})

// Thach (2026-10-04): a cause ruled out because it moved AGAINST the net change
// is labelled "moved against the change (-X)", not "ruled out", so the table
// never reads as if 30% of the customers did not lapse (S13); the verdict code
// is unchanged. "Against" by stage 3's own test (hypotheses.share_verdict): a
// share hypothesis whose contribution's sign differs from the change it claims
// to explain - gross sales for the product lens, revenue otherwise - and only
// beside a compared month (CONTRACTS 11: an incomplete one is never compared).
describe('verdictLabel', () => {
  const view = readDiagnosis(makeDiagnosis())

  it('words each verdict, and one the vocabulary gains later as written', () => {
    expect(verdictLabel(byId('C2'), view, NUMBERS)).toBe('supported')
    expect(verdictLabel({ ...byId('C2'), verdict: 'partial' }, view, NUMBERS)).toBe('partial')
    expect(verdictLabel(byId('T3'), view, NUMBERS)).toBe('inconclusive')
    expect(verdictLabel(byId('P5'), view, NUMBERS)).toBe('not testable')
    expect(verdictLabel(byId('D1'), view, NUMBERS)).toBe('ruled out')
    // CONTRACTS 11: a vocabulary may gain a value (the 6E2 review #10).
    expect(verdictLabel({ ...byId('D1'), verdict: 'not_evaluated' as HypothesisView['verdict'] }, view, NUMBERS)).toBe('not evaluated')
  })

  it('labels a cause that moved against the change in revenue', () => {
    // B1 rose by 1,792 while revenue fell from 104,160 to 96,152.
    expect(verdictLabel(byId('B1'), view, NUMBERS)).toBe('moved against the change (+1,792.00)')
  })

  it('keeps "ruled out" for a cause that moved with the change but too little', () => {
    // P2 (product lens) fell by 300 as gross sales fell (106,000 -> 98,000).
    expect(verdictLabel(byId('P2'), view, NUMBERS)).toBe('ruled out')
  })

  it("keeps \"ruled out\" for an expectation that overshot in the change's own direction", () => {
    // T2 predicted a fall 2.1 times the real one: same sign, outside 0.2-1.8.
    expect(verdictLabel(byId('T2'), view, NUMBERS)).toBe('ruled out')
  })

  // The 6E2 review (#8): a leftover that prints as zero has no direction.
  it('gives a contribution that prints as zero no direction', () => {
    // P1 is +1e-13 against falling gross sales: stage 3's sign test, but "0.00" on screen.
    expect(verdictLabel(byId('P1'), view, NUMBERS)).toBe('ruled out')
  })

  it('measures a product-lens cause against gross sales, as stage 3 does', () => {
    const grossUp = readDiagnosis({ ...makeDiagnosis(), tree: { ...(makeDiagnosis().tree as object), returns: { gross_prev: 98000, gross_cur: 106000 } } })

    // Gross rose while revenue fell: P2's fall is against gross sales, its own measure.
    expect(verdictLabel(byId('P2'), grossUp, NUMBERS)).toBe('moved against the change (-300.00)')
  })

  it('claims no direction it cannot read', () => {
    const noTree = readDiagnosis({ hypotheses: makeDiagnosis().hypotheses })
    expect(verdictLabel(byId('P2'), noTree, NUMBERS)).toBe('ruled out')
    expect(verdictLabel(byId('B1'), readDiagnosis(null), NUMBERS)).toBe('ruled out')

    const incomplete = { ...NUMBERS, period: { ...NUMBERS.period, previous_complete: false } }
    expect(verdictLabel(byId('B1'), view, incomplete)).toBe('ruled out')

    expect(verdictLabel({ ...byId('B1'), share: null }, view, NUMBERS)).toBe('ruled out')
    expect(verdictLabel({ ...byId('B1'), contribution: 0, share: 0 }, view, NUMBERS)).toBe('ruled out')
    expect(verdictLabel({ ...byId('B1'), contribution: -0, share: -0 }, view, NUMBERS)).toBe('ruled out')
  })

  // The 6E2 review (#9): stage 3 still judges against a current month the
  // report withholds; the page claims no direction against a withheld figure.
  it('claims no direction beside a withheld current month', () => {
    const withheld = { ...NUMBERS, kpis: NUMBERS.kpis.map((kpi) => (kpi.id === 'revenue' ? { ...kpi, current: null } : kpi)) }

    expect(verdictLabel(byId('B1'), view, withheld)).toBe('ruled out')
  })

  it('reads no direction from a revenue that did not move', () => {
    const flat = { ...NUMBERS, kpis: NUMBERS.kpis.map((kpi) => (kpi.id === 'revenue' ? { ...kpi, current: 100, previous: 100 } : kpi)) }

    expect(verdictLabel(byId('B1'), view, flat)).toBe('ruled out')
  })
})
