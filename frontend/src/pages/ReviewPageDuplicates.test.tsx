import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type { CanonicalField, CleaningPlan, ExecuteResponse, PreviewResponse, ProfileContract } from '../types/contracts.ts'
import type { LineSummaryResponse } from '../types/lineSummary.ts'

// Session 2E-u4 (Thach, 2026-10-02; before deploy): the AI never proposes
// removing exact duplicates - a copy cannot be told from a genuine repeat
// sale. Review offers it when the file has copies; added by the user, it says
// what it takes: the lines and their revenue, from stage 1's whole-file
// summary. Written before the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
  lineSummary: vi.fn(),
  // Review's currency question (step 5): pending, so the page reads as before.
  currencyQuestion: vi.fn(() => new Promise(() => undefined)),
}))

const MAPPED: [string, CanonicalField][] = [
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Item', 'product_name'],
]

function makePlan(removes = false): CleaningPlan {
  return {
    schema_version: '4.2',
    generated_at: '2026-10-02T00:00:00Z',
    source: 'ai',
    dataset_actions: removes
      ? [{ action: 'remove_exact_duplicates', params: {}, rationale: 'added by the user in Review', alternatives: [], edited_by_user: true }]
      : [],
    column_actions: MAPPED.map(([source_name, canonical_field]) => ({
      source_name,
      semantic_type: 'text',
      canonical_field,
      action: 'flag_only',
      params: {},
      rationale: '',
      alternatives: [],
      edited_by_user: false,
    })),
  }
}

function makeProfile(duplicates: number): ProfileContract {
  return {
    schema_version: '1.2',
    generated_at: '2026-10-02T00:00:00Z',
    dataset: { rows: 100, columns: 4, duplicate_rows: duplicates, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
    columns: MAPPED.map(([name]) => ({
      name,
      dtype: 'str',
      null_count: 0,
      null_pct: 0,
      unique_count: 10,
      min: null,
      max: null,
      mean: null,
      median: null,
      q1: null,
      q3: null,
      top_values: [],
      sample_values: [],
    })),
  }
}

function summary(removed: { lines: number; revenue: number } | null): LineSummaryResponse {
  return {
    run_id: 'run-1',
    reserved_renames: [],
    summary: {
      lines: 95,
      undated_lines: 0,
      identity: {
        gross_sales: 100,
        returns: 0,
        discounts: 0,
        other_deductions: 0,
        other_revenue: 0,
        net_revenue: 100,
        returns_on_suggested_keys: 0,
        money_moved: 100,
      },
      outside_revenue: [],
      unclassified: { lines: 0, amount: 0, share_of_money_moved: 0 },
      unmeasurable: [],
      notes: [],
      duplicates_removed: removed,
    },
    summary_unavailable_reason: null,
  }
}

const PREVIEW: PreviewResponse = {
  run_id: 'run-1',
  preview: { rows_in_file: 100, sample_rows: 100, sampled: false, rows_after: 100, columns_after: [], rows: [], deltas: [] },
}

const EXECUTED: ExecuteResponse = {
  run_id: 'run-1',
  status: 'cleaned',
  report: { schema_version: '4.2', generated_at: '2026-10-02T00:00:00Z', rows_in: 100, rows_out: 100, columns_in: 4, columns_out: 4, changes: [], warnings: [], column_mapping: {} },
  notices: [],
}

function renderReview(duplicates: number, plan: CleaningPlan, answer: LineSummaryResponse) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  vi.mocked(runsApi.lineSummary).mockResolvedValue(answer)
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
  render(
    <ReviewPage
      baseUrl="http://localhost:8000"
      runId="run-1"
      filename="sales.csv"
      profile={makeProfile(duplicates)}
      schema={null}
      initialPlan={plan}
      notices={[]}
      onCancel={vi.fn()}
      onCleaned={vi.fn()}
    />,
  )
  return { executePlan }
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ReviewPage: exact copies (2E-u4)', () => {
  it('says the copies are kept and offers to remove them', () => {
    renderReview(5, makePlan(), summary(null))

    expect(screen.getByText('5 rows are exact copies of another row')).toBeDefined()
    expect(screen.getByText(/They are kept: a copy cannot be told from a genuine repeat sale/)).toBeDefined()
    expect(screen.getByRole('button', { name: 'Remove the copies' })).toBeDefined()
  })

  it('adds the step the user chose to the plan sent', async () => {
    const { executePlan } = renderReview(5, makePlan(), summary(null))

    fireEvent.click(screen.getByRole('button', { name: 'Remove the copies' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Clean' }))

    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    const sent = executePlan.mock.calls[0][2]
    expect(sent.dataset_actions.map((a) => [a.action, a.edited_by_user])).toEqual([['remove_exact_duplicates', true]])
  })

  it('once added, shows the lines and revenue the whole-file summary counts', async () => {
    renderReview(5, makePlan(true), summary({ lines: 5, revenue: 1234.5 }))

    expect(await screen.findByText('The plan removes 5 lines that are exact copies, holding 1,234.50 of revenue')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Keep them' })).toBeDefined()
  })

  it('keeps them again', async () => {
    const { executePlan } = renderReview(5, makePlan(true), summary({ lines: 5, revenue: 1234.5 }))

    fireEvent.click(await screen.findByRole('button', { name: 'Keep them' }))
    expect(screen.getByText('5 rows are exact copies of another row')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Clean' }))
    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    expect(executePlan.mock.calls[0][2].dataset_actions).toEqual([])
  })

  it('before the summary counts the step, says where the revenue will be', () => {
    renderReview(5, makePlan(), summary(null))

    fireEvent.click(screen.getByRole('button', { name: 'Remove the copies' }))

    // Not the profile's raw count: the step runs after the plan drops columns
    // and reads the numbers, so it can take more (2E-u4 review 1, #7).
    expect(screen.getByText('The plan removes the exact copies')).toBeDefined()
    expect(screen.getByText(/Add up the whole file again to see how many lines and how much revenue they hold/)).toBeDefined()
  })

  it('says nothing when the file has no copies', () => {
    renderReview(0, makePlan(), summary(null))

    expect(screen.queryByText(/exact copies/)).toBeNull()
  })
})
