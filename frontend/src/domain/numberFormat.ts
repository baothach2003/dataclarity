// How the quantity and price columns' numbers are written (session 2E-u1,
// Thach): "1,000" is one thousand or one. Stage 1 measures every column on
// the raw file (profile.json's `number_format`) and decides on execute:
// the cells' proof, else the user's answer; with neither, it refuses to run,
// so Review asks and Confirm waits. These functions decide what is asked and
// sent; stage 1 remains the judge (stages/ingest/number_apply.py).

import type { CanonicalField, CleaningPlan, NumberFormat, NumberFormatMeasure, ProfileContract } from '../types/contracts.ts'

// The canonical fields stages 2 and 3 read as numbers (number_apply.NUMERIC_FIELDS).
const NUMERIC_FIELDS: readonly CanonicalField[] = ['quantity', 'unit_price']

export interface NumberColumn {
  column: string
  measure: NumberFormatMeasure
}

/** Answers by source column. An answer applies while its column is asked: a
 * column remapped away and back gets its earlier answer again. */
export type StoredNumberAnswers = Readonly<Record<string, NumberFormat>>

/** The plan's kept quantity and price columns that profile.json measured. */
export function numberColumns(plan: CleaningPlan, profile: ProfileContract): NumberColumn[] {
  return plan.column_actions.flatMap((action) => {
    if (!NUMERIC_FIELDS.includes(action.canonical_field) || action.action === 'drop_column') {
      return []
    }
    const measure = profile.columns.find((c) => c.name === action.source_name)?.number_format ?? null
    return measure === null ? [] : [{ column: action.source_name, measure }]
  })
}

/** The columns asked: their cells prove neither mark (or both) and some read two ways. */
export function numberQuestions(plan: CleaningPlan, profile: ProfileContract): NumberColumn[] {
  return numberColumns(plan, profile).filter((found) => found.measure.decision === 'ask')
}

/** The stored answers that still apply: for a column asked now. A proven
 * column takes no answer (stage 1 refuses one against the proof). */
export function applicableNumberAnswers(
  plan: CleaningPlan,
  profile: ProfileContract,
  stored: StoredNumberAnswers,
): Record<string, NumberFormat> {
  return Object.fromEntries(
    numberQuestions(plan, profile).flatMap(({ column }) => (column in stored ? [[column, stored[column]]] : [])),
  )
}
