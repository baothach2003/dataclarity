// Thach's layout decision (2026-10-15; docs/DASHBOARD_DESIGN.md section 10): the dashboard is pictures and
// figures. Row 1 the tiles (label, figure, arrow, change); row 2 one short line; row 3 the chart cards, no caption
// under a chart; row 4 full-width bands (next month, checked chips, next step); every long text in Technical
// details; a note where its figure is, as a marker that opens its sentence (CLAUDE.md 3.3a as amended). The
// page draws report.json 2.11's block - the same block report.html draws (D7). Written before the page drew it.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { NoteView, ReportContract } from '../types/report.ts'
import type { Dashboard } from '../types/reportDashboard.ts'
import demoClassed from './frontFixtures/demo_classed.json'
import demoUnanswered from './frontFixtures/demo_unanswered.json'
import kaggle from './frontFixtures/kaggle.json'
import kaggleGbp from './frontFixtures/kaggle_gbp.json'
import { InsightsPage } from './InsightsPage.tsx'

vi.mock('../api/analysis.ts', () => ({ downloadReportHtml: vi.fn() }))

afterEach(() => {
  cleanup()
  document.getElementById('recharts_measurement_span')?.remove()
})

const RUNS: Record<string, { report: ReportContract }> = {
  kaggle: kaggle as unknown as { report: ReportContract },
  demo_classed: demoClassed as unknown as { report: ReportContract },
  demo_unanswered: demoUnanswered as unknown as { report: ReportContract },
  kaggle_gbp: kaggleGbp as unknown as { report: ReportContract },
}

function dashboardOf(report: ReportContract): Dashboard {
  if (!report.dashboard?.headline) {
    throw new Error('the fixture is a 2.11 report with its dashboard line')
  }
  return report.dashboard
}

function show(run: string, change?: (report: ReportContract) => void): ReportContract {
  const report = structuredClone(RUNS[run].report)
  change?.(report)
  render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
  return report
}

function notesOf(report: ReportContract): Map<string, NoteView> {
  return new Map([...report.layer_1_numbers.notes, ...report.layer_2_causes.notes].map((note) => [note.code, note]))
}

describe('Insights: pictures and figures, almost no text', () => {
  it.each(Object.keys(RUNS))('%s: the line under the tiles is report.json\'s, before the first chart', (run) => {
    const report = show(run)
    const line = screen.getByTestId('dashboard-headline')
    expect(line.textContent).toContain(dashboardOf(report).headline?.text)
    const firstChart = screen.getAllByTestId(/^widget-/)[0]
    expect(line.compareDocumentPosition(firstChart) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it.each(Object.keys(RUNS))('%s: no paragraph outside Technical details, the line and the bands', (run) => {
    show(run)
    const dashboard = screen.getByTestId('dashboard')
    const stray = [...dashboard.querySelectorAll('p')].filter(
      // A chart's own internals (Recharts' tooltip label) are no paragraph of the dashboard.
      (p) => !p.closest('.band, .dashboard-headline, .marker__panel, .visually-hidden, .chart-frame'),
    )
    expect(stray.map((p) => p.textContent)).toEqual([])
  })

  it.each(Object.keys(RUNS))('%s: only the chart widgets are cards, in report.json\'s order', (run) => {
    const report = show(run)
    const drawn = screen.getAllByTestId(/^widget-/).map((node) => node.dataset.testid?.replace('widget-', ''))
    expect(drawn).toEqual(dashboardOf(report).widgets.filter((w) => w.kind === 'chart').map((w) => w.id))
  })

  it('Kaggle: a tile is its label, figure, arrow and change - "was 308", no month, no sentence', () => {
    show('kaggle')
    const orders = screen.getByTestId('tile-orders')
    expect(orders.textContent).toContain('was 308')
    expect(orders.textContent).not.toContain('November 2024')
    expect(within(screen.getByTestId('tile-sales')).getByText('+4,925.00 (+11.9%)', { exact: false })).toBeTruthy()
  })

  it.each(Object.keys(RUNS))('%s: every note marker is present where its figure is, and opens its sentence', (run) => {
    const report = show(run)
    const dashboard = dashboardOf(report)
    const notes = notesOf(report)
    const places: [HTMLElement, string[]][] = [
      ...dashboard.tiles.filter((t) => t.notes.length > 0).map((t): [HTMLElement, string[]] => [screen.getByTestId(`tile-${t.id}`), t.notes]),
      ...dashboard.widgets
        .filter((w) => w.kind === 'chart' && w.notes.length > 0)
        .map((w): [HTMLElement, string[]] => [screen.getByTestId(`widget-${w.id}`), w.notes]),
    ]
    if (dashboard.headline && dashboard.headline.notes.length > 0) {
      places.push([screen.getByTestId('dashboard-headline'), dashboard.headline.notes])
    }
    for (const [where, codes] of places) {
      const marker = [...where.querySelectorAll<HTMLButtonElement>('button.marker')].find((b) => b.dataset.notes === codes.join(' '))
      if (!marker) {
        throw new Error(`a marker for ${codes.join(' ')} beside its figure`)
      }
      expect(marker.getAttribute('aria-expanded')).toBe('false')
      expect(marker.getAttribute('aria-label')).toMatch(/^About /)
      fireEvent.click(marker)
      expect(marker.getAttribute('aria-expanded')).toBe('true')
      const panel = document.getElementById(marker.getAttribute('aria-controls') ?? '')
      for (const code of codes) {
        expect(panel?.textContent).toContain(notes.get(code)?.text)
      }
    }
  })

  it('Kaggle: the trend\'s caption stands behind its marker, not under the chart', () => {
    const report = show('kaggle')
    const trend = dashboardOf(report).widgets.find((w) => w.id === 'trend')
    const caption = trend?.caption[0]
    if (!caption) {
      throw new Error('the Kaggle trend has a caption (January 2025 is not in the chart)')
    }
    const card = screen.getByTestId('widget-trend')
    const marker = card.querySelector<HTMLButtonElement>('button.marker')
    if (!marker) {
      throw new Error('the trend card has a marker')
    }
    // The panel exists for aria-controls, hidden and empty until opened (the review's nit).
    expect(card.querySelector<HTMLElement>('.marker__panel')?.hidden).toBe(true)
    expect(card.querySelector('.marker__panel')?.textContent).toBe('')
    fireEvent.click(marker)
    expect(card.querySelector('.marker__panel')?.textContent).toContain(caption)
  })

  it.each(Object.keys(RUNS))('%s: next month is its figure and range, as numbers, in a full-width band', (run) => {
    const report = show(run)
    const band = dashboardOf(report).next_month
    const drawn = screen.getByTestId('band-next-month')
    if (band?.figure && band.low && band.high) {
      for (const figure of [band.figure, band.low, band.high]) {
        expect(drawn.textContent).toContain(figure)
      }
    }
  })

  it.each(['kaggle', 'demo_classed'])('%s: checked is one row of chips, in report.json\'s order', (run) => {
    const report = show(run)
    const chips = within(screen.getByTestId('band-checked')).getAllByRole('listitem')
    // `checked` is optional in a 2.10 report's type: these 2.11 fixtures hold it.
    const checked = dashboardOf(report).checked ?? []
    expect(checked.length).toBeGreaterThan(0)
    expect(chips.map((chip) => chip.dataset.status)).toEqual(checked.map((c) => c.status))
    checked.forEach((chip, index) => {
      expect(chips[index].textContent).toContain(chip.label)
    })
  })

  it('no next-step band without an action; one line per action with one', () => {
    show('demo_classed')
    expect(screen.queryByTestId('band-next-steps')).toBeNull()
    cleanup()
    const report = show('kaggle')
    const steps = dashboardOf(report).next_steps ?? []
    expect(steps.length).toBeGreaterThan(0)
    expect(within(screen.getByTestId('band-next-steps')).getAllByRole('listitem').map((li) => li.textContent)).toEqual(steps)
  })

  it.each(Object.keys(RUNS))('%s: no mock label in anything a user sees', (run) => {
    show(run)
    const text = document.body.textContent.toLowerCase()
    for (const label of ['placed by', 'mock', 'fixed order', 'placed_by']) {
      expect(text).not.toContain(label)
    }
  })

  it('Kaggle: Technical details holds the long texts - the summary, the checklist, what this report cannot know', () => {
    const report = show('kaggle')
    const details = screen.getByTestId('technical-details')
    const front = report.front
    if (!front) {
      throw new Error('the fixture has its front')
    }
    for (const line of [...front.summary, ...front.checklist.flatMap((g) => g.lines), ...front.cannot_know.map((c) => c.text)]) {
      expect(details.textContent).toContain(line)
    }
    expect(screen.getByTestId('dashboard').textContent).not.toContain(front.summary[0])
  })

  it('Kaggle: the waterfall draws its bars across at every width (its columns\' labels overlapped at 1440 px)', () => {
    show('kaggle')
    const card = screen.getByTestId('widget-waterfall')
    expect(card.querySelector('[data-layout="across"]')).not.toBeNull()
  })
})

describe('Insights: the layout review cycle', () => {
  it('Kaggle: the waterfall card keeps its key "0 = <last month>" - report.html draws it too', () => {
    const report = show('kaggle')
    const waterfall = report.front?.waterfall
    if (!waterfall) {
      throw new Error('the Kaggle front draws the waterfall')
    }
    expect(screen.getByTestId('widget-waterfall').textContent).toContain(`0 = ${waterfall.previous_label} (${waterfall.previous_text})`)
  })

  it.each(Object.keys(RUNS))('%s: the checked band carries its notes behind a marker', (run) => {
    const report = show(run)
    const codes = dashboardOf(report).checked_notes ?? []
    const band = screen.getByTestId('band-checked')
    const marker = band.querySelector<HTMLButtonElement>('button.marker')
    if (codes.length === 0) {
      expect(marker).toBeNull()
      return
    }
    expect(marker?.dataset.notes).toBe(codes.join(' '))
  })

  it('a marker controls a panel that exists, hidden until opened', () => {
    show('demo_classed')
    const marker = screen.getByTestId('tile-orders').querySelector<HTMLButtonElement>('button.marker')
    const panel = document.getElementById(marker?.getAttribute('aria-controls') ?? '')
    expect(panel?.hidden).toBe(true)
    if (marker) {
      fireEvent.click(marker)
    }
    expect(panel?.hidden).toBe(false)
  })

  it('a report before 2.11 (no line under the tiles) draws its front section as it was', () => {
    show('kaggle', (report) => {
      const dashboard = dashboardOf(report)
      dashboard.headline = null
    })
    expect(screen.getByText('In 30 seconds')).toBeTruthy()
    expect(screen.queryByTestId('dashboard')).toBeNull()
  })
})
