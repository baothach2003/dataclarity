import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeReport } from '../pages/insightsFixture.ts'
import { downloadReportHtml, runAnalysis } from './analysis.ts'
import type { AnalysisStep } from './analysis.ts'
import { ApiError, UnreachableError } from './errors.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

const BODIES: Record<AnalysisStep, unknown> = {
  analyze: { run_id: 'run-1', status: 'analyzed', metrics: { schema_version: '13.0' }, notices: [] },
  diagnose: { run_id: 'run-1', status: 'analyzed', diagnosis: { tree: null, calendar: null }, notices: [] },
  predict: { run_id: 'run-1', status: 'analyzed', forecast: { points: [] }, notices: [] },
  report: { run_id: 'run-1', status: 'analyzed', report: makeReport(), html_url: '/api/runs/run-1/download/report.html', notices: [] },
}

function stubSteps(failAt?: AnalysisStep, body?: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((url: string) => {
    const step = url.split('/').pop() as AnalysisStep
    if (step === failAt) {
      return Promise.resolve(
        body === undefined
          ? Response.json(
              { error: { code: 'ANALYSIS_FAILED', message: 'Map a unit price column first.', details: { canonical_field: 'unit_price' } } },
              { status: 422 },
            )
          : Response.json(body),
      )
    }
    return Promise.resolve(Response.json(BODIES[step]))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

// Stages 2-5 in their order (SPECS 8): each POST only after the one before
// succeeded, the page told which step runs.
describe('runAnalysis', () => {
  it('runs analyze, diagnose, predict and report in order and returns the report', async () => {
    const fetchMock = stubSteps()
    const steps: AnalysisStep[] = []

    const result = await runAnalysis('http://localhost:8000/', 'run-1', { onStep: (step) => steps.push(step) })

    expect(steps).toEqual(['analyze', 'diagnose', 'predict', 'report'])
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual([
      'http://localhost:8000/api/runs/run-1/analyze',
      'http://localhost:8000/api/runs/run-1/diagnose',
      'http://localhost:8000/api/runs/run-1/predict',
      'http://localhost:8000/api/runs/run-1/report',
    ])
    expect(fetchMock.mock.calls.every((call) => (call[1] as RequestInit).method === 'POST')).toBe(true)
    expect(result.report.source_file).toBe('store_sales_2026Q2.csv')
    expect(result.diagnosis).toEqual({ tree: null, calendar: null })
  })

  it('stops at the first refusal and calls no later step', async () => {
    const fetchMock = stubSteps('analyze')

    const failure = runAnalysis('http://localhost:8000', 'run-1', { onStep: () => undefined })

    await expect(failure).rejects.toThrow(ApiError)
    await expect(failure).rejects.toMatchObject({ code: 'ANALYSIS_FAILED', details: { canonical_field: 'unit_price' } })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('checks the report body rather than trusting it', async () => {
    stubSteps('report', { run_id: 'run-1', status: 'analyzed', report: { source_file: 'x.csv' }, html_url: '', notices: [] })

    await expect(runAnalysis('http://localhost:8000', 'run-1', { onStep: () => undefined })).rejects.toThrow(UnreachableError)
  })

  it("checks the lists the page walks, a KPI's notes included", async () => {
    const report = makeReport()
    ;(report.layer_1_numbers.kpis[0] as unknown as Record<string, unknown>).notes = null
    stubSteps('report', { run_id: 'run-1', status: 'analyzed', report, html_url: '', notices: [] })

    await expect(runAnalysis('http://localhost:8000', 'run-1', { onStep: () => undefined })).rejects.toThrow(UnreachableError)
  })

  // The 6E1 review (#7): a failure at predict or report is resumed there -
  // analyze and diagnose are not run again, nor their later outputs removed.
  it('resumes from a later step with the diagnosis it already has', async () => {
    const fetchMock = stubSteps()
    const steps: AnalysisStep[] = []

    const result = await runAnalysis(
      'http://localhost:8000',
      'run-1',
      { onStep: (step) => steps.push(step) },
      { from: 'predict', diagnosis: { tree: 'kept' } },
    )

    expect(steps).toEqual(['predict', 'report'])
    expect(fetchMock.mock.calls.map((call) => String(call[0]).split('/').pop())).toEqual(['predict', 'report'])
    expect(result.diagnosis).toEqual({ tree: 'kept' })
  })

  it('hands over the diagnosis as soon as it has it, so a later failure can resume', async () => {
    stubSteps('predict')
    const onDiagnosis = vi.fn()

    await expect(runAnalysis('http://localhost:8000', 'run-1', { onStep: () => undefined, onDiagnosis })).rejects.toThrow(ApiError)
    expect(onDiagnosis).toHaveBeenCalledWith({ tree: null, calendar: null })
  })
})

describe('downloadReportHtml', () => {
  it('GETs the report page as a file', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('<!doctype html>', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const blob = await downloadReportHtml('http://localhost:8000', 'run-1')

    expect(await blob.text()).toBe('<!doctype html>')
    expect(fetchMock.mock.calls[0]?.[0]).toBe('http://localhost:8000/api/runs/run-1/download/report.html')
  })

  it('throws the error envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(Response.json({ error: { code: 'INVALID_STATE', message: 'Build the report first.' } }, { status: 409 })),
    )

    await expect(downloadReportHtml('http://localhost:8000', 'run-1')).rejects.toMatchObject({ code: 'INVALID_STATE' })
  })
})
