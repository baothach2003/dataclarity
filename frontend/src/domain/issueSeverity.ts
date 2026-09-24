// Column issue severity, for the badge color in the Review table (SPECS
// section 4.2 B: "Issues ... badges with counts"; design/mockups/Review.png
// shows them gray/orange/red). `ColumnIssue` (docs/CONTRACTS.md section 3)
// carries no severity field — only a dataset-wide `DatasetIssue` does — so this
// is a UI-only classification, decided here and not by the AI (CLAUDE.md 3.2):
// it colors a badge, it never changes a count or a cleaning action.
//
// The rule: cosmetic issues that never lose data are low; issues that can
// distort a computed number are medium; issues that lose rows or corrupt a
// column are high. `missing_values` is a special case, because losing it is
// only a real problem depending on the column: dropped for a required field
// (SPECS section 6) regardless of how small, and elsewhere exactly at the 5%
// line SPECS section 6 already uses to switch from imputing to an explicit
// "Unknown" category.

import type { CanonicalField, IssueCode, Severity } from '../types/contracts.ts'
import { REQUIRED_CANONICAL_FIELDS } from './transformCatalog.ts'

const MISSING_HIGH_ABOVE_PCT = 5

const LOW: ReadonlySet<IssueCode> = new Set([
  'trailing_whitespace',
  'inconsistent_case',
  'near_duplicate_labels',
  'duplicate_rows',
  'constant_column',
  'zero_values',
])

// order_id_not_one_order (2E-e): the mapping would rewrite every order KPI;
// stage 2 falls back to lines, but the user should fix the mapping.
const HIGH: ReadonlySet<IssueCode> = new Set([
  'all_null_column',
  'non_numeric_in_numeric',
  'order_id_not_one_order',
])

export function columnIssueSeverity(
  code: IssueCode,
  canonicalField: CanonicalField,
  pct: number | null,
): Severity {
  if (code === 'missing_values') {
    // order_id (2E-e): one blank id on a sale or return line turns every order
    // figure in the file into lines, whatever the share.
    if (REQUIRED_CANONICAL_FIELDS.has(canonicalField) || canonicalField === 'order_id') {
      return 'high'
    }
    return pct !== null && pct >= MISSING_HIGH_ABOVE_PCT ? 'high' : 'medium'
  }
  if (LOW.has(code)) {
    return 'low'
  }
  if (HIGH.has(code)) {
    return 'high'
  }
  return 'medium'
}
