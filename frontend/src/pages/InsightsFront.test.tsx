// The report redesign's step 5 (docs/REPORT_REDESIGN.md section 8): Insights opens with report.json's front
// section - one copy of the wording, the page words no figure - and today's cards move behind "Technical
// details". The fixtures are stage 5's real output on the three real runs (tests/contracts/front_fixtures.py
// proves it). Written before the code.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FRONT_BANNED, bannedIn } from '../domain/frontBanned.ts'
import { waterfallRows } from '../domain/frontView.ts'
import type { Bridge, Front, Waterfall } from '../types/reportFront.ts'
import type { ReportContract } from '../types/report.ts'
import demoClassed from './frontFixtures/demo_classed.json'
import demoUnanswered from './frontFixtures/demo_unanswered.json'
import kaggle from './frontFixtures/kaggle.json'
import kaggleGbp from './frontFixtures/kaggle_gbp.json'
import { InsightsPage } from './InsightsPage.tsx'

vi.mock('../api/analysis.ts', () => ({ downloadReportHtml: vi.fn() }))

afterEach(() => {
  cleanup()
})

interface FrontFixture {
  report: ReportContract
  bridge: Bridge
}

const RUNS: Record<string, FrontFixture> = {
  kaggle: kaggle as unknown as FrontFixture,
  demo_classed: demoClassed as unknown as FrontFixture,
  demo_unanswered: demoUnanswered as unknown as FrontFixture,
  kaggle_gbp: kaggleGbp as unknown as FrontFixture,
}

function show(run: string) {
  const { report } = structuredClone(RUNS[run])
  render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
  return report
}

/** A value the fixture has: the test fails plainly where it does not. */
function given<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) {
    throw new Error('the fixture lacks this value')
  }
  return value
}

function frontOf(report: ReportContract): Front {
  return given(report.front)
}

function waterfallOf(report: ReportContract): Waterfall {
  return given(frontOf(report).waterfall)
}

function technical(): HTMLElement {
  return screen.getByTestId('technical-details')
}

/** The page's text outside the "Technical details" toggle, each text node apart - textContent glues
 * neighbouring elements together ("you can shareDownload"), hiding a word at an element's end (step 5's
 * review). */
function outsideTheToggle(): string {
  const page = document.body.cloneNode(true) as HTMLElement
  page.querySelector('[data-testid="technical-details"]')?.remove()
  const walker = document.createTreeWalker(page, NodeFilter.SHOW_TEXT)
  const parts: string[] = []
  for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
    parts.push(node.textContent ?? '')
  }
  return parts.join(' ')
}

describe('Insights opens with the front section', () => {
  it.each(Object.keys(RUNS))('uses no analyst word or banned word outside the toggle (%s)', (run) => {
    show(run)

    expect(bannedIn(outsideTheToggle())).toEqual([])
  })

  it('knows every word the contract bans (contracts/report_front.py FRONT_BANNED, pinned by pytest)', () => {
    expect(FRONT_BANNED).toContain('hypothesis')
    expect(bannedIn('Revenue rose; the lever and its share')).toEqual(['lever', 'share', 'revenue'])
    expect(bannedIn('sales rose')).toEqual([])
  })

  it.each(Object.keys(RUNS))("prints the front block's sentences as written (%s)", (run) => {
    const report = show(run)
    const front = frontOf(report)

    for (const line of [...front.caution, ...front.summary, front.sales_note, ...front.next_month]) {
      expect(screen.getByText(line)).toBeDefined()
    }
    for (const item of front.cannot_know) {
      expect(screen.getByText(item.text, { exact: false })).toBeDefined()
    }
  })

  it('puts the KPI cards, the hypothesis table and the limits behind a closed "Technical details" toggle', () => {
    show('kaggle')
    const toggle = technical()

    expect(toggle.tagName).toBe('DETAILS')
    expect((toggle as HTMLDetailsElement).open).toBe(false)
    expect(within(toggle).getByText('Technical details')).toBeDefined()
    expect(within(toggle).getAllByTestId('kpi-label')).toHaveLength(5)
    expect(within(toggle).getByRole('table', { name: /hypothes/i })).toBeDefined()
    expect(within(toggle).getByText('What this data cannot test')).toBeDefined()
    expect(screen.queryByText('Data trust: trusted', { exact: false })?.closest('[data-testid="technical-details"]')).toBe(toggle)
  })

  it('shows the front before the toggle', () => {
    const report = show('kaggle')
    const summary = screen.getByText(frontOf(report).summary[0])

    expect(summary.compareDocumentPosition(technical()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })
})

describe('the waterfall draws the bridge (Q17)', () => {
  it.each(['kaggle', 'demo_classed', 'demo_unanswered'])("its bars are bridge.bars[].shown, in order (%s)", (run) => {
    const { report, bridge } = RUNS[run]
    const rows = waterfallRows(waterfallOf(report))

    expect(rows.slice(0, -1).map((row) => row.shown)).toEqual(bridge.bars.map((bar) => bar.shown))
    expect(rows.slice(0, -1).map((row) => row.factor)).toEqual(bridge.bars.map((bar) => bar.factor))
    // Each part from where the last ended, last month's sales at zero; then the whole change.
    let level = 0
    for (const row of rows.slice(0, -1)) {
      expect(row.range).toEqual([level, level + row.shown].sort((a, b) => a - b))
      level += row.shown
    }
    expect(rows.at(-1)).toMatchObject({ factor: null, shown: bridge.shown_change, range: [0, bridge.shown_change].sort((a, b) => a - b) })
  })

  it.each(['kaggle', 'demo_classed', 'demo_unanswered'])('lists each bar with its words as stage 5 wrote them (%s)', (run) => {
    const report = show(run)
    const waterfall = waterfallOf(report)
    const table = screen.getByRole('table', { name: 'Where the change came from' })

    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows.map((row) => row.textContent)).toEqual([
      ...waterfall.bars.map((bar) => `${bar.label}${bar.was} → ${bar.now}${bar.worth}`),
      `Total change${waterfall.change_text}`,
    ])
  })

  it.each(['demo_classed', 'demo_unanswered'])('never draws the basket split when the bridge withholds it (%s)', (run) => {
    const { bridge } = RUNS[run]
    const report = show(run)
    const rows = waterfallRows(waterfallOf(report))

    expect(bridge.aov_split).toBe(false)
    expect(rows.map((row) => row.factor)).not.toContain('units_per_order')
    expect(rows.map((row) => row.factor)).not.toContain('price_per_unit')
    expect(screen.getByText(given(waterfallOf(report).note))).toBeDefined()
    const table = screen.getByRole('table', { name: 'Where the change came from' })
    const parts = within(table).getAllByRole('rowheader').map((cell) => cell.textContent)
    expect(parts).not.toContain('Items per order')
    expect(parts).not.toContain('Average price per item')
  })

  it('draws the split where the bridge has it (kaggle)', () => {
    const { bridge, report } = RUNS.kaggle

    expect(bridge.aov_split).toBe(true)
    expect(waterfallRows(waterfallOf(report)).map((row) => row.factor)).toEqual([
      'customers', 'frequency', 'units_per_order', 'price_per_unit', null,
    ])
  })
})

describe('sales by month', () => {
  it('is titled "Sales by month (before any costs)" with the partial-month sentence', () => {
    const report = show('kaggle')

    expect(screen.getByRole('heading', { name: 'Sales by month (before any costs)' })).toBeDefined()
    expect(frontOf(report).chart_note[0]).toMatch(/^January 2025 is not in the chart/)
    expect(screen.getByText(frontOf(report).chart_note[0])).toBeDefined()
  })
})

describe('the currency', () => {
  it('puts the ISO code on amounts and never on a count (kaggle confirmed as GBP)', () => {
    show('kaggle_gbp')
    const toggle = technical()
    const card = (label: string) => within(toggle).getByText(label, { selector: '[data-testid="kpi-label"]' }).closest('.kpi-card') as HTMLElement

    expect(within(card('Revenue')).getByTestId('kpi-value').textContent).toBe('GBP 46,292.50')
    expect(within(card('Orders')).getByTestId('kpi-value').textContent).toBe('343')
    expect(within(card('Active customers')).getByTestId('kpi-value').textContent).not.toContain('GBP')
    expect(document.body.textContent).not.toMatch(/GBP \d+ (orders|customers|lines|months)/)
    expect(document.body.textContent).toContain('Amounts are in GBP.')
  })

  it("says once that amounts are in the file's currency when none was stated", () => {
    show('kaggle')

    expect(document.body.textContent.split("Amounts are in your file's currency.")).toHaveLength(2)
    expect(document.body.textContent).not.toMatch(/\b(GBP|EUR|USD|AUD) \d/)
  })
})

describe('what to do next', () => {
  it('lists each action as stage 4 wrote it (kaggle)', () => {
    const report = show('kaggle')
    const section = screen.getByRole('region', { name: 'What to do next' })
    const item = given(frontOf(report).next_steps).items[0]

    expect(within(section).getByText(`Rests on: ${item.rests_on}`)).toBeDefined()
    expect(within(section).getByText(item.action)).toBeDefined()
    expect(within(section).getByText(item.why)).toBeDefined()
    expect(within(section).getByText(item.watch)).toBeDefined()
  })

  it('says why nothing is suggested (demo_classed)', () => {
    const report = show('demo_classed')
    const section = screen.getByRole('region', { name: 'What to do next' })

    expect(within(section).getByText(given(given(frontOf(report).next_steps).sentence))).toBeDefined()
  })
})

describe('the notes beside the figures', () => {
  it("open the toggle at the note's sentence", () => {
    const report = show('demo_classed')
    const code = frontOf(report).notes.summary[0]
    expect(code).toBeDefined()

    fireEvent.click(screen.getAllByRole('link', { name: code.replaceAll('_', ' ') })[0])

    expect((technical() as HTMLDetailsElement).open).toBe(true)
    expect(document.getElementById(`note-${code}`)).not.toBeNull()
    expect(technical().contains(document.getElementById(`note-${code}`))).toBe(true)
  })
})

// --- step 5's review: its findings, each failing before the fix --------------------------------------------------

describe('the review of step 5', () => {
  it('sees a banned word at the end of an element (the footer said "share")', () => {
    show('kaggle')

    expect(outsideTheToggle()).not.toMatch(/\bshare\b/i)
    expect(screen.getByText('The whole report in one file to download')).toBeDefined()
  })

  it("keeps stage 2's later-lines sentence inside the toggle, as report.html's appendix does", () => {
    const { report } = structuredClone(RUNS.kaggle_gbp)
    const reason = 'Your file has 3 lines dated after the upload; their revenue (1,234.00) stays in its own month.'
    report.layer_1_numbers.future_lines_reason = reason
    render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)

    expect(technical().contains(screen.getByText(reason))).toBe(true)
    expect(bannedIn(outsideTheToggle())).toEqual([])
  })

  it('points "see below" at the technical details', () => {
    const { report } = structuredClone(RUNS.kaggle)
    report.layer_1_numbers.kpis = report.layer_1_numbers.kpis.map((kpi) => ({ ...kpi, current: null, current_reason: 'Withheld.' }))
    render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)

    expect(screen.getByText(/the current month's figures are withheld \(see Technical details\)/)).toBeDefined()
    expect(document.body.textContent).not.toContain('(see below)')
  })

  it('puts the code on a moved-against label, as report.html does (kaggle confirmed as GBP)', () => {
    show('kaggle_gbp')

    expect(within(technical()).getByText('moved against the change in gross sales (GBP -1,479.65)')).toBeDefined()
  })

  it("keeps the label as stage 5 wrote it when no currency is stated", () => {
    show('kaggle')

    expect(within(technical()).getByText('moved against the change in gross sales (-1,479.65)')).toBeDefined()
  })

  it("lists the change's split, exact, in the toggle - the withheld split as numbers, never drawn (design 1.7)", () => {
    const report = show('demo_classed')
    const table = within(technical()).getByRole('table', { name: 'The split of the change, exact' })
    const levels = given(report.layer_2_causes.lever_levels)

    expect(within(table).getAllByRole('row').slice(1)).toHaveLength(levels.reduce((n, level) => n + level.factors.length, 0))
    expect(within(table).getAllByText('level2').length).toBeGreaterThan(0)
  })

  it("shows revenue's exact change beside its percentage (Q22)", () => {
    show('kaggle_gbp')
    const revenue = within(technical()).getByText('Revenue', { selector: '[data-testid="kpi-label"]' }).closest('.kpi-card') as HTMLElement

    expect(within(revenue).getByText('GBP +4,925.00')).toBeDefined()
  })
})
