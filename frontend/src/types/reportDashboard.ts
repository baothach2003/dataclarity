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

export interface Dashboard {
  state: 'compared' | 'not_compared' | 'blocked'
  tiles: Tile[]
  not_shown: string[]
  caution: string[]
  widgets: Widget[]
}
