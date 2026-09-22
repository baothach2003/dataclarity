// Integration coverage for the screen state machine (docs/SPECS.md section 3):
// Upload -> Analyzing -> Review -> Results, and the AI_UNAVAILABLE branch that
// must skip POST /plan entirely (SPECS: calling it needs schema_inference.json,
// which a degraded schema step never writes).

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import * as runsApi from './api/runs.ts'
import { ApiError } from './api/errors.ts'
import type { RunUpload } from './api/runs.ts'
import type { ProfileContract, RunCreated, SchemaInferenceContract } from './types/contracts.ts'

vi.mock('./api/runs.ts', () => ({
  createRun: vi.fn(),
  getProfile: vi.fn(),
  analyzeSchema: vi.fn(),
  proposePlan: vi.fn(),
  previewPlan: vi.fn(),
  executePlan: vi.fn(),
  downloadCleanedCsv: vi.fn(),
}))

function upload(run: RunCreated): RunUpload {
  return { promise: Promise.resolve(run), cancel: vi.fn() }
}

function makeProfile(): ProfileContract {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    dataset: { rows: 5, columns: 2, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
    columns: [
      { name: 'sku', dtype: 'object', null_count: 0, null_pct: 0, unique_count: 5, min: null, max: null, mean: null, median: null, q1: null, q3: null, top_values: [], sample_values: [] },
      { name: 'name', dtype: 'object', null_count: 0, null_pct: 0, unique_count: 5, min: null, max: null, mean: null, median: null, q1: null, q3: null, top_values: [], sample_values: [] },
    ],
  }
}

function makeSchema(): SchemaInferenceContract {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    model_used: 'claude-sonnet-5',
    domain_confidence: 0.9,
    domain_reasoning: 'looks like sales data',
    dataset_issues: [],
    columns: [
      { source_name: 'sku', semantic_type: 'identifier', canonical_field: 'sku', confidence: 0.9, issues: [] },
      { source_name: 'name', semantic_type: 'text', canonical_field: 'product_name', confidence: 0.9, issues: [] },
    ],
  }
}

async function uploadAFile() {
  const input = document.querySelector('input[type="file"]')
  if (!(input instanceof HTMLInputElement)) {
    throw new Error('file input not found')
  }
  const file = new File(['sku,name\nA1,Mug\n'], 'sales.csv', { type: 'text/csv' })
  fireEvent.change(input, { target: { files: [file] } })
  await vi.waitFor(() => {
    expect(runsApi.createRun).toHaveBeenCalled()
  })
}

beforeEach(() => {
  vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000')
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

describe('App: the full stage 1 screen sequence', () => {
  it('uploads, analyzes, proposes a plan and reaches Review with everything the API returned', async () => {
    vi.mocked(runsApi.createRun).mockReturnValue(
      upload({ run_id: 'run-1', filename: 'sales.csv', size_bytes: 20, status: 'uploaded' }),
    )
    vi.mocked(runsApi.analyzeSchema).mockResolvedValue({
      run_id: 'run-1',
      status: 'profiled',
      schema_inference: makeSchema(),
      notices: [],
    })
    vi.mocked(runsApi.getProfile).mockResolvedValue(makeProfile())
    vi.mocked(runsApi.proposePlan).mockResolvedValue({
      run_id: 'run-1',
      status: 'planned',
      plan: {
        schema_version: '1.0',
        generated_at: '2026-09-22T00:00:00Z',
        source: 'ai',
        dataset_actions: [],
        column_actions: [
          { source_name: 'sku', semantic_type: 'identifier', canonical_field: 'sku', action: 'trim_whitespace', params: {}, rationale: '', alternatives: [], edited_by_user: false },
          { source_name: 'name', semantic_type: 'text', canonical_field: 'product_name', action: 'trim_whitespace', params: {}, rationale: '', alternatives: [], edited_by_user: false },
        ],
      },
      notices: [],
    })
    vi.mocked(runsApi.previewPlan).mockResolvedValue({
      run_id: 'run-1',
      preview: { rows_in_file: 5, sample_rows: 5, sampled: false, rows_after: 5, columns_after: ['sku', 'name'], rows: [], deltas: [] },
    })

    render(<App />)
    await uploadAFile()

    expect(await screen.findByText('Review cleaning plan')).toBeDefined()
    expect(runsApi.analyzeSchema).toHaveBeenCalledWith('http://localhost:8000', 'run-1')
    expect(runsApi.getProfile).toHaveBeenCalledWith('http://localhost:8000', 'run-1')
    expect(runsApi.proposePlan).toHaveBeenCalledWith('http://localhost:8000', 'run-1')
  })

  it('skips POST /plan when the schema step came back AI_UNAVAILABLE', async () => {
    vi.mocked(runsApi.createRun).mockReturnValue(
      upload({ run_id: 'run-2', filename: 'sales.csv', size_bytes: 20, status: 'uploaded' }),
    )
    vi.mocked(runsApi.analyzeSchema).mockResolvedValue({
      run_id: 'run-2',
      status: 'profiled',
      schema_inference: null,
      notices: [{ code: 'AI_UNAVAILABLE', message: 'The AI assistant could not analyze this file.' }],
    })
    vi.mocked(runsApi.getProfile).mockResolvedValue(makeProfile())
    vi.mocked(runsApi.previewPlan).mockResolvedValue({
      run_id: 'run-2',
      preview: { rows_in_file: 5, sample_rows: 5, sampled: false, rows_after: 5, columns_after: ['sku', 'name'], rows: [], deltas: [] },
    })

    render(<App />)
    await uploadAFile()

    expect(await screen.findByText('AI suggestions are unavailable right now')).toBeDefined()
    expect(runsApi.proposePlan).not.toHaveBeenCalled()
  })

  it('shows the fixed error copy and returns to Upload when analyze-schema fails hard', async () => {
    vi.mocked(runsApi.createRun).mockReturnValue(
      upload({ run_id: 'run-3', filename: 'sales.csv', size_bytes: 20, status: 'uploaded' }),
    )
    vi.mocked(runsApi.analyzeSchema).mockRejectedValue(new ApiError('PARSE_FAILED', 'bad file'))

    render(<App />)
    await uploadAFile()

    expect(await screen.findByText("We couldn't read this file")).toBeDefined()
    fireEvent.click(screen.getByText('Upload a different file'))
    expect(await screen.findByText('Upload a sales or inventory file')).toBeDefined()
  })
})
