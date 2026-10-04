import { describe, expect, it } from 'vitest'
import { makeDiagnosis } from '../pages/diagnosisFixture.ts'
import { readDiagnosis } from './diagnosisView.ts'

function withLever(lever: Record<string, unknown>): Record<string, unknown> {
  const diagnosis = makeDiagnosis()
  const tree = diagnosis.tree as { lever: Record<string, unknown> }
  tree.lever = { ...tree.lever, ...lever }
  return diagnosis
}

describe('readDiagnosis', () => {
  it('reads the FE fields the decomposition card needs: the lever tree and the calendar', () => {
    const view = readDiagnosis(makeDiagnosis())

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
      expect(view.maskedShiftPair).toBeNull()
      expect(view.calendar).toBeNull()
    }
  })
})
