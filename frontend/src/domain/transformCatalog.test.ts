import { describe, expect, it } from 'vitest'
import { columnIssueSeverity } from './issueSeverity.ts'
import { CANONICAL_FIELD_LABELS, ISSUE_LABELS } from './labels.ts'
import { illegalityReason, legalColumnActions } from './transformCatalog.ts'

// Session 2E-e: the optional canonical field order_id, mirrored from stage 1.
describe('order_id in the Review screen', () => {
  it('is never imputed - one filled-in id would merge blank lines into one order', () => {
    // text and categorical allow imputation by type, so only the order_id rule refuses it
    // (an identifier column refuses it by type already).
    expect(illegalityReason('impute_constant', 'text', 'order_id')).toMatch(/single order/)
    expect(illegalityReason('impute_mode', 'categorical_nominal', 'order_id')).toMatch(/single order/)
    expect(illegalityReason('impute_constant', 'text', 'customer')).toBeNull()
    expect(legalColumnActions('identifier', 'order_id')).toContain('drop_rows_missing')
    expect(legalColumnActions('identifier', 'order_id')).not.toContain('impute_constant')
  })

  it('takes no action that rewrites an id (2E-e doubt-review)', () => {
    const allowed = new Set(['drop_rows_missing', 'drop_column', 'flag_only', 'trim_whitespace'])
    for (const semantic of ['identifier', 'text', 'numeric_discrete', 'categorical_nominal'] as const) {
      for (const action of legalColumnActions(semantic, 'order_id')) {
        expect(allowed.has(action)).toBe(true)
      }
    }
    expect(illegalityReason('clip_outliers_iqr', 'numeric_discrete', 'order_id')).toMatch(/rewriting ids/)
  })

  it('has a label, and so does the issue stage 1 raises about it', () => {
    expect(CANONICAL_FIELD_LABELS.order_id).toBe('order / invoice id')
    expect(ISSUE_LABELS.order_id_not_one_order).toBe('not an order id')
  })

  it('shows a column that is not an order id as a high-severity issue', () => {
    expect(columnIssueSeverity('order_id_not_one_order', 'order_id', null)).toBe('high')
  })

  it('shows any missing order id as high: one blank id turns every order figure into lines', () => {
    expect(columnIssueSeverity('missing_values', 'order_id', 0.1)).toBe('high')
    expect(illegalityReason('impute_constant', 'text', 'order_id')).not.toMatch(/order of its own/)
  })
})
