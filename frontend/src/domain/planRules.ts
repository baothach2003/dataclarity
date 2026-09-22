// UI-side rules for the Review screen's guardrails (docs/SPECS.md section 4.2
// B): the Confirm gate and the same-field mapping conflict. Both mirror
// `stages/ingest/plan_validation.py`, which re-checks the submitted plan for
// real; this module only keeps the user from submitting something it would
// reject; see CLAUDE.md 3.2/3.3.

import type { CanonicalField, CleaningPlan } from '../types/contracts.ts'
import { REQUIRED_CANONICAL_FIELDS } from './transformCatalog.ts'

const REQUIRED_FIELD_ORDER: CanonicalField[] = ['product_name', 'transaction_date', 'quantity']

export function mappedColumnsByField(plan: CleaningPlan): Map<CanonicalField, string[]> {
  const map = new Map<CanonicalField, string[]>()
  for (const column of plan.column_actions) {
    if (column.canonical_field === 'ignore') {
      continue
    }
    const columns = map.get(column.canonical_field)
    if (columns) {
      columns.push(column.source_name)
    } else {
      map.set(column.canonical_field, [column.source_name])
    }
  }
  return map
}

export function droppedColumnNames(plan: CleaningPlan): Set<string> {
  return new Set(
    plan.column_actions.filter((column) => column.action === 'drop_column').map((c) => c.source_name),
  )
}

/** Required fields not mapped to a column that survives the plan, in the fixed
 * order the Confirm-disabled copy uses (design/mockups/Review · Confirm
 * disabled (spec).png). Empty means Confirm may run. */
export function missingRequiredFields(plan: CleaningPlan): CanonicalField[] {
  const mapped = mappedColumnsByField(plan)
  const dropped = droppedColumnNames(plan)
  return REQUIRED_FIELD_ORDER.filter((field) => {
    const columns = mapped.get(field) ?? []
    return columns.every((name) => dropped.has(name))
  })
}

/** The other column already mapped to `field`, or null when `field` is free
 * (docs/SPECS.md 4.2: "mapping two columns to the same canonical field is
 * blocked inline"). `field: "ignore"` is never a conflict: many columns may
 * be ignored. */
export function mappingConflict(
  plan: CleaningPlan,
  sourceName: string,
  field: CanonicalField,
): string | null {
  if (field === 'ignore') {
    return null
  }
  const holder = plan.column_actions.find(
    (column) => column.canonical_field === field && column.source_name !== sourceName,
  )
  return holder ? holder.source_name : null
}

export function isRequiredField(field: CanonicalField): boolean {
  return REQUIRED_CANONICAL_FIELDS.has(field)
}
