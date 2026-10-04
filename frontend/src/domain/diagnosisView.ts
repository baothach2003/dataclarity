// What the Insights page reads of diagnosis.json - only fields CONTRACTS 11 lists for FE - for the card
// "Where the revenue change came from". Read tolerantly: a part that is missing or not the contract's
// shape is left out, never guessed (the report.json the page leads with is checked; this file's fields
// add a card). The hypothesis table's labels are report.json's own (stage 5, Thach 2026-10-04 (vii)).

import { money } from './reportFormat.ts'

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

export function readDiagnosis(raw: unknown): DiagnosisView {
  const diagnosis = record(raw)
  const tree = record(diagnosis?.tree)
  const lever = record(tree?.lever)
  const calendar = record(diagnosis?.calendar)
  const calendarMethod = calendar?.method
  return {
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

/** A signed money figure: "+500.00", "-300.00", and "0.00" unsigned. */
export function signedMoney(value: number): string {
  const printed = money(value)
  return /^[0.,]+$/.test(printed) ? printed : value > 0 ? `+${printed}` : printed
}
