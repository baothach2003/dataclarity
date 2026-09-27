import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  DateOrderMeasure,
  ExecuteResponse,
  Params,
  PreviewResponse,
  ProfileContract,
  TransformAction,
} from '../types/contracts.ts'

// Session 2E-j (Thach): Review asks how the dates are written when the file
// cannot say ("05/01/2026" is 5 January or 1 May), and Confirm waits for the
// answer - stage 1 refuses to run without one, since either default
// fabricates dates. A proven order is shown with its proof. Written before
// the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
}))

const MAPPED: [string, CanonicalField][] = [
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Item', 'product_name'],
]
const AMBIGUOUS: DateOrderMeasure = {
  shaped: 90,
  day_first: 0,
  month_first: 0,
  ambiguous: 90,
  day_first_example: null,
  month_first_example: null,
  decision: 'ask',
  hint: null,
}

function action(name: string, field: CanonicalField, act: TransformAction, params: Params): ColumnAction {
  return { source_name: name, semantic_type: 'text', canonical_field: field, action: act, params, rationale: '', alternatives: [], edited_by_user: false }
}

function makePlan(dayAction: TransformAction = 'flag_only', dayParams: Params = {}): CleaningPlan {
  return {
    schema_version: '3.1',
    generated_at: '2026-09-27T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: MAPPED.map(([name, field]) =>
      name === 'Day' ? action(name, field, dayAction, dayParams) : action(name, field, 'flag_only', {}),
    ),
  }
}

function makeProfile(measure: DateOrderMeasure | null): ProfileContract {
  return {
    schema_version: '1.1',
    generated_at: '2026-09-27T00:00:00Z',
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
      date_order: name === 'Day' ? measure : null,
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
    schema_version: '3.1',
    generated_at: '2026-09-27T00:00:00Z',
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

function renderReview(measure: DateOrderMeasure | null, plan: CleaningPlan = makePlan()) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
  render(
    <ReviewPage
      baseUrl="http://localhost:8000"
      runId="run-1"
      filename="sales.csv"
      profile={makeProfile(measure)}
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

describe('ReviewPage: how the dates are written', () => {
  it('asks, and Confirm waits for the answer', () => {
    renderReview(AMBIGUOUS)

    expect(screen.getByText('How are the dates in "Day" written?')).toBeDefined()
    expect(screen.getByText(/can be read two ways/)).toBeDefined()
    expect(confirmButton().disabled).toBe(true)
    expect(screen.getByText('Answer how the dates are written first')).toBeDefined()
  })

  it('counts the dates that read two ways, not every date of that shape (mutation check)', () => {
    renderReview({ ...AMBIGUOUS, shaped: 100, ambiguous: 90 })

    expect(screen.getByText(/^90 dates such as 05\/01\/2026 can be read two ways/)).toBeDefined()
  })

  it('sends the answer with the plan', async () => {
    const { executePlan } = renderReview(AMBIGUOUS)

    fireEvent.click(screen.getByRole('button', { name: 'Day first (31/12/2026)' }))

    expect(screen.getByText('Dates in "Day" are read day first')).toBeDefined()
    expect(confirmButton().disabled).toBe(false)
    fireEvent.click(confirmButton())
    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    expect(executePlan.mock.calls[0][2].confirmations?.dates_day_first).toBe(true)
  })

  it('can change the answer', () => {
    renderReview(AMBIGUOUS)
    fireEvent.click(screen.getByRole('button', { name: 'Month first (12/31/2026)' }))

    fireEvent.click(screen.getByRole('button', { name: 'Change' }))

    expect(screen.getByText('How are the dates in "Day" written?')).toBeDefined()
    expect(confirmButton().disabled).toBe(true)
  })

  it('names both proofs when the file holds both', () => {
    renderReview({ ...AMBIGUOUS, day_first: 2, month_first: 1, day_first_example: '13/01/2026', month_first_example: '01/13/2026' })

    expect(screen.getByText(/"13\/01\/2026" can only be day first and "01\/13\/2026" only month first/)).toBeDefined()
  })

  it('states both readings of the first of each month, choosing neither (review cycle 2 #3)', () => {
    renderReview({ ...AMBIGUOUS, hint: 'day_first' })

    expect(screen.getByText(/Read day first, every date is the 1st of a month.*read month first, they are the first days of one month/)).toBeDefined()
    expect(confirmButton().disabled).toBe(true)
  })

  it('shows a proven order with its proof, and asks nothing', () => {
    renderReview({ ...AMBIGUOUS, day_first: 12, day_first_example: '13/01/2026', decision: 'day_first' })

    expect(screen.getByText('Dates in "Day" are read day first')).toBeDefined()
    expect(screen.getByText(/12 dates, such as "13\/01\/2026", can only be read that way/)).toBeDefined()
    expect(confirmButton().disabled).toBe(false)
  })

  it('asks nothing for a file with no such dates', () => {
    renderReview(null)

    expect(screen.queryByText(/How are the dates/)).toBeNull()
    expect(confirmButton().disabled).toBe(false)
  })

  it('warns when the parse step reads the dates the other way, and fixes it', async () => {
    const { executePlan } = renderReview(AMBIGUOUS, makePlan('parse_datetime', {}))
    fireEvent.click(screen.getByRole('button', { name: 'Day first (31/12/2026)' }))

    expect(screen.getByText('The parse step on "Day" reads these dates month first')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Read them day first' }))

    expect(screen.queryByText(/The parse step on "Day"/)).toBeNull()
    fireEvent.click(confirmButton())
    await vi.waitFor(() => {
      expect(executePlan).toHaveBeenCalledTimes(1)
    })
    expect(executePlan.mock.calls[0][2].column_actions[0].params).toEqual({ dayfirst: true })
  })
})
