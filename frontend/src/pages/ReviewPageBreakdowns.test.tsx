import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type { BreakdownQuestion } from '../types/breakdowns.ts'
import type { CleaningPlan, ColumnAction, ExecuteResponse, PreviewResponse, ProfileContract } from '../types/contracts.ts'

// The dashboard's step 4 (Thach's D4; docs/DASHBOARD_DESIGN.md 5.4): Review shows the columns stage 1 found able
// to split sales and the AI's suggestion among them; the user removes or adds columns, at most two, and what is
// selected goes with the plan to execute. The AI is never called here: the server's answer is faked.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
  lineSummary: vi.fn(() => new Promise(() => undefined)),
  currencyQuestion: vi.fn(() => new Promise(() => undefined)),
  breakdownQuestion: vi.fn(),
}))

function action(name: string, field: ColumnAction['canonical_field']): ColumnAction {
  return { source_name: name, semantic_type: 'text', canonical_field: field, action: 'flag_only', params: {}, rationale: '', alternatives: [], edited_by_user: false }
}

const PLAN: CleaningPlan = {
  schema_version: '4.4',
  generated_at: '2026-10-14T00:00:00Z',
  source: 'ai',
  dataset_actions: [],
  column_actions: [action('Day', 'transaction_date'), action('Qty', 'quantity'), action('Price', 'unit_price'),
    action('Item', 'product_name'), action('Payment Method', 'ignore'), action('Location', 'ignore'), action('Till', 'ignore')],
}

const PROFILE: ProfileContract = {
  schema_version: '1.2',
  generated_at: '2026-10-14T00:00:00Z',
  dataset: { rows: 10, columns: 7, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
  columns: ['Day', 'Qty', 'Price', 'Item', 'Payment Method', 'Location', 'Till'].map((name) => ({
    name, dtype: 'str', null_count: 0, null_pct: 0, unique_count: 3, min: null, max: null, mean: null, median: null,
    q1: null, q3: null, top_values: [], sample_values: [], number_format: null,
  })),
}

const PREVIEW: PreviewResponse = {
  run_id: 'run-1',
  preview: { rows_in_file: 10, sample_rows: 10, sampled: false, rows_after: 10, columns_after: [], rows: [], deltas: [] },
}

const EXECUTED: ExecuteResponse = {
  run_id: 'run-1',
  status: 'cleaned',
  report: {
    schema_version: '4.4', generated_at: '2026-10-14T00:00:00Z', rows_in: 10, rows_out: 10, columns_in: 7,
    columns_out: 7, changes: [], warnings: [], column_mapping: {},
  },
  notices: [],
}

const SUGGESTED: BreakdownQuestion = {
  eligible: [
    { column: 'Payment Method', values: ['Cash', 'Credit Card', 'Digital Wallet'] },
    { column: 'Location', values: ['Online', 'In-store'] },
    { column: 'Till', values: ['T1', 'T2'] },
  ],
  suggested: ['Location', 'Payment Method'],
  status: 'chosen',
  message: "Suggested from your file's columns. Change or remove them; at most two.",
}

function renderReview(question: BreakdownQuestion) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const breakdownQuestion = vi.mocked(runsApi.breakdownQuestion).mockResolvedValue({ run_id: 'run-1', question })
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
  render(
    <ReviewPage baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" profile={PROFILE} schema={null}
      initialPlan={PLAN} notices={[]} onCancel={vi.fn()} onCleaned={vi.fn()} />,
  )
  return { breakdownQuestion, executePlan }
}

async function confirm(executePlan: ReturnType<typeof vi.fn>): Promise<CleaningPlan> {
  const button = screen.getByRole('button', { name: 'Confirm & Clean' })
  if (!(button instanceof HTMLButtonElement)) {
    throw new Error('Confirm is a button')
  }
  await waitFor(() => {
    expect(button.disabled).toBe(false)
  })
  fireEvent.click(button)
  await waitFor(() => {
    expect(executePlan).toHaveBeenCalled()
  })
  return executePlan.mock.calls[0][2] as CleaningPlan
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ReviewPage: the columns to split sales by', () => {
  it('asks stage 1 about the plan as it stands and shows the suggestion with its values and where it came from', async () => {
    const { breakdownQuestion } = renderReview(SUGGESTED)
    expect(await screen.findByText('Location')).toBeTruthy()
    expect(breakdownQuestion.mock.calls[0][2].column_actions).toEqual(PLAN.column_actions)
    expect(screen.getByText("Suggested from your file's columns. Change or remove them; at most two.")).toBeTruthy()
    expect(screen.getByText(/\(Cash, Credit Card, Digital Wallet\)/)).toBeTruthy()
  })

  it('sends the suggestion unchanged when the user leaves it', async () => {
    const { executePlan } = renderReview(SUGGESTED)
    await screen.findByText('Location')
    expect((await confirm(executePlan)).breakdowns).toEqual(['Location', 'Payment Method'])
  })

  it('lets the user remove one and add another, at most two', async () => {
    const { executePlan } = renderReview(SUGGESTED)
    await screen.findByText('Location')
    const add = screen.getByRole('combobox', { name: 'Add a column to split sales by' })
    if (!(add instanceof HTMLSelectElement)) {
      throw new Error('the add control is a select')
    }
    expect(add.disabled).toBe(true) // two chosen: at most two
    fireEvent.click(screen.getByRole('button', { name: 'Remove Payment Method' }))
    expect(add.disabled).toBe(false)
    fireEvent.change(add, { target: { value: 'Till' } })
    expect((await confirm(executePlan)).breakdowns).toEqual(['Location', 'Till'])
  })

  it('never holds Confirm for the suggestion, and says what confirming before it arrives means (step 4 review #6)', async () => {
    const { executePlan } = renderReview(SUGGESTED)
    vi.mocked(runsApi.breakdownQuestion).mockReset().mockReturnValue(new Promise(() => undefined))
    cleanup()
    render(
      <ReviewPage baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" profile={PROFILE} schema={null}
        initialPlan={PLAN} notices={[]} onCancel={vi.fn()} onCleaned={vi.fn()} />,
    )
    expect(screen.getByText(/If you confirm now, sales are not split by any column\./)).toBeTruthy()
    expect((await confirm(executePlan)).breakdowns).toBeUndefined()
  })

  it('does not hold Confirm when the question failed: no split is sent', async () => {
    const { executePlan } = renderReview(SUGGESTED)
    vi.mocked(runsApi.breakdownQuestion).mockReset().mockRejectedValue(new Error('down'))
    cleanup()
    render(
      <ReviewPage baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" profile={PROFILE} schema={null}
        initialPlan={PLAN} notices={[]} onCancel={vi.fn()} onCleaned={vi.fn()} />,
    )
    expect(await screen.findByText('The columns to split sales by could not be read')).toBeTruthy()
    expect((await confirm(executePlan)).breakdowns).toBeUndefined()
  })

  it('sends no breakdown when the user removes them all', async () => {
    const { executePlan } = renderReview(SUGGESTED)
    await screen.findByText('Location')
    fireEvent.click(screen.getByRole('button', { name: 'Remove Location' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove Payment Method' }))
    expect(screen.getByText('Sales will not be split by any column.')).toBeTruthy()
    expect((await confirm(executePlan)).breakdowns).toBeUndefined()
  })

  it('with no suggestion, offers the columns and selects none', async () => {
    const { executePlan } = renderReview({ ...SUGGESTED, suggested: [], status: 'ai_unavailable',
      message: 'No suggestion could be made. You can pick up to two from the list.' })
    expect(await screen.findByText('No suggestion could be made. You can pick up to two from the list.')).toBeTruthy()
    expect((await confirm(executePlan)).breakdowns).toBeUndefined()
  })

  it('says why when no column can split sales, and offers nothing', async () => {
    renderReview({ eligible: [], suggested: [], status: 'none_eligible', message: 'No column of your file can split sales.' })
    expect(await screen.findByText('No column of your file can split sales.')).toBeTruthy()
    expect(screen.queryByRole('combobox', { name: 'Add a column to split sales by' })).toBeNull()
  })

  it("shows a column's own text as text, never markup", async () => {
    renderReview({ ...SUGGESTED, eligible: [{ column: '<b>Store</b>', values: ['<i>A</i>'] }], suggested: ['<b>Store</b>'] })
    expect(await screen.findByText('<b>Store</b>')).toBeTruthy()
    expect(document.querySelector('b b')).toBeNull()
  })
})
