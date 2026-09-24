// Display labels for the enums in docs/AI_PIPELINE.md section 5. Kept separate
// from types/contracts.ts (data shapes only) and transformCatalog.ts (the
// legality matrix), so a copy change never touches either.

import type { CanonicalField, IssueCode, SemanticType } from '../types/contracts.ts'

export const CANONICAL_FIELD_LABELS: Record<CanonicalField, string> = {
  product_name: 'product name',
  sku: 'SKU',
  category: 'category',
  transaction_date: 'transaction date',
  quantity: 'quantity',
  unit_price: 'unit price',
  transaction_type: 'transaction type',
  supplier: 'supplier',
  customer: 'customer',
  note: 'note',
  order_id: 'order / invoice id',
  ignore: 'ignore',
}

export const SEMANTIC_TYPE_LABELS: Record<SemanticType, string> = {
  numeric_continuous: 'Numeric (continuous)',
  numeric_discrete: 'Numeric (discrete)',
  categorical_nominal: 'Categorical (nominal)',
  categorical_ordinal: 'Categorical (ordinal)',
  datetime: 'Datetime',
  identifier: 'Identifier',
  boolean: 'Boolean',
  text: 'Text',
}

export const ISSUE_LABELS: Record<IssueCode, string> = {
  missing_values: 'missing',
  invalid_dates: 'invalid dates',
  mixed_date_formats: 'mixed date formats',
  negative_values: 'negative',
  zero_values: 'zero',
  inconsistent_case: 'inconsistent case',
  trailing_whitespace: 'whitespace',
  near_duplicate_labels: 'near-duplicate labels',
  outliers_iqr: 'outliers',
  mixed_types: 'mixed types',
  constant_column: 'constant column',
  all_null_column: 'all null',
  duplicate_rows: 'duplicate rows',
  duplicate_business_key: 'duplicate key',
  non_numeric_in_numeric: 'non-numeric values',
  order_id_not_one_order: 'not an order id',
}

export function joinFieldLabels(fields: CanonicalField[]): string {
  const labels = fields.map((field) => CANONICAL_FIELD_LABELS[field])
  if (labels.length <= 1) {
    return labels.join('')
  }
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1] ?? ''}`
}
