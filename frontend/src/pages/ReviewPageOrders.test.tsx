import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  ExecuteResponse,
  PreviewResponse,
  ProfileContract,
  SchemaInferenceContract,
  TransformAction,
} from '../types/contracts.ts'

// Session 2E-e2 (Thach): the order basis, visible and decided in Review.
// Written before the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
}))

const MAPPED: [string, CanonicalField][] = [
  ['Inv', 'order_id'],
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Cust', 'customer'],
  ['Item', 'product_name'],
]
const WITHOUT_CUSTOMER = MAPPED.filter(([, field]) => field !== 'customer')

function action(source_name: string, canonical_field: CanonicalField, act: TransformAction = 'flag_only'): ColumnAction {
  return {
    source_name,
    semantic_type: 'text',
    canonical_field,
    action: act,
    params: { note: '' },
    rationale: '',
    alternatives: [],
    edited_by_user: false,
  }
}

function makePlan(mapping: [string, CanonicalField][], actions: Record<string, TransformAction> = {}): CleaningPlan {
  return {
    schema_version: '2.1',
    generated_at: '2026-09-26T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: mapping.map(([name, field]) => action(name, field, actions[name])),
  }
}

function makeProfile(mapping: [string, CanonicalField][], blankIds = 0, blankCustomers = false): ProfileContract {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-26T00:00:00Z',
    dataset: { rows: 100, columns: mapping.length, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
    columns: mapping.map(([name]) => ({
      name,
      dtype: 'object',
      null_count: name === 'Inv' || name === 'Batch' ? blankIds : name === 'Cust' && blankCustomers ? 100 : 0,
      null_pct: 0,
      unique_count: name === 'Cust' && blankCustomers ? 0 : 10,
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

function makeSchema(mapping: [string, CanonicalField][], receiptFillLines = 0, flagOrderId = false): SchemaInferenceContract {
  return {
    schema_version: '2.1',
    generated_at: '2026-09-26T00:00:00Z',
    model_used: 'claude-sonnet-5',
    domain_confidence: 0.9,
    domain_reasoning: 'sales lines',
    dataset_issues: [],
    columns: mapping.map(([name, field]) => ({
      source_name: name,
      semantic_type: 'text',
      canonical_field: field,
      confidence: 0.9,
      issues:
        flagOrderId && field === 'order_id'
          ? [{ code: 'order_id_not_one_order' as const, count: 8, pct: null, examples: [] }]
          : [],
    })),
    receipt_fill_lines: receiptFillLines,
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
    schema_version: '2.1',
    generated_at: '2026-09-26T00:00:00Z',
    rows_in: 100,
    rows_out: 100,
    columns_in: 6,
    columns_out: 6,
    changes: [],
    warnings: [],
    column_mapping: {},
  },
  notices: [],
}

function renderReview(
  mapping: [string, CanonicalField][],
  options: {
    blankIds?: number
    fill?: number
    notInventory?: boolean
    actions?: Record<string, TransformAction>
    blankCustomers?: boolean
    flagOrderId?: boolean
  } = {},
) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
  const onCancel = vi.fn()
  render(
    <ReviewPage
      baseUrl="http://localhost:8000"
      runId="run-1"
      filename="sales.csv"
      profile={makeProfile(mapping, options.blankIds, options.blankCustomers)}
      schema={makeSchema(mapping, options.fill, options.flagOrderId)}
      initialPlan={makePlan(mapping, options.actions)}
      notices={options.notInventory ? [{ code: 'NOT_INVENTORY', message: 'This does not look like sales data.' }] : []}
      onCancel={onCancel}
      onCleaned={vi.fn()}
    />,
  )
  return { executePlan, onCancel }
}

async function confirmedPlan(executePlan: ReturnType<typeof vi.mocked<typeof runsApi.executePlan>>) {
  fireEvent.click(screen.getByRole('button', { name: 'Confirm & Clean' }))
  await vi.waitFor(() => {
    expect(executePlan).toHaveBeenCalledTimes(1)
  })
  return executePlan.mock.calls[0][2]
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ReviewPage: blank order ids', () => {
  it('says how many lines have no order id and that the file then counts lines', () => {
    renderReview(MAPPED, { blankIds: 7 })

    expect(screen.getByText('Up to 7 lines have no order id')).toBeDefined()
    expect(screen.getByText(/the whole file counts lines, not orders/)).toBeDefined()
  })

  it('drops those lines when asked, and says their revenue leaves every figure', async () => {
    const { executePlan } = renderReview(MAPPED, { blankIds: 7 })

    fireEvent.click(screen.getByRole('button', { name: 'Drop these lines' }))

    expect(screen.getByText('Up to 7 lines with no order id will be dropped')).toBeDefined()
    expect(screen.getByText(/their revenue leaves every figure/)).toBeDefined()
    const sent = await confirmedPlan(executePlan)
    expect(sent.column_actions.find((c) => c.source_name === 'Inv')?.action).toBe('drop_rows_missing')
  })

  it('offers another upload', () => {
    const { onCancel } = renderReview(MAPPED, { blankIds: 7 })

    fireEvent.click(screen.getByRole('button', { name: 'Upload a fixed file' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('keeps the lines and hides the notice when asked (mutation check F9)', () => {
    renderReview(MAPPED, { blankIds: 7 })

    fireEvent.click(screen.getByRole('button', { name: 'Keep and count lines' }))

    expect(screen.queryByText(/have no order id/)).toBeNull()
  })

  it('asks nothing about orders for a file that is not sales data (mutation check F10)', () => {
    renderReview(WITHOUT_CUSTOMER, { blankIds: 7, notInventory: true })

    expect(screen.queryByText(/have no order id/)).toBeNull()
    expect(screen.queryByText(/a receipt number\?/)).toBeNull()
  })

  it('warns that stock-in lines with no id would be dropped too (cycle 2 F7)', () => {
    renderReview([...MAPPED, ['Type', 'transaction_type']], { blankIds: 7 })

    expect(screen.getByText(/stock-in lines with no order id are dropped too/)).toBeDefined()
  })

  it('asks again about blank ids after the order id moves to another column (cycle 2 F8)', () => {
    renderReview([...MAPPED, ['Batch', 'ignore']], { blankIds: 5 })
    fireEvent.click(screen.getByRole('button', { name: 'Keep and count lines' }))

    fireEvent.change(screen.getAllByDisplayValue('order / invoice id')[0], { target: { value: 'ignore' } })
    const ignored = screen.getAllByDisplayValue('ignore')
    fireEvent.change(ignored[ignored.length - 1], { target: { value: 'order_id' } })

    expect(screen.getByText('Up to 5 lines have no order id')).toBeDefined()
  })

  it('shows nothing when every line has an id', () => {
    renderReview(MAPPED)

    expect(screen.queryByText(/have no order id/)).toBeNull()
  })
})

describe('ReviewPage: the receipt question', () => {
  it('asks when there is no customer column, and sends the answer', async () => {
    const { executePlan } = renderReview(WITHOUT_CUSTOMER)

    expect(screen.getByText('Is "Inv" a receipt number?')).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'Yes, a receipt number' }))

    const sent = await confirmedPlan(executePlan)
    expect(sent.confirmations).toEqual({ order_id_is_receipt: true, customer_on_first_line_only: null })
  })

  it('sends no answer when the user gives none, and Confirm is not blocked', async () => {
    const { executePlan } = renderReview(WITHOUT_CUSTOMER)

    const sent = await confirmedPlan(executePlan)

    expect(sent.confirmations).toEqual({ order_id_is_receipt: null, customer_on_first_line_only: null })
  })

  it('asks again, and sends nothing, after the order id moves to another column (review B)', async () => {
    const { executePlan } = renderReview([...WITHOUT_CUSTOMER, ['Batch', 'ignore']])
    fireEvent.click(screen.getByRole('button', { name: 'Yes, a receipt number' }))

    fireEvent.change(screen.getAllByDisplayValue('order / invoice id')[0], { target: { value: 'ignore' } })
    const ignored = screen.getAllByDisplayValue('ignore')
    fireEvent.change(ignored[ignored.length - 1], { target: { value: 'order_id' } })

    expect(screen.getByText('Is "Batch" a receipt number?')).toBeDefined()
    const sent = await confirmedPlan(executePlan)
    expect(sent.confirmations).toEqual({ order_id_is_receipt: null, customer_on_first_line_only: null })
  })

  it('does not promise orders by id while kept lines have no id (cycle 2 F9)', () => {
    renderReview(WITHOUT_CUSTOMER, { blankIds: 3 })
    fireEvent.click(screen.getByRole('button', { name: 'Keep and count lines' }))
    fireEvent.click(screen.getByRole('button', { name: 'Yes, a receipt number' }))

    expect(screen.getByText(/once every sale and return line has an id/)).toBeDefined()
    expect(screen.queryByText('Orders are counted by this column.')).toBeNull()
  })

  it('warns that a plan filling the blank customers in lets the id pass (cycle 3 F1)', () => {
    renderReview(MAPPED, { blankCustomers: true, actions: { Cust: 'impute_constant' } })

    expect(screen.getByText('Is "Inv" a receipt number?')).toBeDefined()
    expect(screen.getByText(/fills the blank customers in/)).toBeDefined()
  })

  it('keeps and shows a No after a customer column is mapped (cycle 3 F2)', async () => {
    const { executePlan } = renderReview([...WITHOUT_CUSTOMER, ['Buyer', 'ignore']])
    fireEvent.click(screen.getByRole('button', { name: 'No, a batch code' }))

    const ignored = screen.getAllByDisplayValue('ignore')
    fireEvent.change(ignored[ignored.length - 1], { target: { value: 'customer' } })

    expect(screen.getByText('"Inv" is not a receipt number')).toBeDefined()
    const sent = await confirmedPlan(executePlan)
    expect(sent.confirmations?.order_id_is_receipt).toBe(false)
  })

  it('does not promise orders by id when stage 1 found its ids spanning days (cycle 3 F4)', () => {
    renderReview(WITHOUT_CUSTOMER, { flagOrderId: true })
    fireEvent.click(screen.getByRole('button', { name: 'Yes, a receipt number' }))

    expect(screen.getByText(/ids spanning several days or customers/)).toBeDefined()
    expect(screen.queryByText('Orders are counted by this column.')).toBeNull()
  })

  it('does not ask when there is a customer column', () => {
    renderReview(MAPPED)

    expect(screen.queryByText(/a receipt number\?/)).toBeNull()
  })
})

describe('ReviewPage: the fill question', () => {
  it('asks with the count stage 1 measured, and sends a no', async () => {
    const { executePlan } = renderReview(MAPPED, { fill: 12 })

    expect(screen.getByText("Is the customer written on a receipt's first line only?")).toBeDefined()
    expect(screen.getByText(/12 lines have no customer but share a receipt number/)).toBeDefined()
    fireEvent.click(screen.getByRole('button', { name: 'No, leave them without a customer' }))

    const sent = await confirmedPlan(executePlan)
    expect(sent.confirmations).toEqual({ order_id_is_receipt: null, customer_on_first_line_only: false })
  })

  it('lets an answer be changed', () => {
    renderReview(MAPPED, { fill: 12 })

    fireEvent.click(screen.getByRole('button', { name: 'Yes, the first line only' }))
    fireEvent.click(screen.getByRole('button', { name: 'Change' }))

    expect(screen.getByRole('button', { name: 'Yes, the first line only' })).toBeDefined()
  })

  it('says an unanswered question fills, and that No keeps them apart (review A)', () => {
    renderReview(MAPPED, { fill: 12 })

    expect(screen.getByText(/they are taken to be unless you answer No/)).toBeDefined()
  })

  it('says it could not count them when there is no schema (review L)', () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={makeProfile(MAPPED)}
        schema={null}
        initialPlan={makePlan(MAPPED)}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )

    expect(screen.getByText(/could not count these lines/)).toBeDefined()
    expect(screen.queryByText(/mapping changed/)).toBeNull()
  })

  it('does not promise a fill while kept lines have no id (cycle 3 F4)', () => {
    renderReview(MAPPED, { fill: 12, blankIds: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'Keep and count lines' }))
    fireEvent.click(screen.getByRole('button', { name: 'Yes, the first line only' }))

    expect(screen.getByText(/until then the file counts lines and nothing is filled/)).toBeDefined()
  })

  it('does not ask when stage 1 measured no fill', () => {
    renderReview(MAPPED, { fill: 0 })

    expect(screen.queryByText(/first line only\?/)).toBeNull()
  })
})
