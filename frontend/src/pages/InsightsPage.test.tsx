import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as analysisApi from '../api/analysis.ts'
import { ApiError } from '../api/errors.ts'
import * as browserDownload from '../domain/browserDownload.ts'
import type { ReportContract } from '../types/report.ts'
import { DISCOUNTS_TEXT, makeReport } from './insightsFixture.ts'
import { InsightsPage } from './InsightsPage.tsx'

vi.mock('../api/analysis.ts', () => ({ downloadReportHtml: vi.fn() }))
vi.mock('../domain/browserDownload.ts', () => ({ triggerBlobDownload: vi.fn() }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function show(report: ReportContract = makeReport()) {
  return render(<InsightsPage baseUrl="http://localhost:8000" runId="run-1" report={report} />)
}

// PROJECT_PLAN 6E, layer 1 (the numbers) with the design gap decisions; every
// figure as report.json has it - the page computes none (CLAUDE.md 3.2).
describe('InsightsPage: the numbers', () => {
  it('names the file, the months compared and the dates the file covers', () => {
    show()

    expect(screen.getByRole('heading', { level: 1, name: 'Insights' })).toBeDefined()
    expect(screen.getByText('store_sales_2026Q2.csv · June 2026 compared with May 2026 · the file covers 2026-04-01 to 2026-06-30')).toBeDefined()
  })

  it("shows the trust badge with every check's message and the limitations, toned by its verdict", () => {
    show()
    const badge = screen.getByText('Data trust: caution').closest('.notice')

    expect(badge?.className).toContain('notice--warning')
    expect(within(badge as HTMLElement).getByText('D1 (caution): About 5 days in the current month have no sales.')).toBeDefined()
    expect(within(badge as HTMLElement).getByText(/rows dropped in stage 1 cannot be assigned to a period/)).toBeDefined()
  })

  it("words a blocked badge as stage 5 does", () => {
    const report = makeReport()
    report.layer_1_numbers.trust.verdict = 'blocked'
    show(report)

    expect(screen.getByText('Data trust: blocked - the figures below are not a base for conclusions').closest('.notice')?.className).toContain('notice--error')
  })

  it('shows the five KPIs in order', () => {
    show()

    expect(screen.getAllByTestId('kpi-label').map((label) => label.textContent)).toEqual([
      'Revenue',
      'Orders',
      'Active customers',
      'Average order value',
      'Return rate',
    ])
  })

  it('says once why an incomplete previous month is not compared', () => {
    const report = makeReport()
    const reason = 'The file starts on 2026-05-12, after 2026-05 began.'
    report.layer_1_numbers.period = { ...report.layer_1_numbers.period, previous_complete: false, previous_incomplete_reason: reason }
    report.layer_1_numbers.kpis = report.layer_1_numbers.kpis.map((kpi) => ({
      ...kpi,
      previous: null,
      change_pct: null,
      previous_reason: reason,
      change_reason: kpi.id === 'revenue' ? reason : null,
    }))
    show(report)

    expect(screen.getByText(/June 2026; May 2026 is not compared/)).toBeDefined()
    expect(screen.getAllByText(reason)).toHaveLength(1)
    expect(screen.getAllByText('May 2026: not compared (see below)')).toHaveLength(5)
  })

  it("says the current month's figures are withheld when they are (CONTRACTS 9)", () => {
    const report = makeReport()
    report.layer_1_numbers.kpis = report.layer_1_numbers.kpis.map((kpi) => ({
      ...kpi,
      current: null,
      current_reason: 'No line counted in revenue is dated in 2026-06: a closed month or missing data, which the file cannot tell apart.',
      change_pct: null,
    }))
    show(report)

    expect(screen.getByText(/June 2026 against May 2026: the current month's figures are withheld \(see below\)/)).toBeDefined()
  })

  it('shows the notes about the figures under the KPIs: a month the file starts inside, unconfirmed walk-ins, later lines', () => {
    const report = makeReport()
    report.layer_1_numbers.current_note = 'The file starts on 2026-06-04: June 2026 may be a shop that opened then, or an export cut short.'
    report.layer_1_numbers.unconfirmed_placeholders_reason = '"Guest" may stand for walk-in customers; nobody confirmed it, so it is counted as a customer.'
    show(report)
    const about = screen.getByText('About these figures').closest('.notice') as HTMLElement

    expect(within(about).getByText(/The file starts on 2026-06-04/)).toBeDefined()
    expect(within(about).getByText(/"Guest" may stand for walk-in customers/)).toBeDefined()
    expect(screen.getByText('includes possible walk-ins not confirmed (see below)')).toBeDefined()
  })

  // The 6E1 review (#20): why the dates covered end before the file's last
  // line belongs beside those dates, as report.html puts it.
  it('says beside the dates covered why later lines are left out', () => {
    const report = makeReport()
    report.layer_1_numbers.future_lines_reason = '3 lines are dated after the upload, so no figure counts them.'
    show(report)

    const reason = screen.getByText('3 lines are dated after the upload, so no figure counts them.')
    expect(reason.closest('.notice')).toBeNull()
    expect(reason.previousElementSibling?.className).toBe('page__subtitle')
  })

  it('says both when the previous month is not compared and the current one is withheld', () => {
    const report = makeReport()
    const reason = 'The file starts on 2026-05-12, after 2026-05 began.'
    report.layer_1_numbers.period = { ...report.layer_1_numbers.period, previous_complete: false, previous_incomplete_reason: reason }
    report.layer_1_numbers.kpis = report.layer_1_numbers.kpis.map((kpi) => ({
      ...kpi,
      current: null,
      previous: null,
      change_pct: null,
      current_reason: 'No line counted in revenue is dated in 2026-06.',
      previous_reason: reason,
    }))
    show(report)

    expect(screen.getByText(/June 2026; May 2026 is not compared; the current month's figures are withheld/)).toBeDefined()
  })

  it('shows no such notice when there is nothing to say', () => {
    show()

    expect(screen.queryByText('About these figures')).toBeNull()
  })

  it('ends with "How to read these figures": the always-on notes, once, in the last card', () => {
    show()
    const cards = [...document.querySelectorAll('.page > section.card')]

    expect(screen.getAllByText(DISCOUNTS_TEXT)).toHaveLength(1)
    expect(cards.at(-1)?.querySelector('h2')?.textContent).toBe('How to read these figures')
  })

  it('marks every stage done, with nothing spinning (6E1 review #6)', () => {
    show()

    expect(document.querySelectorAll('.stepper__badge--done')).toHaveLength(5)
    expect(document.querySelector('.stepper [aria-current]')).toBeNull()
  })

  // The 6E1 review (#12): a KPI may name a note the report shows among the
  // causes' notes only (contracts/report.py allows it).
  it("finds a KPI's note among the causes' notes too", () => {
    const report = makeReport()
    report.layer_2_causes.notes = report.layer_1_numbers.notes
    report.layer_1_numbers.notes = []
    show(report)

    expect(screen.getByRole('button', { name: 'Notes on Orders' })).toBeDefined()
  })

  it('says what the file was and where the figures come from', () => {
    show()

    expect(screen.getByText('Rows in: 12,480. Rows out: 12,301. Changes that did something: 3. Warnings: 1.')).toBeDefined()
    // The 6E1 review (#9): an AI answer can be a column mapping or a cleaning
    // plan, not only words - but never a figure.
    expect(screen.getByText("Stages run: ingest, analyze, diagnose, predict. AI answers used: 1 (claude-sonnet-5). Every figure is computed by code from the earlier stages' files; the AI computes none.")).toBeDefined()
  })

  it('renders the file name as text, never as markup (SEC-3)', () => {
    const report = makeReport()
    report.source_file = '<img src=x onerror=alert(1)>.csv'
    show(report)

    expect(document.querySelector('img')).toBeNull()
    expect(screen.getByText(/<img src=x onerror=alert\(1\)>\.csv/)).toBeDefined()
  })
})

describe('InsightsPage: the report download', () => {
  it('downloads the HTML report under the file name', async () => {
    const blob = new Blob(['<!doctype html>'])
    vi.mocked(analysisApi.downloadReportHtml).mockResolvedValue(blob)
    show()

    fireEvent.click(screen.getByRole('button', { name: 'Download HTML report' }))

    await vi.waitFor(() => {
      expect(browserDownload.triggerBlobDownload).toHaveBeenCalledWith(blob, 'report_store_sales_2026Q2.html')
    })
    expect(analysisApi.downloadReportHtml).toHaveBeenCalledWith('http://localhost:8000', 'run-1')
  })

  it('says why a download failed', async () => {
    vi.mocked(analysisApi.downloadReportHtml).mockRejectedValue(new ApiError('EXPIRED', "The run's files are gone."))
    show()

    fireEvent.click(screen.getByRole('button', { name: 'Download HTML report' }))

    expect(await screen.findByText("This run's files are no longer available")).toBeDefined()
  })
})
