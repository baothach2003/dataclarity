// Thach's visual style (2026-10-15; docs/DASHBOARD_DESIGN.md section 11) on the Insights page, as report.html draws
// it (tests/stages/report/test_dashboard_visual.py): the main KPI row (a small decorative icon per tile, the change
// under the figure), the chart cards, a strip of secondary KPIs; green and red only on the arrow and the waterfall;
// a second series only where two months are compared, with its legend; top products with the value at the bar's
// end; the palette's tokens, dark selected. Written before the page drew it.

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { STRIP_TILES, TILE_ICONS, TILE_POLARITY } from '../components/dashboardIcons.ts'
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

// Thach's Q10 (2026-10-16): the arrow's colour by the metric's fixed polarity - sales, orders, AOV, customers up =
// good (green); the return rate down = good (green). A property of the metric, not a verdict on the month.
describe('Insights: the arrow colour by polarity (Q10)', () => {
  function arrowOf(tileId: string): Element | null {
    return screen.getByTestId(`tile-${tileId}`).querySelector('.tile__arrow')
  }

  it('the page holds the same polarity table as report.html', () => {
    expect(TILE_POLARITY).toEqual({ sales: 1, orders: 1, aov: 1, customers: 1, return_rate: -1 })
  })

  it('demo: a falling return rate is green, a falling average red, the rest green', () => {
    show('demo_classed')
    expect(arrowOf('return_rate')?.className).toBe('tile__arrow tile__arrow--down tile__arrow--good')
    expect(arrowOf('return_rate')?.getAttribute('aria-label')).toBe('lower than last month')
    expect(arrowOf('return_rate')?.textContent).toBe('▼')
    expect(arrowOf('aov')?.className).toBe('tile__arrow tile__arrow--down tile__arrow--bad')
    for (const id of ['sales', 'orders', 'customers']) {
      expect(arrowOf(id)?.className).toBe('tile__arrow tile__arrow--up tile__arrow--good')
    }
  })

  it.each([
    ['return_rate', 'up', 'tile__arrow tile__arrow--up tile__arrow--bad'],
    ['customers', 'down', 'tile__arrow tile__arrow--down tile__arrow--bad'],
    ['return_rate', 'same', 'tile__arrow tile__arrow--same'],
  ] as const)('%s %s: %s', (tileId, direction, expected) => {
    const report = structuredClone(RUNS.demo_classed)
    const tile = report.dashboard?.tiles.find((t) => t.id === tileId)
    if (tile) tile.direction = direction
    render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
    expect(arrowOf(tileId)?.className).toBe(expected)
  })
})

// Thach's D-23 addition (2026-10-16): the good/bad meaning without visible words - screen-reader-only text after the
// direction and the figure (", good" / ", bad") and a title on the arrow ("Higher is better" / "Lower is better").
describe('Insights: good or bad said without visible words (D-23)', () => {
  const BETTER = { 1: 'Higher is better', '-1': 'Lower is better' } as const
  const IDS = ['sales', 'orders', 'aov', 'customers', 'return_rate'] as const

  function showWith(tileId: string, direction: 'up' | 'down' | 'same'): HTMLElement {
    const report = structuredClone(RUNS.demo_classed)
    const tile = report.dashboard?.tiles.find((t) => t.id === tileId)
    if (tile) tile.direction = direction
    render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
    const change = screen.getByTestId(`tile-${tileId}`).querySelector<HTMLElement>('.tile__change')
    if (change === null) throw new Error(`${tileId}: no change line`)
    return change
  }

  function visible(element: HTMLElement): string {
    const copy = element.cloneNode(true) as HTMLElement
    copy.querySelectorAll('.visually-hidden').forEach((hidden) => {
      hidden.remove()
    })
    return copy.textContent
  }

  for (const tileId of IDS) {
    for (const direction of ['up', 'down'] as const) {
      it(`${tileId} ${direction}: the screen-reader text follows the polarity table`, () => {
        const change = showWith(tileId, direction)
        const good = (direction === 'up' ? 1 : -1) === TILE_POLARITY[tileId]
        const hidden = change.querySelectorAll('.visually-hidden')
        expect(hidden.length).toBe(1)
        expect(hidden[0].textContent).toBe(good ? ', good' : ', bad')
        expect(change.lastElementChild).toBe(hidden[0])
        expect(change.querySelector('.tile__arrow')?.getAttribute('title')).toBe(BETTER[TILE_POLARITY[tileId]])
        expect(visible(change)).not.toMatch(/good|bad|better/i)
      })
    }

    it(`${tileId} same: no good or bad, the metric's title kept, no new visible word`, () => {
      const change = showWith(tileId, 'same')
      expect(change.querySelector('.visually-hidden')).toBeNull()
      expect(change.querySelector('.tile__arrow')?.getAttribute('title')).toBe(BETTER[TILE_POLARITY[tileId]])
      expect(visible(change)).not.toMatch(/good|bad|better/i)
    })
  }
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
