import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import { ApiError } from '../api/errors.ts'
import * as runsApi from '../api/runs.ts'
import type {
  CanonicalField,
  CleaningPlan,
  PreviewResponse,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'
import type { LineSummaryResponse } from '../types/lineSummary.ts'

// Session 2E-t3 (Thach): Review shows the whole file for the answers as they
// stand - asked of stage 1, which computes every figure: once when Review
// opens, then when the user asks again (review 1 #1). Written before the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
  lineSummary: vi.fn(),
}))

const MAPPED: [string, CanonicalField][] = [
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Code', 'sku'],
  ['Item', 'product_name'],
]

const PLAN: CleaningPlan = {
  schema_version: '4.0',
  generated_at: '2026-09-26T00:00:00Z',
  source: 'ai',
  dataset_actions: [],
  column_actions: MAPPED.map(([source_name, canonical_field]) => ({
    source_name,
    semantic_type: 'text',
    canonical_field,
    action: 'flag_only',
    params: { note: '' },
    rationale: '',
    alternatives: [],
    edited_by_user: false,
  })),
}

const PROFILE: ProfileContract = {
  schema_version: '1.0',
  generated_at: '2026-09-26T00:00:00Z',
  dataset: { rows: 100, columns: 5, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
  columns: MAPPED.map(([name]) => ({
    name,
    dtype: 'object',
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

const SCHEMA: SchemaInferenceContract = {
  schema_version: '4.0',
  generated_at: '2026-09-26T00:00:00Z',
  model_used: 'claude-sonnet-5',
  domain_confidence: 0.9,
  domain_reasoning: 'sales lines',
  dataset_issues: [],
  columns: MAPPED.map(([source_name, canonical_field]) => ({
    source_name,
    semantic_type: 'text',
    canonical_field,
    confidence: 0.9,
    issues: [],
  })),
  non_product_candidates: [
    { value: 'POST', field: 'sku', name: 'POSTAGE', lines: 3, positive: 12, negative: 0, suggested: 'charge', word: 'postage' },
  ],
}

const PREVIEW: PreviewResponse = {
  run_id: 'run-1',
  preview: { rows_in_file: 100, sample_rows: 100, sampled: false, rows_after: 100, columns_after: [], rows: [], deltas: [] },
}

const SUMMARY: LineSummaryResponse = {
  run_id: 'run-1',
  reserved_renames: [{ source: 'line_class', written_as: 'line_class_source', holds: "each line's class" }],
  summary: {
    lines: 17,
    undated_lines: 0,
    identity: {
      gross_sales: 65,
      returns: 13,
      discounts: 5,
      other_deductions: 2,
      other_revenue: 4,
      net_revenue: 49,
      returns_on_suggested_keys: 0,
      money_moved: 89,
    },
    outside_revenue: [{ line_class: 'cost', scope: 'file', sign: null, lines: 1, amount: -7, lines_without_amount: 0 }],
    unclassified: { lines: 0, amount: 0, share_of_money_moved: 0 },
    unmeasurable: [],
    notes: [
      {
        code: 'discounts_in_prices',
        figures: ['gross_sales', 'discounts'],
        text: "Discounts count only lines classed as discounts; a discount already taken off a line's price is not visible, and that line's gross sales are at the reduced price.",
        measures: [],
      },
    ],
  },
  summary_unavailable_reason: null,
}

function renderReview(notices: { code: 'NOT_INVENTORY'; message: string }[] = []) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const lineSummary = vi.mocked(runsApi.lineSummary).mockResolvedValue(SUMMARY)
  render(
    <ReviewPage
      baseUrl="http://localhost:8000"
      runId="run-1"
      filename="sales.csv"
      profile={PROFILE}
      schema={SCHEMA}
      initialPlan={PLAN}
      notices={notices}
      onCancel={vi.fn()}
      onCleaned={vi.fn()}
    />,
  )
  return lineSummary
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const WAIT = { timeout: 3000 }

describe('ReviewPage: the whole file as the answers stand (2E-t3)', () => {
  it('says it is adding up, then shows the identity, what is outside revenue, the notes and the renamed column', async () => {
    renderReview()

    expect(screen.getByText('Adding up the whole file…')).toBeDefined()
    expect(await screen.findByText(/= net revenue 49\.00 - the plan keeps 17 lines\./, {}, WAIT)).toBeDefined()
    expect(screen.getByText(/Outside revenue, reported apart: Fees and costs: 1 line \(-7\.00\)\./)).toBeDefined()
    expect(screen.getByText(/Discounts count only lines classed as discounts/)).toBeDefined()
    expect(screen.getByText(/"line_class" will be written as "line_class_source": .* holds each line's class\./)).toBeDefined()
  })

  it('does not ask again on an edit: it marks the figures as before the change, and asks when told to', async () => {
    const lineSummary = renderReview()
    await screen.findByText(/= net revenue 49\.00/, {}, WAIT)
    expect(lineSummary).toHaveBeenCalledTimes(1)
    expect(lineSummary.mock.calls[0][2].confirmations?.line_classes).toBeUndefined()

    fireEvent.change(screen.getByRole('combobox', { name: 'What is "POST"?' }), { target: { value: 'charge' } })

    expect(screen.getByText('The whole file, as your answers stand (before your latest changes)')).toBeDefined()
    expect(lineSummary).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Add up again' }))
    expect(screen.getByText('The whole file, as your answers stand (updating…)')).toBeDefined()
    await vi.waitFor(() => {
      expect(lineSummary).toHaveBeenCalledTimes(2)
    }, WAIT)
    expect(lineSummary.mock.calls[1][2].confirmations?.line_classes).toEqual([
      { value: 'POST', field: 'sku', line_class: 'charge' },
    ])
    expect(await screen.findByText('The whole file, as your answers stand', {}, WAIT)).toBeDefined()
  })

  it('says why there is no summary yet', async () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
    const lineSummary = renderReview()
    lineSummary.mockResolvedValue({
      ...SUMMARY,
      reserved_renames: [],
      summary: null,
      summary_unavailable_reason: 'Answer how the dates are written to see the whole file.',
    })
    await screen.findByText(/= net revenue 49\.00/, {}, WAIT)
    fireEvent.change(screen.getByRole('combobox', { name: 'What is "POST"?' }), { target: { value: 'cost' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add up again' }))

    expect(await screen.findByText('Answer how the dates are written to see the whole file.', {}, WAIT)).toBeDefined()
  })

  it('says it could not add up, and offers to try again', async () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
    vi.mocked(runsApi.lineSummary).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(SUMMARY)
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={PROFILE}
        schema={SCHEMA}
        initialPlan={PLAN}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    expect(await screen.findByText('The whole file, as your answers stand: not added up', {}, WAIT)).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/= net revenue 49\.00/, {}, WAIT)).toBeDefined()
  })

  it('keeps the earlier answer after a failed ask, marked, and says why (review 2 #5, #6)', async () => {
    const lineSummary = renderReview()
    await screen.findByText(/= net revenue 49\.00/, {}, WAIT)
    lineSummary.mockRejectedValueOnce(
      new ApiError('INVALID_STATE', 'busy', { reason: 'summary_in_progress' }),
    )
    fireEvent.change(screen.getByRole('combobox', { name: 'What is "POST"?' }), { target: { value: 'cost' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add up again' }))

    expect(await screen.findByText(/still being added up from an earlier request/, {}, WAIT)).toBeDefined()
    expect(screen.getByText('Columns the cleaned file writes under another name (as last checked)')).toBeDefined()
    expect(screen.getByText('The whole file, as your answers stand (before your latest changes)')).toBeDefined()
    expect(screen.getByText(/= net revenue 49\.00/)).toBeDefined()
  })

  it('does not ask for a file that is not inventory data', async () => {
    const lineSummary = renderReview([{ code: 'NOT_INVENTORY', message: 'Not sales data' }])
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(lineSummary).not.toHaveBeenCalled()
  })
})
