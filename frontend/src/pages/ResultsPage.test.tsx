import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ResultsPage } from './ResultsPage.tsx'
import * as runsApi from '../api/runs.ts'
import { ApiError } from '../api/errors.ts'
import type { CleaningReport } from '../types/contracts.ts'

vi.mock('../api/runs.ts', () => ({ downloadCleanedCsv: vi.fn() }))

function makeReport(overrides: Partial<CleaningReport> = {}): CleaningReport {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    rows_in: 12480,
    rows_out: 12301,
    columns_in: 14,
    columns_out: 14,
    changes: [
      {
        action: 'remove_exact_duplicates',
        column: null,
        cells_affected: 0,
        rows_affected: 37,
        params: {},
        detail: 'removed 37 exact-duplicate rows',
      },
      {
        action: 'drop_rows_missing',
        column: 'qty_sold',
        cells_affected: 0,
        rows_affected: 142,
        params: {},
        detail: 'dropped 142 rows with no qty_sold',
      },
      {
        action: 'impute_constant',
        column: 'cust',
        cells_affected: 980,
        rows_affected: 0,
        params: { value: 'Unknown' },
        detail: "filled with 'Unknown'",
      },
      {
        action: 'flag_only',
        column: 'comments',
        cells_affected: 0,
        rows_affected: 0,
        params: {},
        detail: 'kept as is',
      },
    ],
    warnings: [],
    column_mapping: { qty_sold: 'quantity', cust: 'customer' },
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ResultsPage', () => {
  it('shows summary tiles and only the actions that changed something', () => {
    render(
      <ResultsPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        report={makeReport()}
        notices={[]}
      />,
    )

    expect(screen.getByText('12,301')).toBeDefined() // rows out tile
    expect(screen.getByText("Fill 'Unknown'")).toBeDefined() // dynamic impute_constant label
    expect(screen.queryByText('kept as is')).toBeNull() // flag_only, no effect: filtered out
  })

  it('labels Rows dropped with the canonical field name, not the raw column', () => {
    render(
      <ResultsPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        report={makeReport()}
        notices={[]}
      />,
    )

    expect(screen.getByText('missing quantity')).toBeDefined()
  })

  it('downloads the report client-side without calling the API', () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:fake'), revokeObjectURL: vi.fn() })

    render(
      <ResultsPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        report={makeReport()}
        notices={[]}
      />,
    )
    fireEvent.click(screen.getByText('Download cleaning_report.json'))

    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(runsApi.downloadCleanedCsv).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('fetches the cleaned CSV from the download endpoint and reports a failure', async () => {
    vi.mocked(runsApi.downloadCleanedCsv).mockRejectedValue(new ApiError('EXPIRED', 'gone'))
    render(
      <ResultsPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        report={makeReport()}
        notices={[]}
      />,
    )

    fireEvent.click(screen.getByText('Download cleaned_sales.csv'))

    expect(await screen.findByText('This run has expired')).toBeDefined()
    expect(runsApi.downloadCleanedCsv).toHaveBeenCalledWith('http://localhost:8000', 'run-1')
  })

  it('keeps Run full analysis and Import to dashboard disabled (Phases 2-5 and 7 are not built)', () => {
    render(
      <ResultsPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        report={makeReport()}
        notices={[]}
      />,
    )

    expect(screen.getByRole('button', { name: 'Run full analysis' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Import to dashboard' }).hasAttribute('disabled')).toBe(true)
  })

  it('shows a not-inventory notice when the execute response carried one', () => {
    render(
      <ResultsPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="roster.csv"
        report={makeReport()}
        notices={[{ code: 'NOT_INVENTORY', message: 'not inventory' }]}
      />,
    )

    expect(screen.getByText('Generic cleaning only')).toBeDefined()
  })
})
