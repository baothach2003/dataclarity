// Results page summary tiles (docs/SPECS.md section 4.3; design/mockups/
// Results.png), built only from numbers `cleaning_report.json` actually
// carries (CLAUDE.md 3.2: every number traceable to a tested pandas function,
// never invented here). `cells_affected` and `rows_affected` — never both
// nonzero for one entry — are documented per action in
// `stages/ingest/transforms.py`'s module docstring table.

import { CANONICAL_FIELD_LABELS } from './labels.ts'
import type { CanonicalField, ChangeLogEntry, CleaningReport } from '../types/contracts.ts'

export interface SummaryTile {
  label: string
  value: number
  caption: string
}

const IMPUTATION_ACTIONS = new Set(['impute_median', 'impute_mean', 'impute_mode', 'impute_constant'])

function sum(entries: ChangeLogEntry[], predicate: (entry: ChangeLogEntry) => boolean, field: 'cells_affected' | 'rows_affected'): number {
  return entries.filter(predicate).reduce((total, entry) => total + entry[field], 0)
}

function fieldLabel(column: string | null, mapping: Record<string, CanonicalField>): string {
  if (column === null) {
    return ''
  }
  return column in mapping ? CANONICAL_FIELD_LABELS[mapping[column]] : column
}

export function buildSummaryTiles(report: CleaningReport): SummaryTile[] {
  const { changes, column_mapping } = report
  const droppedMissing = changes.filter((c) => c.action === 'drop_rows_missing' && c.rows_affected > 0)
  const droppedFields = [...new Set(droppedMissing.map((c) => fieldLabel(c.column, column_mapping)))]

  return [
    { label: 'Rows in → out', value: report.rows_out, caption: `${report.rows_in.toLocaleString()} → ${report.rows_out.toLocaleString()}` },
    {
      label: 'Cells imputed',
      value: sum(changes, (c) => IMPUTATION_ACTIONS.has(c.action), 'cells_affected'),
      caption: '',
    },
    {
      label: 'Rows dropped',
      value: sum(changes, (c) => c.action === 'drop_rows_missing', 'rows_affected'),
      caption: droppedFields.length > 0 ? `missing ${droppedFields.join(', ')}` : '',
    },
    {
      label: 'Duplicates removed',
      value: sum(changes, (c) => c.action === 'remove_exact_duplicates', 'rows_affected'),
      caption: 'exact-row',
    },
    {
      label: 'Categories standardized',
      value: sum(changes, (c) => c.action === 'standardize_categories', 'cells_affected'),
      caption: 'labels merged',
    },
    {
      label: 'Dates parsed',
      value: sum(changes, (c) => c.action === 'parse_datetime', 'cells_affected'),
      caption: 'to ISO 8601',
    },
  ]
}

/** Rows with no effect (`flag_only`, or any action that changed nothing:
 * stages/ingest/transforms.py "an action that changes nothing still returns
 * an entry, with cells_affected: 0 and rows_affected: 0") clutter "What ran"
 * without telling the user anything happened, so they are left out here. */
export function changesWithEffect(report: CleaningReport): ChangeLogEntry[] {
  return report.changes.filter((c) => c.cells_affected > 0 || c.rows_affected > 0)
}
