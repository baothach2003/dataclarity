import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import { ApiError } from '../api/errors.ts'
import type {
  CleaningPlan,
  ColumnAction,
  PreviewResponse,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
}))

function column(overrides: Partial<ColumnAction> & { source_name: string }): ColumnAction {
  return {
    semantic_type: 'text',
    canonical_field: 'ignore',
    action: 'flag_only',
    params: {},
    rationale: 'This column looks fine as is.',
    alternatives: [],
    edited_by_user: false,
    ...overrides,
  }
}

function makeProfile(): ProfileContract {
  const names = ['sku', 'name', 'qty', 'day']
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    dataset: { rows: 100, columns: 4, duplicate_rows: 2, missing_cells_pct: 3.5, encoding_used: 'utf-8', delimiter: ',' },
    columns: names.map((name) => ({
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
}

function makeSchema(overrides: Partial<SchemaInferenceContract> = {}): SchemaInferenceContract {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    model_used: 'claude-sonnet-5',
    domain_confidence: 0.9,
    domain_reasoning: 'looks like sales data',
    dataset_issues: [],
    columns: [
      { source_name: 'sku', semantic_type: 'identifier', canonical_field: 'sku', confidence: 0.95, issues: [] },
      { source_name: 'name', semantic_type: 'text', canonical_field: 'product_name', confidence: 0.9, issues: [] },
      {
        source_name: 'qty',
        semantic_type: 'numeric_discrete',
        canonical_field: 'quantity',
        confidence: 0.55,
        issues: [{ code: 'missing_values', count: 4, pct: 4, examples: ['row 2'] }],
      },
      { source_name: 'day', semantic_type: 'datetime', canonical_field: 'transaction_date', confidence: 0.92, issues: [] },
    ],
    ...overrides,
  }
}

function makeMappedPlan(): CleaningPlan {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: [
      column({ source_name: 'sku', semantic_type: 'identifier', canonical_field: 'sku', action: 'trim_whitespace' }),
      column({ source_name: 'name', semantic_type: 'text', canonical_field: 'product_name', action: 'trim_whitespace' }),
      column({
        source_name: 'qty',
        semantic_type: 'numeric_discrete',
        canonical_field: 'quantity',
        action: 'drop_rows_missing',
      }),
      column({
        source_name: 'day',
        semantic_type: 'datetime',
        canonical_field: 'transaction_date',
        action: 'parse_datetime',
      }),
    ],
  }
}

function makePreviewResponse(): PreviewResponse {
  return {
    run_id: 'run-1',
    preview: {
      rows_in_file: 100,
      sample_rows: 100,
      sampled: false,
      rows_after: 96,
      columns_after: ['sku', 'name', 'qty', 'day'],
      rows: [],
      deltas: [],
    },
  }
}

function isDisabled(element: HTMLElement): boolean {
  return element.hasAttribute('disabled')
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('ReviewPage: plan edits debounce into a preview call', () => {
  it('requests a preview 400ms after mount with the initial plan', async () => {
    vi.useFakeTimers()
    const previewPlan = vi.mocked(runsApi.previewPlan).mockResolvedValue(makePreviewResponse())
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile()}
        schema={makeSchema()}
        initialPlan={makeMappedPlan()}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    expect(previewPlan).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(400)

    expect(previewPlan).toHaveBeenCalledTimes(1)
    expect(previewPlan.mock.calls[0]?.[1]).toBe('run-1')
  })

  it('coalesces several edits within the debounce window into one call', async () => {
    vi.useFakeTimers()
    const previewPlan = vi.mocked(runsApi.previewPlan).mockResolvedValue(makePreviewResponse())
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile()}
        schema={makeSchema()}
        initialPlan={makeMappedPlan()}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )
    await vi.advanceTimersByTimeAsync(400)
    expect(previewPlan).toHaveBeenCalledTimes(1)

    const nameSelect = screen.getAllByDisplayValue('Trim whitespace')[1]
    fireEvent.change(nameSelect, { target: { value: 'drop_column' } })
    await vi.advanceTimersByTimeAsync(200)
    fireEvent.change(nameSelect, { target: { value: 'flag_only' } })
    await vi.advanceTimersByTimeAsync(400)

    expect(previewPlan).toHaveBeenCalledTimes(2)
    const lastPlan = previewPlan.mock.calls[1][2]
    const nameAction = lastPlan.column_actions.find((c) => c.source_name === 'name')
    expect(nameAction?.action).toBe('flag_only')
    expect(nameAction?.edited_by_user).toBe(true)
  })
})

describe('ReviewPage: required-field gate', () => {
  it('disables Confirm and lists unmapped required fields', () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(makePreviewResponse())
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile()}
        schema={null}
        initialPlan={null}
        notices={[{ code: 'AI_UNAVAILABLE', message: 'The AI could not propose a plan.' }]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    const confirmButton = screen.getByRole('button', { name: 'Confirm & Clean' })
    expect(isDisabled(confirmButton)).toBe(true)
    expect(
      screen.getByText('Required fields not mapped: product name, transaction date and quantity'),
    ).toBeDefined()
  })

  it('enables Confirm once every required field is mapped, and executes that plan', async () => {
    const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue({
      run_id: 'run-1',
      status: 'cleaned',
      report: {
        schema_version: '1.0',
        generated_at: '2026-09-22T00:00:00Z',
        rows_in: 100,
        rows_out: 96,
        columns_in: 4,
        columns_out: 4,
        changes: [],
        warnings: [],
        column_mapping: {},
      },
      notices: [],
    })
    vi.mocked(runsApi.previewPlan).mockResolvedValue(makePreviewResponse())
    const onCleaned = vi.fn()
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile()}
        schema={makeSchema()}
        initialPlan={makeMappedPlan()}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={onCleaned}
      />,
    )

    const confirmButton = screen.getByRole('button', { name: 'Confirm & Clean' })
    expect(isDisabled(confirmButton)).toBe(false)
    fireEvent.click(confirmButton)

    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    expect(onCleaned).toHaveBeenCalledWith({
      report: expect.objectContaining({ rows_out: 96 }) as unknown,
      notices: [],
    })
  })
})

describe('ReviewPage: not-inventory files', () => {
  it('disables mapping and labels Confirm as generic cleaning', () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(makePreviewResponse())
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="roster.csv"
        profile={makeProfile()}
        schema={makeSchema({ domain_confidence: 0.31 })}
        initialPlan={makeMappedPlan()}
        notices={[{
          code: 'NOT_INVENTORY',
          message: 'This file does not look like inventory or sales data (confidence 0.31)',
          details: { domain_confidence: 0.31 },
        }]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    expect(
      screen.getByText('This file does not look like inventory or sales data (confidence 0.31)'),
    ).toBeDefined()
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0)
    expect(isDisabled(screen.getByRole('button', { name: 'Clean & download' }))).toBe(false)
  })
})

describe('ReviewPage: error-state rendering', () => {
  it('shows the fixed copy for a preview failure', async () => {
    vi.mocked(runsApi.previewPlan).mockRejectedValue(new ApiError('INVALID_PLAN', 'nope'))
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile()}
        schema={makeSchema()}
        initialPlan={makeMappedPlan()}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    expect(await screen.findByText("The cleaning plan couldn't be applied")).toBeDefined()
  })

  it('shows the fixed copy for an execute failure and lets the user go back to review', async () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(makePreviewResponse())
    vi.mocked(runsApi.executePlan).mockRejectedValue(
      new ApiError('CLEANING_FAILED', 'drop_rows_missing on qty left no rows'),
    )
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile()}
        schema={makeSchema()}
        initialPlan={makeMappedPlan()}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Confirm & Clean' }))

    expect(await screen.findByText("The cleaning plan couldn't be applied to this data")).toBeDefined()
    expect(screen.getByText('drop_rows_missing on qty left no rows')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Back to review' }))
    expect(screen.queryByText('drop_rows_missing on qty left no rows')).toBeNull()
  })
})
