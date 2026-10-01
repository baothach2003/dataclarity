// Review's whole-file view of the line taxonomy (2E-t3; contracts/lines.py,
// docs/LINE_TAXONOMY.md sections 3 and 5): computed by stage 1 for the plan and
// the answers as they stand. Every scope here is the whole file.
export interface IdentityTerms {
  gross_sales: number
  returns: number
  discounts: number
  other_deductions: number
  other_revenue: number
  net_revenue: number
  returns_on_suggested_keys: number
  money_moved: number
}

export type OutsideRevenueClass = 'gift_card_sale' | 'gift_card_redemption' | 'cost' | 'adjustment' | 'stock_in'

export interface OutsideRevenueLines {
  line_class: OutsideRevenueClass
  scope: 'file' | 'current' | 'previous'
  sign: 'positive' | 'negative' | 'no_money' | null
  lines: number
  amount: number
  lines_without_amount: number
}

export interface UnclassifiedLines {
  lines: number
  amount: number
  share_of_money_moved: number | null
}

export interface UnmeasurableLines {
  scope: 'file' | 'current' | 'previous'
  reason: 'no quantity' | 'no price' | 'amount too large to add'
  lines: number
}

export interface NoteMeasure {
  name: string
  scope: 'file' | 'current' | 'previous'
  lines: number
  amount: number | null
  orders: number | null
  keys: number | null
}

export interface FigureNote {
  code: string
  figures: string[]
  text: string
  measures: NoteMeasure[]
}

// 2E-u4: what the plan's exact-duplicate removal takes, when the user added it.
export interface DuplicatesRemoved {
  lines: number
  revenue: number
}

export interface LineSummary {
  lines: number
  undated_lines: number
  identity: IdentityTerms
  outside_revenue: OutsideRevenueLines[]
  unclassified: UnclassifiedLines
  unmeasurable: UnmeasurableLines[]
  notes: FigureNote[]
  duplicates_removed?: DuplicatesRemoved | null
}

export interface ReservedRename {
  source: string
  written_as: string
  // What the cleaned file's own column of that name holds (stage 1's words).
  holds: string
}

export interface LineSummaryResponse {
  run_id: string
  reserved_renames: ReservedRename[]
  summary: LineSummary | null
  summary_unavailable_reason: string | null
}
