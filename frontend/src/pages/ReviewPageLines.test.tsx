import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from './ReviewPage.tsx'
import * as runsApi from '../api/runs.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ExecuteResponse,
  NonProductCandidate,
  PreviewResponse,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'

// Session 2E-d2 (Thach): Review asks what each line that may not be a product
// is; the user's class travels in the plan. Written before the code.

vi.mock('../api/runs.ts', () => ({
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  proposePlan: vi.fn(),
}))

const MAPPED: [string, CanonicalField][] = [
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Code', 'sku'],
  ['Item', 'product_name'],
]

const PLAN: CleaningPlan = {
  schema_version: '2.3',
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

const MANUAL: NonProductCandidate = {
  value: 'M',
  field: 'sku',
  name: 'Manual',
  lines: 1426,
  positive: 341104.9,
  negative: -423886.17,
  suggested: 'adjustment',
  word: 'manual',
}

const SCHEMA: SchemaInferenceContract = {
  schema_version: '2.3',
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
  non_product_candidates: [MANUAL],
}

const PREVIEW: PreviewResponse = {
  run_id: 'run-1',
  preview: { rows_in_file: 100, sample_rows: 100, sampled: false, rows_after: 100, columns_after: [], rows: [], deltas: [] },
}

const EXECUTED: ExecuteResponse = {
  run_id: 'run-1',
  status: 'cleaned',
  report: {
    schema_version: '2.3',
    generated_at: '2026-09-26T00:00:00Z',
    rows_in: 100,
    rows_out: 100,
    columns_in: 5,
    columns_out: 5,
    changes: [],
    warnings: [],
    column_mapping: {},
  },
  notices: [],
}

function renderReview() {
  vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
  const executePlan = vi.mocked(runsApi.executePlan).mockResolvedValue(EXECUTED)
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
  return executePlan
}

async function sentPlan(executePlan: ReturnType<typeof vi.mocked<typeof runsApi.executePlan>>) {
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

describe('ReviewPage: lines that may not be products (2E-d2)', () => {
  it('shows each candidate with its money and the suggestion, nothing chosen', () => {
    renderReview()

    expect(screen.getByText('Lines that may not be products')).toBeDefined()
    expect(screen.getByText(/"M" \(Manual\): 1,426 lines, \+341,104\.90 and -423,886\.17/)).toBeDefined()
    expect(screen.getByText(/suggested: an accounting adjustment/)).toBeDefined()
    const choice = screen.getByRole('combobox', { name: 'What is "M"?' })
    expect((choice as HTMLSelectElement).value).toBe('')
  })

  it('sends the class the user chose', async () => {
    const executePlan = renderReview()

    fireEvent.change(screen.getByRole('combobox', { name: 'What is "M"?' }), { target: { value: 'adjustment' } })

    const sent = await sentPlan(executePlan)
    expect(sent.confirmations?.line_classes).toEqual([{ value: 'M', field: 'sku', line_class: 'adjustment' }])
  })

  it('does not show an answer given for another SKU column (mutation check F8)', () => {
    vi.mocked(runsApi.previewPlan).mockResolvedValue(PREVIEW)
    const mapping: [string, CanonicalField][] = [...MAPPED, ['Other', 'ignore']]
    const postage: NonProductCandidate = { ...MANUAL, value: 'POSTAGE', name: null, suggested: 'charge', word: 'postage' }
    const plan: CleaningPlan = {
      ...PLAN,
      column_actions: [...PLAN.column_actions, { ...PLAN.column_actions[0], source_name: 'Other', canonical_field: 'ignore' }],
    }
    const profile: ProfileContract = {
      ...PROFILE,
      columns: mapping.map(([name]) => ({
        ...PROFILE.columns[0],
        name,
        top_values: name === 'Other' ? [{ value: 'POSTAGE', count: 30 }] : [],
      })),
    }
    render(
      <ReviewPage
        baseUrl="http://localhost:8000"
        runId="run-1"
        filename="sales.csv"
        profile={profile}
        schema={{ ...SCHEMA, non_product_candidates: [postage] }}
        initialPlan={plan}
        notices={[]}
        onCancel={vi.fn()}
        onCleaned={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByRole('combobox', { name: 'What is "POSTAGE"?' }), { target: { value: 'charge' } })

    fireEvent.change(screen.getByDisplayValue('SKU'), { target: { value: 'ignore' } })
    const ignored = screen.getAllByDisplayValue('ignore')
    fireEvent.change(ignored[ignored.length - 1], { target: { value: 'sku' } })

    const choice = screen.getByRole('combobox', { name: 'What is "POSTAGE"?' })
    expect((choice as HTMLSelectElement).value).toBe('')
  })

  it('sends no class for "a product", or with no answer', async () => {
    const executePlan = renderReview()

    fireEvent.change(screen.getByRole('combobox', { name: 'What is "M"?' }), { target: { value: 'product' } })

    const sent = await sentPlan(executePlan)
    expect(sent.confirmations?.line_classes).toBeUndefined()
  })
})
