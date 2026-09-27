// How the date column's day-month-year cells are written (session 2E-j,
// Thach): "05/01/2026" is 5 January or 1 May. Stage 1 measures every column
// on the raw file (profile.json's `date_order`) and decides on execute: the
// user's answer, else the file's proof; with neither, it refuses to run, so
// Review asks and Confirm waits. These functions decide what is asked and
// sent; stage 1 remains the judge (stages/ingest/date_order.py).

import type { CleaningPlan, DateOrder, DateOrderMeasure, Params, ProfileContract } from '../types/contracts.ts'

/** An answer remembers the column it was given for: a remap asks again. */
export interface StoredDateAnswer {
  value: boolean
  column: string
}

export interface DateQuestion {
  column: string
  measure: DateOrderMeasure
}

/** What the parse step on the date column must change to read as `order`
 * does; `fix` is the params that would, or null when no simple change will
 * (a file holding both proofs needs a format). */
export interface ParseConflict {
  column: string
  order: DateOrder
  fix: Params | null
}

/** The plan's date column, or null; a dropped column is not mapped. */
export function dateColumn(plan: CleaningPlan): string | null {
  return (
    plan.column_actions.find((c) => c.canonical_field === 'transaction_date' && c.action !== 'drop_column')
      ?.source_name ?? null
  )
}

/** profile.json's measure of the plan's date column, or null. */
export function dateMeasure(plan: CleaningPlan, profile: ProfileContract): { column: string; measure: DateOrderMeasure } | null {
  const column = dateColumn(plan)
  const measure = profile.columns.find((c) => c.name === column)?.date_order ?? null
  return column === null || measure === null ? null : { column, measure }
}

/** Asked when the date column's cells prove neither order, or both. */
export function dateQuestion(plan: CleaningPlan, profile: ProfileContract): DateQuestion | null {
  const found = dateMeasure(plan, profile)
  return found !== null && found.measure.decision === 'ask' ? found : null
}

/** The stored answer while it still applies: asked, about the same column. */
export function applicableDateAnswer(
  plan: CleaningPlan,
  profile: ProfileContract,
  stored: StoredDateAnswer | null,
): boolean | null {
  const question = dateQuestion(plan, profile)
  return question !== null && stored !== null && stored.column === question.column ? stored.value : null
}

/** The order stage 1 will apply: the answer, else the proof. */
export function appliedOrder(plan: CleaningPlan, profile: ProfileContract, answer: boolean | null): DateOrder | null {
  if (answer !== null) {
    return answer ? 'day_first' : 'month_first'
  }
  const decision = dateMeasure(plan, profile)?.measure.decision ?? null
  return decision === 'ask' ? null : decision
}

/** Which way a format reads a day-month-year date: only a format whose day
 * and month both come before its year can read one ('%Y-%m-%d' reads ISO,
 * never 05/01/2026 - 2E-j review cycle 1 #8). */
function formatOrder(format: string): DateOrder | null {
  const day = format.indexOf('%d')
  const month = format.indexOf('%m')
  const year = Math.max(format.indexOf('%Y'), format.indexOf('%y'))
  if (day < 0 || month < 0 || year < Math.max(day, month)) {
    return null
  }
  return day < month ? 'day_first' : 'month_first'
}

/** A parse step on the date column that reads some of its cells other than
 * `order` does - the counts stand in for stage 1's cell-by-cell check. Per
 * cell with no dayfirst, pandas reads a cell month first unless it cannot
 * be, so every such cell that proves day first is read right. */
export function parseConflict(plan: CleaningPlan, profile: ProfileContract, answer: boolean | null): ParseConflict | null {
  const found = dateMeasure(plan, profile)
  const order = appliedOrder(plan, profile, answer)
  const step = plan.column_actions.find((c) => c.source_name === found?.column)
  if (found === null || order === null || step?.action !== 'parse_datetime') {
    return null
  }
  const { measure } = found
  const either = measure.ambiguous
  const format = typeof step.params.format === 'string' ? step.params.format : null
  let wrong: boolean
  if (format !== null) {
    const reads = formatOrder(format)
    // The format reads the cells only its own order can hold, which the
    // decided order reads as no date (review cycle 1 #8).
    const itsProof = reads === 'day_first' ? measure.day_first : measure.month_first
    wrong = reads !== null && reads !== order && (either > 0 || itsProof > 0)
  } else if (step.params.dayfirst === true) {
    wrong = order === 'month_first' && (either > 0 || measure.day_first > 0)
  } else {
    wrong = order === 'day_first' ? either > 0 || measure.month_first > 0 : measure.day_first > 0
  }
  if (!wrong) {
    return null
  }
  const rest = Object.fromEntries(Object.entries(step.params).filter(([key]) => key !== 'format' && key !== 'dayfirst'))
  const fix = order === 'day_first' ? { ...rest, dayfirst: true } : measure.day_first > 0 ? null : rest
  return { column: found.column, order, fix }
}
