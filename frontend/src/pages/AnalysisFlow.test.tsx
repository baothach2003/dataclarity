import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as analysisApi from '../api/analysis.ts'
import type { AnalysisProgress, AnalysisResult } from '../api/analysis.ts'
import { ApiError, UnreachableError } from '../api/errors.ts'
import { AnalysisFlow } from './AnalysisFlow.tsx'
import { makeReport } from './insightsFixture.ts'

vi.mock('../api/analysis.ts', () => ({ runAnalysis: vi.fn(), downloadReportHtml: vi.fn() }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const RESULT: AnalysisResult = { report: makeReport(), diagnosis: { tree: null, calendar: null } }

function flow(onBack = vi.fn()) {
  return render(
    <StrictMode>
      <AnalysisFlow baseUrl="http://localhost:8000" runId="run-1" filename="sales.csv" rows={12301} onBack={onBack} />
    </StrictMode>,
  )
}

// Results -> Analyzing -> Insights (SPECS 3; PROJECT_PLAN 6E). The server runs
// one step per run at a time and refuses a second (INVALID_STATE
// step_in_progress): the run starts once, even when StrictMode runs the
// component's effects twice.
describe('AnalysisFlow', () => {
  it('runs the analysis once, shows each step, then the Insights page', async () => {
    let finish: ((result: AnalysisResult) => void) | undefined
    let progress: AnalysisProgress | undefined
    vi.mocked(analysisApi.runAnalysis).mockImplementation((_base, _run, given) => {
      progress = given
      given.onStep('analyze')
      return new Promise((resolve) => { finish = resolve })
    })
    flow()

    expect(vi.mocked(analysisApi.runAnalysis)).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Computing metrics').closest('li')?.className).toContain('analyzing-step--active')
    act(() => progress?.onStep('diagnose'))
    expect(screen.getByText('Diagnosing causes').closest('li')?.className).toContain('analyzing-step--active')
    await act(async () => {
      finish?.(RESULT)
      await Promise.resolve()
    })

    expect(screen.getByRole('heading', { level: 1, name: 'Insights' })).toBeDefined()
  })

  // The 6E1 review (#7): a step that failed after the diagnosis is resumed
  // where it failed, with the diagnosis it already has.
  it('tries again from the step that failed, keeping what came before', async () => {
    vi.mocked(analysisApi.runAnalysis).mockImplementationOnce((_base, _run, progress) => {
      progress.onStep('analyze')
      progress.onStep('diagnose')
      progress.onDiagnosis?.({ tree: 'first run' })
      progress.onStep('predict')
      return Promise.reject(new UnreachableError('the server could not be reached'))
    })
    flow()
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))

    expect(vi.mocked(analysisApi.runAnalysis).mock.calls[1]?.[3]).toEqual({ from: 'predict', diagnosis: { tree: 'first run' } })
  })

  it('starts again from the beginning when the failure came before the diagnosis', async () => {
    vi.mocked(analysisApi.runAnalysis).mockImplementationOnce((_base, _run, progress) => {
      progress.onStep('analyze')
      return Promise.reject(new ApiError('INTERNAL_ERROR', 'boom'))
    })
    vi.mocked(analysisApi.runAnalysis).mockImplementationOnce((_base, _run, progress) => {
      progress.onStep('analyze')
      return Promise.resolve(RESULT)
    })
    flow()
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Insights' })).toBeDefined()
    expect(vi.mocked(analysisApi.runAnalysis).mock.calls[1]?.[3]).toBeUndefined()
  })

  it('goes back to Results on request', async () => {
    vi.mocked(analysisApi.runAnalysis).mockRejectedValue(new ApiError('INTERNAL_ERROR', 'boom'))
    const onBack = vi.fn()
    flow(onBack)

    fireEvent.click(await screen.findByRole('button', { name: 'Back to results' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
