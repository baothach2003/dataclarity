// report.json 2.10's dashboard block (contracts/report_dashboard.py; docs/DASHBOARD_DESIGN.md): the KPI tiles and
// the widgets in the order stage 5 decided. Every figure is printed by stage 5; the page draws, it words none.

import type { NoteCode } from './report.ts'

export type TileId = 'sales' | 'orders' | 'aov' | 'customers' | 'return_rate'
export type WidgetId =
  | 'summary'
  | 'trend'
  | 'waterfall'
  | 'customers'
  | 'products'
  | 'category'
  | 'breakdown_1'
  | 'breakdown_2'
  | 'returns'
  | 'checklist'
  | 'next_steps'
  | 'next_month'
  | 'cannot_know'

export interface Tile {
  id: TileId
  label: string
  unit: 'money' | 'count' | 'ratio'
  now: string | null
  now_value: number | null
  was: string | null
  was_value?: number | null
  change: string | null
  direction: 'up' | 'down' | 'same' | null
  reason: string | null
  notes: NoteCode[]
}

export interface Bar {
  label: string
  now: number
  was: number | null
  now_text: string
  was_text: string | null
  is_blank: boolean
}

export interface Widget {
  id: WidgetId
  kind: 'chart' | 'text'
  chart: 'line' | 'waterfall' | 'bars' | 'diverging' | 'parts' | null
  placed_by: 'named' | 'size' | 'fallback'
  size: number | null
  title: string | null
  column: string | null
  bars: Bar[]
  caption: string[]
  notes: NoteCode[]
}

export interface Dashboard extends DashboardLayout {
  state: 'compared' | 'not_compared' | 'blocked'
  tiles: Tile[]
  not_shown: string[]
  caution: string[]
  widgets: Widget[]
}

// 2.11 (Thach's layout, 2026-10-15; docs/DASHBOARD_DESIGN.md section 10): the line under the tiles, the checked
// chips, the next-month and next-step bands. Optional: a report before 2.11 has none of them.
export interface Headline {
  text: string
  notes: NoteCode[]
  // The sentences behind the line's marker (the caution lines; a blocked report's sentence).
  asides: string[]
}

export type ChipStatus = 'checked' | 'matches' | 'moved' | 'other way' | "can't tell" | 'caution'

export interface Chip {
  label: string
  status: ChipStatus
}

export interface NextMonthBand {
  month: string | null
  figure: string | null
  value: number | null
  low: string | null
  low_value: number | null
  high: string | null
  high_value: number | null
  reason: string | null
  notes: NoteCode[]
  asides: string[]
}

export interface DashboardLayout {
  headline?: Headline | null
  checked?: Chip[]
  next_month?: NextMonthBand | null
  next_steps?: string[]
  // The notes beside the checked chips and the next steps (the front's).
  checked_notes?: NoteCode[]
  next_steps_notes?: NoteCode[]
}
