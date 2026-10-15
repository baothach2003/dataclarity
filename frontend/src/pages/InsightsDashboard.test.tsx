// The dashboard's step 5 (Thach's D7; docs/DASHBOARD_DESIGN.md section 8): Insights draws report.json's dashboard
// block - the tiles, the caution lines under them, then the widgets in the order stage 5 decided - the same block
// report.html draws. The page decides no order and words no figure. The fixtures are stage 5's real output on the
// three real runs (tests/contracts/front_fixtures.py proves it). Written before the page drew the block.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { bannedIn } from '../domain/frontBanned.ts'
import type { ReportContract } from '../types/report.ts'
import type { Dashboard, Widget } from '../types/reportDashboard.ts'
import demoClassed from './frontFixtures/demo_classed.json'
import demoUnanswered from './frontFixtures/demo_unanswered.json'
import kaggle from './frontFixtures/kaggle.json'
import kaggleGbp from './frontFixtures/kaggle_gbp.json'
import { InsightsPage } from './InsightsPage.tsx'

vi.mock('../api/analysis.ts', () => ({ downloadReportHtml: vi.fn() }))

afterEach(() => {
  cleanup()
  // Recharts' hidden tick-measuring span outlives each test (InsightsFront.test.tsx says why).
  document.getElementById('recharts_measurement_span')?.remove()
})

const RUNS: Record<string, { report: ReportContract }> = {
  kaggle: kaggle as unknown as { report: ReportContract },
  demo_classed: demoClassed as unknown as { report: ReportContract },
  demo_unanswered: demoUnanswered as unknown as { report: ReportContract },
  kaggle_gbp: kaggleGbp as unknown as { report: ReportContract },
}

function dashboardOf(report: ReportContract): Dashboard {
  if (!report.dashboard) {
    throw new Error('the fixture is a 2.10 report with its dashboard')
  }
  return report.dashboard
}

/** Opens the marker inside `where` and returns what it shows (CLAUDE.md 3.3a as amended: a note behind an "i"). */
function opened(where: HTMLElement): string {
  const marker = where.querySelector<HTMLButtonElement>('button.marker')
  if (!marker) {
    throw new Error('a marker stands there')
  }
  fireEvent.click(marker)
  return where.querySelector('.marker__panel')?.textContent ?? ''
}

function show(run: string, change?: (report: ReportContract) => void): ReportContract {
  const report = structuredClone(RUNS[run].report)
  change?.(report)
  render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
  return report
}

describe('Insights draws the dashboard block', () => {
  it.each(Object.keys(RUNS))('%s: the tiles first, each printing stage 5\'s own text', (run) => {
    const report = show(run)
    const { tiles } = dashboardOf(report)
    for (const tile of tiles) {
      const card = screen.getByTestId(`tile-${tile.id}`)
      expect(within(card).getByText(tile.label)).toBeTruthy()
      if (tile.now !== null) {
        expect(within(card).getByText(tile.now)).toBeTruthy()
      }
      if (tile.change !== null) {
        expect(card.textContent).toContain(tile.change)
      }
    }
    const first = screen.getByTestId(`tile-${tiles[0].id}`)
    const firstWidget = screen.getByTestId(`widget-${dashboardOf(report).widgets[0].id}`)
    expect(first.compareDocumentPosition(firstWidget) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it.each(Object.keys(RUNS))('%s: the widgets in report.json\'s order, none added, none dropped', (run) => {
    const report = show(run)
    const drawn = screen.getAllByTestId(/^widget-/).map((node) => node.dataset.testid?.replace('widget-', ''))
    // 2.11 (Thach's layout): the chart widgets are the cards; the text parts stand in Technical details.
    expect(drawn).toEqual(dashboardOf(report).widgets.filter((w) => w.kind === 'chart').map((w) => w.id))
  })

  it('Kaggle: the trend widget title is one heading, not two', () => {
    const report = show('kaggle')
    const trend = dashboardOf(report).widgets.find((w) => w.id === 'trend')
    if (!trend?.title) {
      throw new Error('the Kaggle report draws the trend')
    }
    expect(screen.getAllByRole('heading', { name: trend.title })).toHaveLength(1)
  })

  it('Kaggle: "was" beside last month\'s value, the month in the line under the tiles, the arrow worded', () => {
    show('kaggle')
    const orders = screen.getByTestId('tile-orders')
    // 2.11: a tile is its label, figure, arrow and change; "vs November 2024" is the line's.
    expect(orders.textContent).toContain('was 308')
    expect(screen.getByTestId('dashboard-headline').textContent).toContain('vs November 2024')
    expect(within(orders).getByRole('img', { name: 'higher than last month' })).toBeTruthy()
  })

  it('a caution stands under the tiles, before any widget - behind the line\'s marker (2.11)', () => {
    show('kaggle', (report) => {
      const dashboard = dashboardOf(report)
      dashboard.caution = ['Some days in December 2024 have no sales at all.']
      dashboard.headline?.asides.unshift('Some days in December 2024 have no sales at all.')
    })
    const line = screen.getByTestId('dashboard-headline')
    const firstWidget = screen.getAllByTestId(/^widget-/)[0]
    expect(line.compareDocumentPosition(firstWidget) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(opened(line)).toContain('Some days in December 2024 have no sales at all.')
  })

  it('a breakdown widget prints its bars\' texts; a negative bar runs left of zero', () => {
    const breakdown: Widget = {
      id: 'breakdown_1', kind: 'chart', chart: 'bars', placed_by: 'fallback', size: null, title: 'Sales by Desk',
      column: 'Desk', caption: [], notes: [],
      bars: [
        { label: 'Till', now: 48292.5, was: 41867.5, now_text: '48,292.50', was_text: '41,867.50', is_blank: false },
        { label: 'Returns desk', now: -2000, was: -500, now_text: '-2,000.00', was_text: '-500.00', is_blank: false },
      ],
    }
    show('kaggle', (report) => {
      dashboardOf(report).widgets.splice(1, 0, breakdown)
    })
    const card = screen.getByTestId('widget-breakdown_1')
    expect(card.textContent).toContain('-2,000.00')
    expect(card.textContent).toContain('was 41,867.50')
    // In the series colour since Thach's visual style (red is for change only): its place says it is negative.
    const negative = card.querySelectorAll('.hb-bar--now')[1]
    const zero = card.querySelectorAll('.hb-zero')[1]
    if (!(negative instanceof HTMLElement) || !(zero instanceof HTMLElement)) {
      throw new Error('the negative bar and its zero line are drawn')
    }
    expect(parseFloat(negative.style.left)).toBeLessThan(parseFloat(zero.style.left))
  })

  it('bars that are all sales start at zero: the smallest is not drawn as nothing', () => {
    const breakdown: Widget = {
      id: 'breakdown_1', kind: 'chart', chart: 'bars', placed_by: 'fallback', size: null, title: 'Sales by Desk',
      column: 'Desk', caption: [], notes: [],
      bars: [
        { label: 'Till', now: 400, was: null, now_text: '400.00', was_text: null, is_blank: false },
        { label: 'Web', now: 300, was: null, now_text: '300.00', was_text: null, is_blank: false },
      ],
    }
    show('kaggle', (report) => {
      dashboardOf(report).widgets.splice(1, 0, breakdown)
    })
    // One series of no negative value: each value at its bar's end (Thach's visual style), every bar from the
    // track's start, the longest the scale's whole.
    const bars = [...screen.getByTestId('widget-breakdown_1').querySelectorAll<HTMLElement>('.hb-fill')]
    expect(bars.map((bar) => parseFloat(bar.style.getPropertyValue('--w')))).toEqual([1, 0.75])
  })

  it('parts of a whole: a row per month and each part\'s figures in the legend', () => {
    const parts: Widget = {
      id: 'breakdown_1', kind: 'chart', chart: 'parts', placed_by: 'fallback', size: null, title: 'Sales by Channel',
      column: 'Channel', caption: ['Each part is one channel.'], notes: [],
      bars: [
        { label: 'Web', now: 300, was: 100, now_text: '300.00', was_text: '100.00', is_blank: false },
        { label: 'Shop', now: 100, was: 300, now_text: '100.00', was_text: '300.00', is_blank: false },
      ],
    }
    show('kaggle', (report) => {
      dashboardOf(report).widgets.splice(1, 0, parts)
    })
    const card = screen.getByTestId('widget-breakdown_1')
    expect(within(card).getByText('This month')).toBeTruthy()
    expect(within(card).getByText('Last month')).toBeTruthy()
    expect(within(card).getByText('Web: 300.00 (was 100.00)')).toBeTruthy()
    expect(within(card).getByText('Shop: 100.00 (was 300.00)')).toBeTruthy()
    expect(opened(card)).toContain('Each part is one channel.')  // 2.11: the caption behind the card's marker
    const widths = [...card.querySelectorAll<HTMLElement>('.hp-part')].map((part) => parseFloat(part.style.width))
    expect(widths).toEqual([75, 25, 25, 75])
  })

  it('a diverging chart colours a rise, a fall and no change apart', () => {
    const moves: Widget = {
      id: 'customers', kind: 'chart', chart: 'diverging', placed_by: 'size', size: 5, title: 'Customers',
      column: null, caption: [], notes: [],
      bars: [
        { label: 'New', now: 5, was: null, now_text: '+5.00', was_text: null, is_blank: false },
        { label: 'Stopped', now: -3, was: null, now_text: '-3.00', was_text: null, is_blank: false },
        { label: 'Back', now: 0, was: null, now_text: '0.00', was_text: null, is_blank: false },
      ],
    }
    show('kaggle', (report) => {
      const dashboard = dashboardOf(report)
      dashboard.widgets = [moves, ...dashboard.widgets.filter((w) => w.id !== 'customers')]
    })
    const kinds = [...screen.getByTestId('widget-customers').querySelectorAll('.hb-bar:not(.hb-marker)')].map((bar) => bar.className)
    expect(kinds).toEqual(['hb-bar hb-bar--up', 'hb-bar hb-bar--down', 'hb-bar hb-bar--flat'])
  })

  it('a tile with no comparison prints last month\'s value (its month in the line under the tiles)', () => {
    const report = show('kaggle', (r) => {
      for (const tile of dashboardOf(r).tiles) {
        tile.change = null
      }
    })
    for (const tile of dashboardOf(report).tiles) {
      if (tile.was !== null) {
        expect(screen.getByTestId(`tile-${tile.id}`).textContent).toContain(`was ${tile.was}`)
      }
    }
  })

  it('a not-compared report: the data checks line once, in the summary', () => {
    show('kaggle', (report) => {
      const front = report.front
      if (!front) {
        throw new Error('the fixture has its front')
      }
      front.state = 'not_compared'
      front.caution = []
      front.data_checks = ['Data checks: 2 of 3 passed.']
      const dashboard = dashboardOf(report)
      dashboard.state = 'not_compared'
      dashboard.caution = []
      dashboard.widgets = dashboard.widgets.filter((w) => ['summary', 'trend', 'next_month', 'cannot_know'].includes(w.id))
    })
    expect(screen.getAllByText('Data checks: 2 of 3 passed.')).toHaveLength(1)
    // 2.11: the summary's sentences stand in Technical details ("The dashboard in words").
    expect(within(screen.getByTestId('technical-details')).getByText('Data checks: 2 of 3 passed.')).toBeTruthy()
  })

  it('a blocked report: the sales tile\'s reason, no figure, three text widgets, the lines under the tiles', () => {
    show('kaggle', (report) => {
      const dashboard = dashboardOf(report)
      dashboard.state = 'blocked'
      dashboard.caution = []
      dashboard.tiles = [{ ...dashboard.tiles[0], now: null, now_value: null, was: null, was_value: null, change: null, direction: null,
        reason: 'The data did not pass its checks.' }]
      dashboard.not_shown = ['Orders are not shown: the data did not pass its checks.']
      dashboard.widgets = dashboard.widgets.filter((w) => ['summary', 'next_month', 'cannot_know'].includes(w.id))
      if (report.front) {
        report.front.state = 'blocked'
      }
    })
    const tile = screen.getByTestId('tile-sales')
    // 2.11: no figure - the two words "not shown", the reason behind the tile's marker; no chart card; the lines
    // under the tiles stand in Technical details.
    expect(tile.querySelector('.tile__value')?.textContent).toBe('not shown')
    expect(opened(tile)).toContain('The data did not pass its checks.')
    expect(within(screen.getByTestId('technical-details')).getByText('Orders are not shown: the data did not pass its checks.')).toBeTruthy()
    expect(screen.queryAllByTestId(/^widget-/)).toEqual([])
  })

  it('the summary carries the waterfall note once when the change cannot be split', () => {
    show('kaggle', (report) => {
      // As stage 5 writes it: no bridge, so no waterfall widget, and the note in its place.
      if (report.front) {
        report.front.waterfall = null
        report.front.waterfall_note = 'The change cannot be split this month.'
      }
      const dashboard = dashboardOf(report)
      dashboard.widgets = dashboard.widgets.filter((w) => w.id !== 'waterfall')
    })
    expect(screen.getAllByText('The change cannot be split this month.')).toHaveLength(1)
    expect(within(screen.getByTestId('technical-details')).getByText('The change cannot be split this month.')).toBeTruthy()
  })

  it('the trend\'s sentences stand even when no month can be drawn', () => {
    show('kaggle', (report) => {
      report.charts = report.charts.filter((chart) => chart.id !== 'revenue_trend')
      const trend = dashboardOf(report).widgets.find((w) => w.id === 'trend')
      if (trend) {
        trend.caption = ['January 2025 is not in the chart.']
      }
    })
    expect(opened(screen.getByTestId('widget-trend'))).toContain('January 2025 is not in the chart.')  // 2.11
  })

  it('a widget this page cannot draw is left out, never drawn as bars', () => {
    show('kaggle', (report) => {
      dashboardOf(report).widgets.push({
        id: 'returns', kind: 'chart', chart: 'line', placed_by: 'fallback', size: null, title: 'Refunds', column: null,
        caption: [], notes: [], bars: [],
      })
    })
    expect(screen.queryByTestId('widget-returns')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Refunds' })).toBeNull()
  })

  it('a widget id this page does not know (a later, additive one) is left out', () => {
    show('kaggle', (report) => {
      const later = { ...dashboardOf(report).widgets[0], id: 'margins', title: 'Margins' } as unknown as Widget
      dashboardOf(report).widgets.push(later)
    })
    expect(screen.queryByTestId('widget-margins')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Margins' })).toBeNull()
  })

  it('no banned word outside Technical details', () => {
    show('demo_classed')
    const page = document.body.cloneNode(true) as HTMLElement
    page.querySelector('[data-testid="technical-details"]')?.remove()
    expect(bannedIn(page.textContent)).toEqual([])
  })

  it('a report before 2.10 draws its front section as before', () => {
    show('kaggle', (report) => {
      report.dashboard = undefined
    })
    expect(screen.queryByTestId('tile-sales')).toBeNull()
    expect(screen.getByText('In 30 seconds')).toBeTruthy()
  })
})
