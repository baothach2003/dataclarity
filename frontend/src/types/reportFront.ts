// report.json 2.9's front section (contracts/report_front.py; docs/REPORT_REDESIGN.md sections 1 and 8): the
// code-written sentences and bars a shop owner reads first - ONE copy, which report.html prints and the
// Insights page prints the same. Every figure in them is a field of an earlier file, formatted by stage 5;
// the page words none and computes none (CONTRACTS 9 and 11).

import type { NoteCode } from './report.ts'

export type Factor = 'customers' | 'frequency' | 'orders' | 'aov' | 'units_per_order' | 'price_per_unit'

export interface FrontBar {
  factor: Factor
  label: string
  was: string
  now: string
  // What the part added or took away: the bridge's shown cents (diagnosis.json tree.lever.bridge.bars[].shown).
  shown: number
  worth: string
}

export interface Waterfall {
  previous_label: string
  current_label: string
  shown_previous: number
  shown_current: number
  shown_change: number
  previous_text: string
  current_text: string
  change_text: string
  bars: FrontBar[]
  caption: string
  // Why the order value is one bar (the split withheld; Q1); null when drawn.
  note: string | null
}

export interface ChecklistGroup {
  kind: 'matches' | 'moved' | 'against' | 'not_reason' | 'cannot_show'
  title: string
  note: string | null
  lines: string[]
  after: string | null
}

export interface FrontAction {
  rests_on: string
  action: string
  why: string
  watch: string
}

export interface NextSteps {
  status: 'off' | 'suppressed' | 'list' | 'unavailable'
  sentence: string | null
  items: FrontAction[]
}

export interface FrontNotes {
  summary: NoteCode[]
  change: NoteCode[]
  checked: NoteCode[]
  next_month: NoteCode[]
  next_steps: NoteCode[]
}

export interface CannotKnow {
  title: string
  text: string
}

export interface Front {
  state: 'compared' | 'not_compared' | 'blocked'
  caution: string[]
  summary: string[]
  sales_note: string
  chart_title: string
  chart_note: string[]
  waterfall: Waterfall | null
  waterfall_note: string | null
  checklist: ChecklistGroup[]
  data_checks: string[]
  next_steps: NextSteps | null
  next_month: string[]
  cannot_know: CannotKnow[]
  notes: FrontNotes
}

// The currency the amounts are in (Q8): its ISO code on every amount, or none and the one sentence.
export interface ReportCurrency {
  code: string | null
  sentence: string | null
}

export interface RowsLeftOut {
  action: string
  column: string | null
  rows: number
  sentence: string
}

// diagnosis.json tree.lever.bridge (CONTRACTS 11's FE rows): what the waterfall draws, read only to prove it.
export interface BridgeBar {
  factor: Factor
  value_prev: number
  value_cur: number
  contribution: number
  shown: number
}

export interface Bridge {
  revenue_previous: number
  revenue_current: number
  change: number
  shown_previous: number
  shown_current: number
  shown_change: number
  bars: BridgeBar[]
  aov_split: boolean
  aov_split_withheld: 'refund_lines' | 'aov_unchanged' | 'net_units_not_positive' | null
}

// report.json layer_2_causes.lever_levels (contracts/report_front.py LeverLevelView).
export interface LeverTerm {
  name: Factor
  value_prev: number
  value_cur: number
  contribution: number
}

export interface LeverLevelView {
  level: 'level1' | 'level2' | 'pair'
  formula: string
  factors: LeverTerm[]
}
