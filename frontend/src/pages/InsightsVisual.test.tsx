// Thach's visual style (2026-10-15; docs/DASHBOARD_DESIGN.md section 11) on the Insights page, as report.html draws
// it (tests/stages/report/test_dashboard_visual.py): the main KPI row (a small decorative icon per tile, the change
// under the figure), the chart cards, a strip of secondary KPIs; green and red only on the arrow and the waterfall;
// a second series only where two months are compared, with its legend; top products with the value at the bar's
// end; the palette's tokens, dark selected. Written before the page drew it.

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STRIP_TILES, TILE_ICONS } from '../components/dashboardIcons.ts'
import { waterfallRows } from '../domain/frontView.ts'
import type { ReportContract } from '../types/report.ts'
import demoClassed from './frontFixtures/demo_classed.json'
import kaggle from './frontFixtures/kaggle.json'
import { InsightsPage } from './InsightsPage.tsx'

vi.mock('../api/analysis.ts', () => ({ downloadReportHtml: vi.fn() }))

afterEach(() => {
  cleanup()
  document.getElementById('recharts_measurement_span')?.remove()
})

const RUNS: Record<string, ReportContract> = {
  kaggle: (kaggle as unknown as { report: ReportContract }).report,
  demo_classed: (demoClassed as unknown as { report: ReportContract }).report,
}

function show(run: string): ReportContract {
  const report = structuredClone(RUNS[run])
  render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
  return report
}

function tileIds(block: HTMLElement): string[] {
  return Array.from(block.querySelectorAll('[data-testid^="tile-"]')).map((t) => (t.getAttribute('data-testid') ?? '').slice(5))
}

describe('Insights: the reference layout', () => {
  it('the main row holds sales, orders and AOV; the strip, after the cards and before the bands, the rest', () => {
    show('demo_classed')
    expect(tileIds(screen.getByTestId('kpi-main'))).toEqual(['sales', 'orders', 'aov'])
    const strip = screen.getByTestId('kpi-strip')
    expect(tileIds(strip)).toEqual(['customers', 'return_rate'])
    const lastCard = screen.getAllByTestId(/^widget-/).at(-1)
    expect(lastCard && lastCard.compareDocumentPosition(strip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(strip.compareDocumentPosition(screen.getByTestId('band-next-month')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('kaggle: customers in the strip, no return rate', () => {
    show('kaggle')
    expect(tileIds(screen.getByTestId('kpi-strip'))).toEqual(['customers'])
  })

  it.each(Object.keys(RUNS))('%s: each tile has its small decorative icon, the paths report.html draws', (run) => {
    const report = show(run)
    for (const tile of report.dashboard?.tiles ?? []) {
      const svg = screen.getByTestId(`tile-${tile.id}`).querySelector('svg.tile__icon')
      expect(svg?.getAttribute('aria-hidden')).toBe('true')
      expect(svg?.getAttribute('focusable')).toBe('false')
      expect(Array.from(svg?.querySelectorAll('path') ?? []).map((p) => p.getAttribute('d'))).toEqual(TILE_ICONS[tile.id])
    }
    expect(STRIP_TILES).toEqual(['customers', 'return_rate'])
  })

  it('the arrow wears the change colour, the change text does not', () => {
    show('kaggle')
    const sales = screen.getByTestId('tile-sales')
    const arrow = sales.querySelector('.tile__arrow')
    expect(arrow?.classList.contains('tile__arrow--up')).toBe(true)
    const change = sales.querySelector('.tile__change')
    expect(change?.className).toBe('tile__change')
  })
})

describe('Insights: the charts', () => {
  it.each(Object.keys(RUNS))('%s: a chart of two months has a legend, and no change colour', (run) => {
    show(run)
    for (const card of screen.getAllByTestId(/^widget-/)) {
      if (card.querySelector('.hb-bar--was')) {
        const legend = card.querySelector('.legend2')
        expect(legend).not.toBeNull()
        expect(Array.from(legend?.querySelectorAll('li') ?? []).map((li) => li.textContent)).toEqual(['This month', 'Last month'])
        expect(card.querySelector('.hb-bar--up, .hb-bar--down')).toBeNull()
      }
    }
  })

  it.each(Object.keys(RUNS))('%s: top products by sales, each value at its bar\'s end, no quantity', (run) => {
    const report = show(run)
    const card = screen.getByTestId('widget-products')
    const bars = report.dashboard?.widgets.find((w) => w.id === 'products')?.bars ?? []
    const rows = card.querySelectorAll('.hb-row--end')
    expect(rows.length).toBe(bars.length)
    rows.forEach((row, index) => {
      const track = row.querySelector('.hb-track--end')
      expect(track?.children[0].className).toBe('hb-fill')
      expect(track?.children[1].textContent).toBe(bars[index].now_text)
      expect(row.getAttribute('title')).toBe(`${bars[index].label}: ${bars[index].now_text}`)
    })
    expect(card.textContent).not.toMatch(/quantit|units|\bqty\b/i)
  })

  it.each(Object.keys(RUNS))('%s: each waterfall bar label carries its arrow; the whole change none', (run) => {
    const waterfall = RUNS[run].front?.waterfall
    if (!waterfall) {
      throw new Error('the fixture draws a waterfall')
    }
    const rows = waterfallRows(waterfall)
    waterfall.bars.forEach((bar, index) => {
      const arrow = Math.round(bar.shown * 100) > 0 ? '▲ ' : Math.round(bar.shown * 100) < 0 ? '▼ ' : ''
      expect(rows[index].printed).toBe(`${arrow}${bar.worth}`)
    })
    expect(rows.at(-1)?.printed).toBe(waterfall.change_text)
  })
})

// The palette's tokens, light and dark (selected), are pinned by tests/stages/report/test_dashboard_visual.py,
// which reads styles/tokens.css beside report.html's own (a CSS module reads as empty under this test runner).
