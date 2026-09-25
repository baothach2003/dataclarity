// TypeScript mirrors of the Pydantic contracts this UI reads or writes
// (docs/CONTRACTS.md sections 2-5, contracts/profile.py, contracts/cleaning.py).
// Only the fields these 3 screens use are covered (Upload, Review, Results).

export type SemanticType =
  | 'numeric_continuous'
  | 'numeric_discrete'
  | 'categorical_nominal'
  | 'categorical_ordinal'
  | 'datetime'
  | 'identifier'
  | 'boolean'
  | 'text'

export type CanonicalField =
  | 'product_name'
  | 'sku'
  | 'category'
  | 'transaction_date'
  | 'quantity'
  | 'unit_price'
  | 'transaction_type'
  | 'supplier'
  | 'customer'
  | 'note'
  | 'order_id'
  | 'ignore'

export type IssueCode =
  | 'missing_values'
  | 'invalid_dates'
  | 'mixed_date_formats'
  | 'negative_values'
  | 'zero_values'
  | 'inconsistent_case'
  | 'trailing_whitespace'
  | 'near_duplicate_labels'
  | 'outliers_iqr'
  | 'mixed_types'
  | 'constant_column'
  | 'all_null_column'
  | 'duplicate_rows'
  | 'duplicate_business_key'
  | 'non_numeric_in_numeric'
  | 'order_id_not_one_order'

export type Severity = 'low' | 'medium' | 'high'

export type TransformAction =
  | 'impute_median'
  | 'impute_mean'
  | 'impute_mode'
  | 'impute_constant'
  | 'drop_rows_missing'
  | 'drop_column'
  | 'parse_datetime'
  | 'cast_type'
  | 'trim_whitespace'
  | 'normalize_case'
  | 'standardize_categories'
  | 'fix_negative'
  | 'remove_exact_duplicates'
  | 'flag_duplicate_keys'
  | 'clip_outliers_iqr'
  | 'flag_only'

export type PlanSource = 'ai' | 'user_edited' | 'manual'

// --- profile.json ------------------------------------------------------------

export interface DatasetStats {
  rows: number
  columns: number
  duplicate_rows: number
  missing_cells_pct: number
  encoding_used: string
  delimiter: string
}

export interface TopValue {
  value: string
  count: number
}

export interface ColumnProfile {
  name: string
  dtype: string
  null_count: number
  null_pct: number
  unique_count: number
  min: number | null
  max: number | null
  mean: number | null
  median: number | null
  q1: number | null
  q3: number | null
  top_values: TopValue[]
  sample_values: (string | null)[]
}

export interface ProfileContract {
  schema_version: string
  generated_at: string
  dataset: DatasetStats
  columns: ColumnProfile[]
}

// --- schema_inference.json ----------------------------------------------------

export interface DatasetIssue {
  code: IssueCode
  count: number
  severity: Severity
  detail: string
}

export interface ColumnIssue {
  code: IssueCode
  count: number
  pct: number | null
  examples: string[]
}

export interface ColumnInference {
  source_name: string
  semantic_type: SemanticType
  canonical_field: CanonicalField
  confidence: number
  issues: ColumnIssue[]
}

export interface SchemaInferenceContract {
  schema_version: string
  generated_at: string
  model_used: string
  domain_confidence: number
  domain_reasoning: string
  dataset_issues: DatasetIssue[]
  columns: ColumnInference[]
  // 2.1 (2E-e2): stage 1's own measure on the raw file and these columns'
  // mapping - the lines the customer fill would give their receipt's
  // customer. null (or absent, a 2.0 file): not measured.
  receipt_fill_lines?: number | null
}

// --- plan_proposed.json / plan_final.json --------------------------------------

// A plan's params carry whatever an action needs (docs/AI_PIPELINE.md section 6):
// strings, numbers, booleans, or a text-to-text mapping. Never `any` (F6): every
// read of a param value narrows this first (see domain/transformParams.ts).
export type ParamValue = string | number | boolean | Record<string, string> | string[]
export type Params = Record<string, ParamValue>

export interface DatasetAction {
  action: TransformAction
  params: Params
  rationale: string
  alternatives: TransformAction[]
  edited_by_user: boolean
}

export interface ColumnAction {
  source_name: string
  semantic_type: SemanticType
  canonical_field: CanonicalField
  action: TransformAction
  params: Params
  rationale: string
  alternatives: TransformAction[]
  edited_by_user: boolean
}

// Two answers only the user can give on the Review screen (2E-e2). null: not
// asked or not answered, which stages 2 and 3 read as "no".
export interface OrderConfirmations {
  order_id_is_receipt: boolean | null
  customer_on_first_line_only: boolean | null
}

export interface CleaningPlan {
  schema_version: string
  generated_at: string
  source: PlanSource
  dataset_actions: DatasetAction[]
  column_actions: ColumnAction[]
  // 2.1 (2E-e2); absent from a 2.0 plan, which reads as nothing confirmed.
  confirmations?: OrderConfirmations
}

// --- cleaning_report.json -----------------------------------------------------

export interface ChangeLogEntry {
  action: TransformAction
  column: string | null
  cells_affected: number
  rows_affected: number
  params: Params
  detail: string
}

export interface CleaningWarning {
  code: string
  detail: string
}

export interface CleaningReport {
  schema_version: string
  generated_at: string
  rows_in: number
  rows_out: number
  columns_in: number
  columns_out: number
  changes: ChangeLogEntry[]
  warnings: CleaningWarning[]
  // Keyed by source column name, valued by the canonical field it maps to
  // (docs/CONTRACTS.md section 5): {"Prod Name": "product_name"}.
  column_mapping: Record<string, CanonicalField>
  // 2.1 (2E-e2): the answers that ran.
  confirmations?: OrderConfirmations
}

// --- preview (stages/ingest/preview.py PreviewResult) --------------------------

export interface PreviewRow {
  row: number
  before: Record<string, string | null>
  after: Record<string, string | null> | null
  changed: string[]
}

export interface ColumnDelta {
  column: string
  null_pct_before: number | null
  null_pct_after: number | null
  unique_before: number | null
  unique_after: number | null
}

export interface PreviewResult {
  rows_in_file: number
  sample_rows: number
  sampled: boolean
  rows_after: number
  columns_after: string[]
  rows: PreviewRow[]
  deltas: ColumnDelta[]
}

// --- API response envelopes (docs/SPECS.md section 8) --------------------------

export interface Notice {
  code: 'NOT_INVENTORY' | 'AI_UNAVAILABLE'
  message: string
  details?: Record<string, unknown>
}

export interface RunCreated {
  run_id: string
  filename: string
  size_bytes: number
  status: 'uploaded'
}

export interface AnalyzeSchemaResponse {
  run_id: string
  status: 'profiled'
  schema_inference: SchemaInferenceContract | null
  notices: Notice[]
}

export interface PlanResponse {
  run_id: string
  status: 'profiled' | 'planned'
  plan: CleaningPlan | null
  notices: Notice[]
}

export interface PreviewResponse {
  run_id: string
  preview: PreviewResult
}

export interface ExecuteResponse {
  run_id: string
  status: 'cleaned'
  report: CleaningReport
  notices: Notice[]
}
