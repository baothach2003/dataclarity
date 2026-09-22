// Display logic for the revised preview table (docs/FIGMA_DESIGN_NOTES.md
// section 7). Pure functions only: PreviewPane.tsx renders what these decide.

import { ACTION_LABELS, REQUIRED_CANONICAL_FIELDS } from './transformCatalog.ts'
import type { CanonicalField, CleaningPlan, PreviewResult, PreviewRow, SemanticType } from '../types/contracts.ts'

const NUMERIC_TYPES: ReadonlySet<SemanticType> = new Set(['numeric_continuous', 'numeric_discrete'])

/** Columns with at least one changed or filled-in cell among the *displayed*
 * rows (`PreviewResult.rows`, not the wider server-side sample). A dropped
 * row's `changed` is always empty (stages/ingest/preview.py), so it never
 * marks a column changed by itself - a fully unaffected column (like a
 * required field the plan only drops rows for) correctly stays hidden even
 * when some sample rows were dropped over it. */
export function changedColumnsInSample(preview: PreviewResult): Set<string> {
  const changed = new Set<string>()
  for (const row of preview.rows) {
    for (const column of row.changed) {
      changed.add(column)
    }
  }
  return changed
}

export function splitColumns(preview: PreviewResult): { shown: string[]; hidden: string[] } {
  const changed = changedColumnsInSample(preview)
  const shown: string[] = []
  const hidden: string[] = []
  for (const column of preview.columns_after) {
    if (changed.has(column)) {
      shown.push(column)
    } else {
      hidden.push(column)
    }
  }
  return { shown, hidden }
}

function sameBefore(a: PreviewRow['before'], b: PreviewRow['before']): boolean {
  const keysA = Object.keys(a)
  const keysB = Object.keys(b)
  if (keysA.length !== keysB.length) {
    return false
  }
  return keysA.every((key) => a[key] === b[key])
}

function isBlank(value: string | null | undefined): boolean {
  return value === null || value === undefined || value.trim() === ''
}

const SHORT_REQUIRED_FIELD_LABELS: Partial<Record<CanonicalField, string>> = {
  product_name: 'name',
  transaction_date: 'date',
  quantity: 'qty',
}

/** A reason for a dropped row, derived from the plan actually submitted and
 * the row's own values - never invented (docs/FIGMA_DESIGN_NOTES.md section
 * 7): "Duplicate" when `remove_exact_duplicates` is in the plan and another
 * displayed row has identical "before" values (that action runs before any
 * column action, so a real duplicate is caught regardless of what else is
 * wrong with the row); otherwise "No <field>" when a required field's column
 * has `drop_rows_missing` and this row's value for it is blank; otherwise
 * "Dropped", when neither can be determined from what is on screen. */
export function dropReason(row: PreviewRow, plan: CleaningPlan, allRows: PreviewRow[]): string {
  const removesDuplicates = plan.dataset_actions.some((a) => a.action === 'remove_exact_duplicates')
  if (removesDuplicates) {
    const isDuplicate = allRows.some((other) => other.row !== row.row && sameBefore(other.before, row.before))
    if (isDuplicate) {
      return 'Duplicate'
    }
  }
  const missingRequired = plan.column_actions.find(
    (column) =>
      column.action === 'drop_rows_missing' &&
      REQUIRED_CANONICAL_FIELDS.has(column.canonical_field) &&
      isBlank(row.before[column.source_name]),
  )
  if (missingRequired) {
    const short = SHORT_REQUIRED_FIELD_LABELS[missingRequired.canonical_field]
    return `No ${short ?? missingRequired.canonical_field}`
  }
  return 'Dropped'
}

/** Per-column semantic type and the plan action's label, by source column
 * name; a synthesized column (a `__flag_*` column the plan added) has
 * neither, since it is not one of the plan's own column actions. */
export function columnMeta(plan: CleaningPlan): {
  semanticType: Map<string, SemanticType>
  actionLabel: Map<string, string>
} {
  const semanticType = new Map<string, SemanticType>()
  const actionLabel = new Map<string, string>()
  for (const column of plan.column_actions) {
    semanticType.set(column.source_name, column.semantic_type)
    actionLabel.set(column.source_name, ACTION_LABELS[column.action])
  }
  return { semanticType, actionLabel }
}

export function isNumeric(semanticType: SemanticType | undefined): boolean {
  return semanticType !== undefined && NUMERIC_TYPES.has(semanticType)
}

/** A numeric cell's text as the mockup shows it: a whole number written as a
 * float (backend imputation can produce "3.0") loses the trailing ".0". Any
 * other value, numeric or not, is shown exactly as given - this never rounds
 * or reformats a real decimal. */
export function formatCellValue(value: string, numeric: boolean): string {
  if (numeric && /^-?\d+\.0$/.test(value)) {
    return value.slice(0, -2)
  }
  return value
}
