// The dashboard's tile icons and its strip (Thach's visual style, 2026-10-15; docs/DASHBOARD_DESIGN.md section 11):
// one small neutral icon per tile id, decorative; the tiles that stand in the strip of secondary KPIs under the
// chart cards. report.html draws the same (stages/report/html_dashboard.py TILE_ICONS, STRIP_TILES) - a pytest pins
// the two equal, one line per tile below.

import type { Tile } from '../types/reportDashboard.ts'

export const TILE_ICONS: Record<Tile['id'], string[]> = {
  sales: ['M4 20V10', 'M10 20V4', 'M16 20v-6', 'M3 20h18'],
  orders: ['M6 7h12l1 13H5L6 7Z', 'M9 7V6a3 3 0 0 1 6 0v1'],
  aov: ['M6 3h12v18l-3-2-3 2-3-2-3 2V3Z', 'M9 8h6', 'M9 12h6'],
  customers: ['M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M3 20a6 6 0 0 1 12 0', 'M16 5a3 3 0 0 1 0 6', 'M18 20a6 6 0 0 0-2.5-4.9'],
  return_rate: ['M9 14 4 9l5-5', 'M4 9h11a5 5 0 0 1 0 10h-3'],
}

export const STRIP_TILES: readonly Tile['id'][] = ['customers', 'return_rate']
