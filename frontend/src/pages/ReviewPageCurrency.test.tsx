import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type { CleaningPlan, ColumnAction, ExecuteResponse, PreviewResponse, ProfileContract } from '../types/contracts.ts'
import type { CurrencyFinding, CurrencyQuestion } from '../types/currency.ts'

// The report redesign's step 5 (design 6.2 and 6.3): Review always asks the file's currency, from stage 1's
// own reading of the raw file on the plan as edited (POST /currency). Found: its code pre-selected, with
// where it was found; anything else: "Not stated" (never assumed); more than one currency: stage 1's block,
// no answer offered, Confirm stopped. Written before the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
  lineSummary: vi.fn(() => new Promise(() => undefined)),
  currencyQuestion: vi.fn(),
}))

function action(name: string, field: ColumnAction['canonical_field']): ColumnAction {
  return { source_name: name, semantic_type: 'text', canonical_field: field, action: 'flag_only', params: {}, rationale: '', alternatives: [], edited_by_user: false }
}

const PLAN: CleaningPlan = {
  schema_version: '4.3',
  generated_at: '2026-10-06T00:00:00Z',
  source: 'ai',
  dataset_actions: [],
  column_actions: [action('Day', 'transaction_date'), action('Qty', 'quantity'), action('Price', 'unit_price'), action('Item', 'product_name')],
}

const PROFILE: ProfileContract = {
  schema_version: '1.2',
  generated_at: '2026-10-06T00:00:00Z',
  dataset: { rows: 10, columns: 4, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
  columns: ['Day', 'Qty', 'Price', 'Item'].map((name) => ({
    name, dtype: 'str', null_count: 0, null_pct: 0, unique_count: 10, min: null, max: null, mean: null, median: null,
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
    schema_version: '4.3', generated_at: '2026-10-06T00:00:00Z', rows_in: 10, rows_out: 10, columns_in: 4,
    columns_out: 4, changes: [], warnings: [], column_mapping: {},
  },
  notices: [],
}

const ALL = ['GBP', 'EUR', 'USD', 'AUD', 'CAD', 'NZD']

function finding(patch: Partial<CurrencyFinding>): CurrencyFinding {
  return { kind: 'none', code: null, source: null, candidates: [], evidence: null, parts: [], more_parts: 0, hint: null, unreadable: 0, ...patch }
}

function question(patch: Partial<CurrencyQuestion>): CurrencyQuestion {
  return { finding: finding({}), options: ALL, selected: 'not_stated', blocked: null, unreadable: null, hint: null, ...patch }
}

const FOUND = question({
  finding: finding({ kind: 'found', code: 'GBP', source: 'symbol', evidence: 'GBP, from the £ in column Price' }),
  selected: 'GBP',
})
const BLOCK = 'Your file has amounts in more than one currency (GBP: 3 lines, EUR: 1 line). DataClarity cannot add different currencies together. Split the file by currency and upload each part.'
const MIXED = question({
  finding: finding({ kind: 'mixed', parts: [{ label: 'GBP', lines: 3 }, { label: 'EUR', lines: 1 }] }),
  options: [], selected: null, blocked: BLOCK,
})

function renderReview(asked: CurrencyQuestion) {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const currencyQuestion = vi.mocked(runsApi.currencyQuestion).mockResolvedValue({ run_id: 'run-1', question: asked })
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
  render(
    <ReviewPage baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" profile={PROFILE} schema={null}
      initialPlan={PLAN} notices={[]} onCancel={vi.fn()} onCleaned={vi.fn()} />,
  )
  return { currencyQuestion, executePlan }
}

async function picker(): Promise<HTMLSelectElement> {
  const select = await screen.findByRole('combobox', { name: 'Which currency are the amounts in?' })
  if (!(select instanceof HTMLSelectElement)) {
    throw new Error('the currency picker is a select')
  }
  return select
}

function confirmButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: 'Confirm & Clean' })
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('ReviewPage: the currency question', () => {
  it("asks stage 1 about the plan as it stands, the money column the plan's", async () => {
    const { currencyQuestion } = renderReview(FOUND)
    await picker()

    const [, runId, plan] = currencyQuestion.mock.calls[0]
    expect(runId).toBe('run-1')
    expect(plan.column_actions.find((c) => c.canonical_field === 'unit_price')?.source_name).toBe('Price')
  })

  it('pre-selects a found currency, with where it was found', async () => {
    renderReview(FOUND)

    expect((await picker()).value).toBe('GBP')
    expect(screen.getByText('Found in your file: GBP, from the £ in column Price')).toBeDefined()
  })

  it('pre-selects "Not stated" when nothing was found - never a currency', async () => {
    renderReview(question({}))
    const select = await picker()

    expect(select.value).toBe('not_stated')
    expect(within(select).getAllByRole('option').map((option) => option.getAttribute('value'))).toEqual(['not_stated', ...ALL])
    expect(within(select).getByRole('option', { name: 'Not stated' })).toBeDefined()
  })

  it('offers a narrowed family first and pre-selects nothing but "Not stated"', async () => {
    renderReview(question({ finding: finding({ kind: 'narrowed', candidates: ['USD', 'AUD'] }), options: ['USD', 'AUD', 'CAD', 'EUR'] }))
    const select = await picker()

    expect(select.value).toBe('not_stated')
    expect(within(select).getAllByRole('option').map((option) => option.getAttribute('value'))).toEqual(['not_stated', 'USD', 'AUD', 'CAD', 'EUR'])
  })

  it("shows stage 1's own words for a hint and unreadable cells", async () => {
    renderReview(question({ hint: 'Where your file names its currency, it says: Euro', unreadable: '1 cell where the file names its currency could not be read.' }))
    await picker()

    expect(screen.getByText('Where your file names its currency, it says: Euro')).toBeDefined()
    expect(screen.getByText('1 cell where the file names its currency could not be read.')).toBeDefined()
  })

  it('sends the answer the user picked as confirmations.currency', async () => {
    const { executePlan } = renderReview(FOUND)

    fireEvent.change(await picker(), { target: { value: 'EUR' } })
    fireEvent.click(confirmButton())

    await waitFor(() => { expect(executePlan).toHaveBeenCalled() })
    expect(executePlan.mock.calls[0][2].confirmations?.currency).toBe('EUR')
  })

  it('sends no answer when the user left it, so stage 1 applies what it found', async () => {
    const { executePlan } = renderReview(FOUND)
    await picker()

    fireEvent.click(confirmButton())

    await waitFor(() => { expect(executePlan).toHaveBeenCalled() })
    expect(executePlan.mock.calls[0][2].confirmations?.currency).toBeUndefined()
  })

  it("blocks a file with more than one currency: stage 1's sentence, no answer, Confirm stopped", async () => {
    renderReview(MIXED)

    expect(await screen.findByText(BLOCK)).toBeDefined()
    expect(screen.queryByRole('combobox', { name: 'Which currency are the amounts in?' })).toBeNull()
    expect(confirmButton().disabled).toBe(true)
    expect(screen.getByText('This file cannot run: it has amounts in more than one currency')).toBeDefined()
  })
})

// --- step 5's review --------------------------------------------------------------------------------------------

describe("ReviewPage: the currency question, the review's findings", () => {
  it('is shown while stage 1 reads the file - never absent', () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
    vi.mocked(runsApi.currencyQuestion).mockReturnValue(new Promise(() => undefined))
    render(
      <ReviewPage baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" profile={PROFILE} schema={null}
        initialPlan={PLAN} notices={[]} onCancel={vi.fn()} onCleaned={vi.fn()} />,
    )

    expect(screen.getByText('Which currency are the amounts in?')).toBeDefined()
    expect(screen.getByText("Reading the file's currency…")).toBeDefined()
  })

  it('says why a narrowed family comes first, with where the sign was found', async () => {
    renderReview(question({
      finding: finding({ kind: 'narrowed', candidates: ['USD', 'AUD'], evidence: 'from the $ in column Price' }),
      options: ['USD', 'AUD', 'CAD'],
    }))
    await picker()

    expect(screen.getByText('The sign in your file (from the $ in column Price) is used by several currencies; those are listed first.')).toBeDefined()
  })
})

describe('useCurrencyQuestion: the money column', () => {
  it('asks again when the money column changes, and drops an answer about the old one', async () => {
    const { renderHook, act } = await import('@testing-library/react')
    const { useCurrencyQuestion } = await import('./useCurrencyQuestion.ts')
    const ask = vi.mocked(runsApi.currencyQuestion).mockResolvedValue({ run_id: 'run-1', question: FOUND })
    const other: CleaningPlan = {
      ...PLAN,
      column_actions: PLAN.column_actions.map((c) =>
        c.source_name === 'Price' ? { ...c, canonical_field: 'ignore' } : c.source_name === 'Item' ? { ...c, canonical_field: 'unit_price' } : c),
    }
    const hook = renderHook(({ plan }) => useCurrencyQuestion('http://localhost:8000', 'run-1', plan, true), { initialProps: { plan: PLAN } })
    await waitFor(() => { expect(hook.result.current.question).not.toBeNull() })
    act(() => { hook.result.current.choose('EUR') })
    expect(hook.result.current.answer).toBe('EUR')

    hook.rerender({ plan: other })

    expect(hook.result.current.answer).toBeNull()
    await waitFor(() => { expect(ask).toHaveBeenCalledTimes(2) })
    expect(ask.mock.calls[1][2].column_actions.find((c) => c.canonical_field === 'unit_price')?.source_name).toBe('Item')
  })

  it('keeps the answer while other edits leave the money column alone', async () => {
    const { renderHook, act } = await import('@testing-library/react')
    const { useCurrencyQuestion } = await import('./useCurrencyQuestion.ts')
    const ask = vi.mocked(runsApi.currencyQuestion).mockResolvedValue({ run_id: 'run-1', question: FOUND })
    const hook = renderHook(({ plan }) => useCurrencyQuestion('http://localhost:8000', 'run-1', plan, true), { initialProps: { plan: PLAN } })
    await waitFor(() => { expect(hook.result.current.question).not.toBeNull() })
    act(() => { hook.result.current.choose('EUR') })

    hook.rerender({ plan: { ...PLAN, dataset_actions: [] } })

    expect(hook.result.current.answer).toBe('EUR')
    expect(ask).toHaveBeenCalledTimes(1)
  })
})

describe('ReviewPage: asking again after an error (the scoped review)', () => {
  it('shows the question on its way again, not the old error', async () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
    vi.mocked(runsApi.currencyQuestion)
      .mockRejectedValueOnce(new Error('network'))
      .mockReturnValueOnce(new Promise(() => undefined))
    render(
      <ReviewPage baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" profile={PROFILE} schema={null}
        initialPlan={PLAN} notices={[]} onCancel={vi.fn()} onCleaned={vi.fn()} />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Ask again' }))

    expect(await screen.findByText("Reading the file's currency…")).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Ask again' })).toBeNull()
  })
})
