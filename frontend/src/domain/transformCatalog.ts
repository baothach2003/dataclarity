// Client-side mirror of the transform catalog and legality matrix
// (stages/ingest/transform_catalog.py, docs/AI_PIPELINE.md section 6).
//
// This is UI-only: it decides what the Action dropdown offers and re-filters
// when the semantic type changes (docs/SPECS.md section 4.2). The backend is
// the source of truth and re-validates the submitted plan against the same
// rules (stages/ingest/plan_validation.py) — nothing here is ever trusted on
// its own (CLAUDE.md 3.2/3.3).

import type { CanonicalField, SemanticType, TransformAction } from '../types/contracts.ts'

export const ALL_ACTIONS: readonly TransformAction[] = [
  'impute_median',
  'impute_mean',
  'impute_mode',
  'impute_constant',
  'drop_rows_missing',
  'drop_column',
  'parse_datetime',
  'cast_type',
  'trim_whitespace',
  'normalize_case',
  'standardize_categories',
  'fix_negative',
  'remove_exact_duplicates',
  'flag_duplicate_keys',
  'clip_outliers_iqr',
  'flag_only',
]

const NUMERIC_TYPES: ReadonlySet<SemanticType> = new Set(['numeric_continuous', 'numeric_discrete'])
const CATEGORICAL_TYPES: ReadonlySet<SemanticType> = new Set(['categorical_nominal', 'categorical_ordinal'])
const TEXTUAL_TYPES: ReadonlySet<SemanticType> = new Set([...CATEGORICAL_TYPES, 'text'])
const STRING_SHAPE_TYPES: ReadonlySet<SemanticType> = new Set([...TEXTUAL_TYPES, 'identifier'])
const ALL_SEMANTIC_TYPES: ReadonlySet<SemanticType> = new Set([
  'numeric_continuous',
  'numeric_discrete',
  'categorical_nominal',
  'categorical_ordinal',
  'datetime',
  'identifier',
  'boolean',
  'text',
])

export const DATASET_ACTIONS: ReadonlySet<TransformAction> = new Set([
  'remove_exact_duplicates',
  'flag_duplicate_keys',
])

export const IMPUTATION_ACTIONS: ReadonlySet<TransformAction> = new Set([
  'impute_median',
  'impute_mean',
  'impute_mode',
  'impute_constant',
])

// The only actions an order_id column takes - none rewrites an id (2E-e);
// mirrors stage 1's transform_catalog.ORDER_ID_ACTIONS.
const ORDER_ID_ACTIONS: ReadonlySet<TransformAction> = new Set([
  'drop_rows_missing',
  'drop_column',
  'flag_only',
  'trim_whitespace',
])

// Without these three a row cannot be counted at all (AI_PIPELINE section 6).
export const REQUIRED_CANONICAL_FIELDS: ReadonlySet<CanonicalField> = new Set([
  'product_name',
  'transaction_date',
  'quantity',
])

const LEGAL_SEMANTIC_TYPES: Partial<Record<TransformAction, ReadonlySet<SemanticType>>> = {
  impute_median: NUMERIC_TYPES,
  impute_mean: NUMERIC_TYPES,
  impute_mode: new Set([...TEXTUAL_TYPES, 'boolean']),
  impute_constant: new Set([...TEXTUAL_TYPES, 'boolean']),
  drop_rows_missing: ALL_SEMANTIC_TYPES,
  drop_column: ALL_SEMANTIC_TYPES,
  parse_datetime: new Set(['datetime']),
  cast_type: ALL_SEMANTIC_TYPES,
  trim_whitespace: STRING_SHAPE_TYPES,
  normalize_case: STRING_SHAPE_TYPES,
  standardize_categories: CATEGORICAL_TYPES,
  fix_negative: NUMERIC_TYPES,
  clip_outliers_iqr: NUMERIC_TYPES,
  flag_only: ALL_SEMANTIC_TYPES,
}

export function scopeOf(action: TransformAction): 'column' | 'dataset' {
  return DATASET_ACTIONS.has(action) ? 'dataset' : 'column'
}

/** Why `action` may not run on a column of this type/mapping, or null when it may
 * (mirrors `transform_catalog.illegality_reason`, column actions only: the two
 * dataset actions have no per-column legality). */
export function illegalityReason(
  action: TransformAction,
  semanticType: SemanticType,
  canonicalField: CanonicalField,
): string | null {
  const legalTypes = LEGAL_SEMANTIC_TYPES[action]
  if (legalTypes === undefined) {
    return `${action} applies to the dataset, not to a column`
  }
  if (!legalTypes.has(semanticType)) {
    return `${action} is not legal for a ${semanticType} column`
  }
  // order_id is never imputed either (2E-e): one filled-in id would merge every
  // blank line into a single order. Same words as stage 1's transform_catalog.
  if (canonicalField === 'order_id' && !ORDER_ID_ACTIONS.has(action) && !IMPUTATION_ACTIONS.has(action)) {
    return `${action} is not legal for order_id: an id is text and must stay as it is - rewriting ids splits or merges orders`
  }
  if (canonicalField === 'order_id' && IMPUTATION_ACTIONS.has(action)) {
    return `${action} is not legal for order_id: one filled-in id would merge every blank line into a single order - drop those rows, or leave them and the figures count lines`
  }
  // customer is never imputed either (Thach, 2E-k), whatever its type: a
  // filled-in value becomes a customer the file never named. Same words as
  // stage 1's transform_catalog.
  if (canonicalField === 'customer' && IMPUTATION_ACTIONS.has(action)) {
    return `${action} is not legal for customer: a filled-in value becomes a customer the file never named - leave the blanks, they are walk-ins`
  }
  if (REQUIRED_CANONICAL_FIELDS.has(canonicalField) && IMPUTATION_ACTIONS.has(action)) {
    return `${action} is not legal for ${canonicalField}, a required field: use drop_rows_missing or flag_only`
  }
  return null
}

/** Every column action legal for this column, in the catalog's own order
 * (mirrors `transform_catalog.legal_column_actions`). */
export function legalColumnActions(
  semanticType: SemanticType,
  canonicalField: CanonicalField,
): TransformAction[] {
  return ALL_ACTIONS.filter(
    (action) => scopeOf(action) === 'column' && illegalityReason(action, semanticType, canonicalField) === null,
  )
}

export function legalDatasetActions(): TransformAction[] {
  return ALL_ACTIONS.filter((action) => scopeOf(action) === 'dataset')
}

// --- params (stages/ingest/transform_params.py + transform_catalog.py) --------

export const REQUIRED_PARAMS: Partial<Record<TransformAction, readonly string[]>> = {
  impute_constant: ['value'],
  cast_type: ['target'],
  normalize_case: ['mode'],
  standardize_categories: ['mapping'],
  flag_duplicate_keys: ['keys'],
}

export const OPTIONAL_PARAMS: Partial<Record<TransformAction, readonly string[]>> = {
  parse_datetime: ['format', 'dayfirst'],
  fix_negative: ['strategy'],
  clip_outliers_iqr: ['k'],
  flag_only: ['note'],
}

export const CAST_TARGETS = ['integer', 'float', 'string', 'boolean'] as const
export const CASE_MODES = ['title', 'lower', 'upper'] as const
export const NEGATIVE_STRATEGIES = ['flag', 'abs', 'drop'] as const

/** Human labels for the Action dropdown and the selected-action cell
 * (design/mockups/Review.png). */
export const ACTION_LABELS: Record<TransformAction, string> = {
  impute_median: 'Impute median',
  impute_mean: 'Impute mean',
  impute_mode: 'Impute mode',
  impute_constant: 'Fill value',
  drop_rows_missing: 'Drop missing rows',
  drop_column: 'Drop column',
  parse_datetime: 'Parse dates',
  cast_type: 'Convert type',
  trim_whitespace: 'Trim whitespace',
  normalize_case: 'Standardize case',
  standardize_categories: 'Standardize labels',
  fix_negative: 'Fix negative values',
  remove_exact_duplicates: 'Remove exact duplicates',
  flag_duplicate_keys: 'Flag duplicate keys',
  clip_outliers_iqr: 'Clip outliers',
  flag_only: 'Keep as is',
}

export const CASE_MODE_LABELS: Record<(typeof CASE_MODES)[number], string> = {
  title: 'Title Case',
  lower: 'lower case',
  upper: 'UPPER CASE',
}

export const NEGATIVE_STRATEGY_LABELS: Record<(typeof NEGATIVE_STRATEGIES)[number], string> = {
  // "abs" replaces a negative with its absolute value (-5 -> 5), never 0
  // (stages/ingest/transforms.py fix_negative) - copy must say that plainly.
  flag: 'Flag and keep',
  abs: 'Make positive (absolute value)',
  drop: 'Drop these rows',
}

export const CAST_TARGET_LABELS: Record<(typeof CAST_TARGETS)[number], string> = {
  integer: 'Integer',
  float: 'Decimal',
  string: 'Text',
  boolean: 'True / false',
}
