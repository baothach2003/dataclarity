import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  ExecuteResponse,
  NumberFormatMeasure,
  PreviewResponse,
  ProfileContract,
} from '../types/contracts.ts'

// Session 2E-u1 (Thach, 2026-10-02; 2E-u F1): Review asks how the numbers in
// the quantity or price column are written when the file cannot say ("1,000"
// is one thousand or one), and Confirm waits for the answer - stage 1 refuses
// to run without one: never a default either way. Written before the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
  lineSummary: vi.fn(() => new Promise(() => undefined)),
}))

const MAPPED: [string, CanonicalField][] = [
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Item', 'product_name'],
]
const AMBIGUOUS: NumberFormatMeasure = {
  readable: 90,
  point: 0,
  comma: 0,
  ambiguous: 40,
  currency: 0,
  unreadable: 0,
  point_example: null,
  comma_example: null,
  ambiguous_example: '1,000',
  decision: 'ask',
}
const PROVEN: NumberFormatMeasure = { ...AMBIGUOUS, point: 50, point_example: '1,000.00', decision: 'decimal_point' }

function action(name: string, field: CanonicalField, act: ColumnAction['action'] = 'flag_only'): ColumnAction {
  return { source_name: name, semantic_type: 'text', canonical_field: field, action: act, params: {}, rationale: '', alternatives: [], edited_by_user: false }
}

function makePlan(priceAction: ColumnAction['action'] = 'flag_only'): CleaningPlan {
  return {
    schema_version: '4.1',
    generated_at: '2026-10-02T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: MAPPED.map(([name, field]) => action(name, field, name === 'Price' ? priceAction : 'flag_only')),
  }
}

function makeProfile(price: NumberFormatMeasure | null, item: NumberFormatMeasure | null = null): ProfileContract {
  return {
    schema_version: '1.2',
    generated_at: '2026-10-02T00:00:00Z',
    dataset: { rows: 100, columns: MAPPED.length, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
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
      number_format: name === 'Price' ? price : name === 'Item' ? item : null,
    })),
  }
}

const PREVIEW: PreviewResponse = {
  run_id: 'run-1',
  preview: { rows_in_file: 100, sample_rows: 100, sampled: false, rows_after: 100, columns_after: [], rows: [], deltas: [] },
}

const EXECUTED: ExecuteResponse = {
  run_id: 'run-1',
  status: 'cleaned',
  report: {
    schema_version: '4.1',
    generated_at: '2026-10-02T00:00:00Z',
    rows_in: 100,
    rows_out: 100,
    columns_in: 4,
    columns_out: 4,
    changes: [],
    warnings: [],
    column_mapping: {},
  },
  notices: [],
}

function renderReview(profile: ProfileContract, plan: CleaningPlan = makePlan()) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
  render(
    <ReviewPage
      baseUrl="http://localhost:8000"
      runId="run-1"
      filename="sales.csv"
      profile={profile}
      schema={null}
      initialPlan={plan}
      notices={[]}
      onCancel={vi.fn()}
      onCleaned={vi.fn()}
    />,
  )
  return { executePlan }
}

function confirmButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Confirm & Clean' })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ReviewPage: how the numbers are written', () => {
  it('asks, and Confirm waits for the answer', () => {
    renderReview(makeProfile(AMBIGUOUS))

    expect(screen.getByText('How are the numbers in "Price" written?')).toBeDefined()
    expect(screen.getByText(/^40 numbers such as "1,000" can be read two ways/)).toBeDefined()
    expect(confirmButton().disabled).toBe(true)
    expect(screen.getByText('Answer how the numbers are written first')).toBeDefined()
  })

  it('sends the answer for that column with the plan', async () => {
    const { executePlan } = renderReview(makeProfile(AMBIGUOUS))

    fireEvent.click(screen.getByRole('button', { name: 'With a decimal comma (1.000,50)' }))

    expect(screen.getByText('Numbers in "Price" are read with a decimal comma')).toBeDefined()
    expect(confirmButton().disabled).toBe(false)
    fireEvent.click(confirmButton())
    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    expect(executePlan.mock.calls[0][2].confirmations?.number_formats).toEqual({ Price: 'decimal_comma' })
  })

  it('previews with the answer, as execution will read the column (review 2, N2)', async () => {
    renderReview(makeProfile(AMBIGUOUS))
    await vi.waitFor(() => {
      expect(runsApi.previewPlan).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'With a decimal comma (1.000,50)' }))

    await vi.waitFor(() => {
      const calls = vi.mocked(runsApi.previewPlan).mock.calls
      expect(calls[calls.length - 1][2].confirmations?.number_formats).toEqual({ Price: 'decimal_comma' })
    })
  })

  it('can change the answer', () => {
    renderReview(makeProfile(AMBIGUOUS))
    fireEvent.click(screen.getByRole('button', { name: 'With a decimal point (1,000.50)' }))

    fireEvent.click(screen.getByRole('button', { name: 'Change' }))

    expect(screen.getByText('How are the numbers in "Price" written?')).toBeDefined()
    expect(confirmButton().disabled).toBe(true)
  })

  it('asks nothing for a proven column, and says how it is read', () => {
    const { executePlan } = renderReview(makeProfile(PROVEN))

    expect(screen.queryByText(/How are the numbers/)).toBeNull()
    expect(screen.getByText('Numbers in "Price" are read with a decimal point')).toBeDefined()
    expect(screen.getByText(/50 numbers, such as "1,000.00", can only be read that way/)).toBeDefined()
    expect(confirmButton().disabled).toBe(false)
    expect(executePlan).not.toHaveBeenCalled()
  })

  it('says when the column proves both marks rather than neither (review 1, F8)', () => {
    renderReview(makeProfile({ ...AMBIGUOUS, point: 3, comma: 2, point_example: '10.5', comma_example: '10,5' }))

    expect(screen.getByText(/the column's other numbers prove both marks \("10\.5" and "10,5"\)/)).toBeDefined()
  })

  it('when the column proves both marks, the answer reads only the two-way numbers (review 2, N7)', () => {
    renderReview(makeProfile({ ...AMBIGUOUS, point: 3, comma: 2, point_example: '10.5', comma_example: '10,5' }))

    fireEvent.click(screen.getByRole('button', { name: 'With a decimal comma (1.000,50)' }))

    expect(screen.getByText('Numbers such as "1,000" in "Price" are read with a decimal comma')).toBeDefined()
    expect(screen.getByText(/As you answered; a number that proves its own mark \("10\.5", "10,5"\) is read by it\./)).toBeDefined()
  })

  it('asks only about the quantity and price columns', () => {
    renderReview(makeProfile(null, AMBIGUOUS))

    expect(screen.queryByText(/How are the numbers/)).toBeNull()
    expect(confirmButton().disabled).toBe(false)
  })

  it('does not ask about a dropped column', () => {
    renderReview(makeProfile(AMBIGUOUS), makePlan('drop_column'))

    expect(screen.queryByText(/How are the numbers/)).toBeNull()
  })

  it('sends no number answers when none was asked', async () => {
    const { executePlan } = renderReview(makeProfile(null))

    fireEvent.click(confirmButton())
    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    expect(executePlan.mock.calls[0][2].confirmations?.number_formats).toBeUndefined()
  })
})
