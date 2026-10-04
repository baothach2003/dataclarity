// What the Insights page reads of diagnosis.json - only fields CONTRACTS 11 lists for FE - and the
// verdict label of the hypothesis table. Read tolerantly: a part that is missing or not the contract's
// shape is left out, never guessed (the report.json the page leads with is checked; this file's fields
// add a card and a label).

import { money } from './reportFormat.ts'
import type { HypothesisView, Numbers } from '../types/report.ts'

export type FactorName = 'customers' | 'frequency' | 'orders' | 'aov' | 'units_per_order' | 'price_per_unit'

export interface Factor {
  name: FactorName
  valuePrev: number
  valueCur: number
  contribution: number
}

export interface Decomposition {
  formula: string
  factors: Factor[]
}

export interface DiagnosisView {
  lensById: Map<string, string>
  familyById: Map<string, string>
  // The direction gross sales moved (tree.returns), the product lens's measure in stage 3; null unread.
  grossDirection: -1 | 0 | 1 | null
  level1: Decomposition | null
  level2: Decomposition | null
  // Rule 4's orders x AOV pair, which its headline cites - only while the masked-shift alert is on.
  maskedShiftPair: Decomposition | null
  calendar: { method: 'weekday_weights' | 'day_count'; calendarEffect: number; calendarAdjustedChange: number } | null
}

const FACTORS = new Set<string>(['customers', 'frequency', 'orders', 'aov', 'units_per_order', 'price_per_unit'])

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function decomposition(value: unknown): Decomposition | null {
  const level = record(value)
  if (!level || typeof level.formula !== 'string' || !Array.isArray(level.factors) || level.factors.length === 0) {
    return null
  }
  const factors: Factor[] = []
  for (const item of level.factors) {
    const factor = record(item)
    if (
      !factor ||
      typeof factor.name !== 'string' ||
      !FACTORS.has(factor.name) ||
      !finite(factor.value_prev) ||
      !finite(factor.value_cur) ||
      !finite(factor.contribution)
    ) {
      return null
    }
    factors.push({ name: factor.name as FactorName, valuePrev: factor.value_prev, valueCur: factor.value_cur, contribution: factor.contribution })
  }
  return { formula: level.formula, factors }
}

function direction(previous: number, current: number): -1 | 0 | 1 {
  return current > previous ? 1 : current < previous ? -1 : 0
}

export function readDiagnosis(raw: unknown): DiagnosisView {
  const diagnosis = record(raw)
  const lensById = new Map<string, string>()
  const familyById = new Map<string, string>()
  for (const item of Array.isArray(diagnosis?.hypotheses) ? diagnosis.hypotheses : []) {
    const hypothesis = record(item)
    if (hypothesis && typeof hypothesis.id === 'string') {
      if (typeof hypothesis.lens === 'string') {
        lensById.set(hypothesis.id, hypothesis.lens)
      }
      if (typeof hypothesis.family === 'string') {
        familyById.set(hypothesis.id, hypothesis.family)
      }
    }
  }
  const tree = record(diagnosis?.tree)
  const lever = record(tree?.lever)
  const returns = record(tree?.returns)
  const calendar = record(diagnosis?.calendar)
  const calendarMethod = calendar?.method
  return {
    lensById,
    familyById,
    grossDirection: returns && finite(returns.gross_prev) && finite(returns.gross_cur) ? direction(returns.gross_prev, returns.gross_cur) : null,
    level1: decomposition(lever?.level1),
    level2: decomposition(lever?.level2),
    maskedShiftPair: lever?.masked_shift_alert === true ? decomposition(lever.masked_shift_pair) : null,
    // With expected_prev 0 the effect is a fallback (ratio 1, calendar_effect.py), not a measurement
    // (the 6E2 review #4).
    calendar:
      calendar &&
      (calendarMethod === 'weekday_weights' || calendarMethod === 'day_count') &&
      finite(calendar.expected_prev) &&
      calendar.expected_prev !== 0 &&
      finite(calendar.calendar_effect) &&
      finite(calendar.calendar_adjusted_change)
        ? { method: calendarMethod, calendarEffect: calendar.calendar_effect, calendarAdjustedChange: calendar.calendar_adjusted_change }
        : null,
  }
}

const LABELS: Partial<Record<string, string>> = {
  supported: 'supported',
  partial: 'partial',
  ruled_out: 'ruled out',
  inconclusive: 'inconclusive',
  not_testable: 'not testable',
}

/** A signed money figure: "+500.00", "-300.00", and "0.00" unsigned. */
export function signedMoney(value: number): string {
  const printed = money(value)
  return /^[0.,]+$/.test(printed) ? printed : value > 0 ? `+${printed}` : printed
}

/** The direction of the change a hypothesis claims to explain, by stage 3's own measure
 * (hypotheses.share_verdict): gross sales for the product lens, revenue otherwise; null when the page
 * cannot read it, or the previous month is not compared (CONTRACTS 11). */
function changeDirection(hypothesisId: string, view: DiagnosisView, numbers: Numbers): -1 | 0 | 1 | null {
  if (!numbers.period.previous_complete) {
    return null
  }
  const lens = view.lensById.get(hypothesisId)
  if (lens === undefined) {
    return null
  }
  if (lens === 'product') {
    return view.grossDirection
  }
  const revenue = numbers.kpis.find((kpi) => kpi.id === 'revenue')
  return revenue && revenue.current !== null && revenue.previous !== null ? direction(revenue.previous, revenue.current) : null
}

export interface Verdict {
  label: string
  // Ruled out for moving against the change: drawn apart from a plain "ruled out".
  against: boolean
}

/** The hypothesis table's verdict (Thach, 2026-10-04): a share hypothesis ruled out because it moved
 * AGAINST the change it claims to explain reads "moved against the change (+X)" - so a table never reads
 * as if 30% of the customers did not lapse (S13). The verdict code is unchanged. Not "against": a share of
 * null (the change did not move), a contribution that prints as zero (a leftover - the 6E2 review #8), a
 * change the page does not show (an incomplete previous month, a withheld current one - #9). */
export function verdictOf(hypothesis: HypothesisView, view: DiagnosisView, numbers: Numbers): Verdict {
  const { verdict, contribution, share } = hypothesis
  if (verdict === 'ruled_out' && share !== null && contribution !== null && money(contribution) !== '0.00') {
    const moved = changeDirection(hypothesis.id, view, numbers)
    if (moved !== null && moved !== 0 && moved !== Math.sign(contribution)) {
      return { label: `moved against the change (${signedMoney(contribution)})`, against: true }
    }
  }
  // A verdict the vocabulary gains later, as stage 5 words it (CONTRACTS 11; the 6E2 review #10).
  return { label: LABELS[verdict] ?? verdict.replaceAll('_', ' '), against: false }
}

export function verdictLabel(hypothesis: HypothesisView, view: DiagnosisView, numbers: Numbers): string {
  return verdictOf(hypothesis, view, numbers).label
}
