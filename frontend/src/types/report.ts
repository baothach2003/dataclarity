// report.json, stage 5's data layer (contracts/report.py, contracts/report_views.py; docs/CONTRACTS.md
// section 9), as the Insights page reads it. Stage 5 computes nothing and neither does this page: every
// figure is shown as the file has it, a null with its reason (CONTRACTS 11).

export type NoteCode =
  | 'same_day_cancellations'
  | 'returns_booked_as_in'
  | 'unconfirmed_suggestions'
  | 'unconfirmed_deductions'
  | 'discounts_in_prices'
  | 'other_transaction_types'

export type NoteFigure =
  | 'revenue'
  | 'gross_sales'
  | 'returns'
  | 'discounts'
  | 'other_deductions'
  | 'return_rate'
  | 'orders'
  | 'aov'
  | 'units'
  | 'customers'
  | 'products'
  | 'diagnosis'

export type Scope = 'file' | 'current' | 'previous'

export interface NoteMeasure {
  name: string
  scope: Scope
  lines: number
  amount: number | null
  orders?: number | null
  keys?: number | null
}

// Worded by stage 5 from contracts.lines.NOTE_TEXTS by its code, never the file's sentence.
export interface NoteView {
  code: NoteCode
  text: string
  figures: NoteFigure[]
  measures: NoteMeasure[]
}

export interface ReportPeriod {
  current: string
  previous: string
  data_start: string
  data_end: string
  previous_complete: boolean
  previous_incomplete_reason: string | null
}

export type TrustVerdict = 'trusted' | 'caution' | 'blocked'

export interface TrustCheckView {
  id: 'D1' | 'D2' | 'D3'
  status: 'ok' | 'caution' | 'blocked' | 'inconclusive' | 'not_applicable'
  message: string
}

export interface TrustBadge {
  verdict: TrustVerdict
  checks: TrustCheckView[]
  limitations: string[]
}

export type KpiId = 'revenue' | 'orders' | 'active_customers' | 'aov' | 'return_rate'
export type KpiUnit = 'money' | 'count' | 'ratio'

export interface Kpi {
  id: KpiId
  label: string
  unit: KpiUnit
  current: number | null
  previous: number | null
  change_pct: number | null
  change_reason: string | null
  current_reason: string | null
  previous_reason: string | null
  notes: NoteCode[]
}

export interface MonthRevenue {
  period: string
  revenue: number | null
  revenue_reason: string | null
  complete: boolean
}

export interface UnmeasurableLines {
  scope: Scope
  reason: 'no quantity' | 'no price' | 'amount too large to add'
  lines: number
}

export interface NonProductLines {
  line_class: string
  lines: number
  amount: number
  amount_current: number
  amount_previous: number
  reason: string
}

export interface OutsideRevenueLines {
  line_class: string
  scope: Scope
  sign: 'positive' | 'negative' | 'no_money' | null
  lines: number
  amount: number
  lines_without_amount: number
  // 2.5 (Thach, 2026-10-04, (ix)): why it is outside revenue, worded by its class code.
  reason: string
}

export interface Numbers {
  period: ReportPeriod
  trust: TrustBadge
  kpis: Kpi[]
  current_note: string | null
  revenue_by_month: MonthRevenue[]
  undated_lines: number
  undated_lines_reason: string | null
  future_lines?: number
  future_lines_reason?: string | null
  unconfirmed_placeholders_reason?: string | null
  unmeasurable: UnmeasurableLines[]
  non_product: NonProductLines[]
  outside_revenue: OutsideRevenueLines[]
  how_to_read: NoteView[]
  notes: NoteView[]
}

export type Verdict = 'supported' | 'partial' | 'ruled_out' | 'inconclusive' | 'not_testable'

export interface HypothesisView {
  id: string
  // 2.6 (Thach, 2026-10-05, Q2): the lens, as diagnosis.json has it - the label names its total from it.
  lens: string
  statement: string
  verdict: Verdict
  contribution: number | null
  share: number | null
  rule: string
  // Free-form per hypothesis; no key is relied on (CONTRACTS 11).
  evidence: Record<string, unknown>
  // 2.5 (Thach, 2026-10-04, (vii)-(viii)): one copy of what the page and report.html print - ruled out for
  // moving against the change (stage 5 decides, by stage 3's sign test), the verdict as shown, the
  // evidence as report.html words it, key by key.
  moved_against: boolean
  verdict_label: string
  evidence_text: string[]
}

export interface Headline {
  rule: 1 | 2 | 3 | 4 | 5 | 6 | 7
  hypothesis_id: string | null
  lens: string | null
  message: string
  // The headline's size test (contracts/diagnosis.py HeadlineMovement); not read by the page.
  movement?: Record<string, unknown> | null
}

export interface NotTestable {
  id: string
  statement: string
  reason: string
}

export interface AiFindings {
  summary: string
  headline_explanation: string
  hypothesis_notes: { id: string; text: string }[]
  not_tested_note: string
}

export interface Causes {
  headline: Headline
  hypotheses_note?: string | null
  hypotheses: HypothesisView[]
  not_testable: NotTestable[]
  // Not shown in the v1 UI (Thach, 2026-10-03): it stays in the downloadable report.
  signals: unknown[] | null
  narration: AiFindings | null
  // 'not_in_v1' (report.json 2.8, Thach Q21): 3F is closed - nothing failed, nothing is shown.
  narration_status: 'shown' | 'unavailable' | 'not_in_v1'
  notes: NoteView[]
  suggested_classes: Record<string, string>
}

export interface RevenuePoint {
  period: string
  point: number
  low: number
  high: number
  confidence: number
}

export interface ForecastView {
  method: string
  months_used: number
  insufficient_history: boolean
  points: RevenuePoint[]
  history_note: string | null
  season_years: number | null
  season_note: string | null
  notes: NoteCode[]
  first_month_in_file: boolean
  partial_first_month_until: string | null
}

// forecast.json's recommendation as report.json shows it: AI text, rendered escaped (SEC-3), its
// confidence a label, never a figure (contracts/report_views.py RecommendationView).
export interface RecommendationView {
  priority: number
  insight: string
  cause: string
  action: string
  expected_impact: string
  how_to_measure: string
  confidence_label: 'low' | 'medium' | 'high'
}

export interface DoNotDo {
  tempting_action: string
  why_wrong_here: string
}

export interface Actions {
  forecast: ForecastView
  // Off in v1 (recommendations_status "switched_off"): an info notice in the cards' place (design gap review).
  recommendations: RecommendationView[] | null
  do_not_do: DoNotDo[] | null
  recommendations_status: 'shown' | 'switched_off' | 'unavailable'
  notes: NoteCode[]
}

export interface ChartSeries {
  name: string
  x: string[]
  // null: a month not drawn - a gap, never a zero or a join.
  y: (number | null)[]
}

export interface Chart {
  id: 'revenue_trend' | 'forecast'
  type: string
  title: string
  series: ChartSeries[]
  notes: NoteCode[]
  note: string | null
  cautions: string[]
}

export interface DataQuality {
  rows_in: number
  rows_out: number
  issues_fixed: number
  warnings: number
}

export interface Provenance {
  stages_run: string[]
  ai_calls: number
  models_used: string[]
}

export interface ReportContract {
  schema_version: string
  generated_at: string
  run_id: string
  source_file: string
  data_quality: DataQuality
  layer_1_numbers: Numbers
  layer_2_causes: Causes
  layer_3_actions: Actions
  charts: Chart[]
  provenance: Provenance
}
