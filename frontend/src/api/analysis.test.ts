import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeReport } from '../pages/insightsFixture.ts'
import { downloadReportHtml, runAnalysis } from './analysis.ts'
import type { AnalysisStep } from './analysis.ts'
import { ApiError, UnreachableError } from './errors.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

const BODIES: Record<AnalysisStep, unknown> = {
  analyze: { run_id: 'run-1', status: 'analyzed', metrics: { schema_version: '13.0', core: { orders_basis: 'lines' } }, notices: [] },
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
    // metrics.json's core.orders_basis (a CONTRACTS 11 FE field): the page names the lever's factors by it.
    expect(result.ordersBasis).toBe('lines')
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

  // The 6E2 review (#6): the causes' lists too - one the page walks that is not
  // a list would blank the whole app (no error boundary).
  it.each([
    ['hypotheses', (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes as unknown as Record<string, unknown>).hypotheses = null
    }],
    ["a hypothesis's evidence", (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes.hypotheses[0] as unknown as Record<string, unknown>).evidence = null
    }],
    ["a hypothesis's evidence text", (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes.hypotheses[0] as unknown as Record<string, unknown>).evidence_text = 'x'
    }],
    ["a hypothesis's label", (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes.hypotheses[0] as unknown as Record<string, unknown>).verdict_label = 3
    }],
    ["a hypothesis's lens", (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes.hypotheses[0] as unknown as Record<string, unknown>).lens = null
    }],
    ["a hypothesis's against flag", (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes.hypotheses[0] as unknown as Record<string, unknown>).moved_against = 'yes'
    }],
    ['the lines outside revenue', (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_1_numbers as unknown as Record<string, unknown>).outside_revenue = null
    }],
    ["a line outside revenue's reason", (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_1_numbers as unknown as Record<string, unknown>).outside_revenue = [
        { line_class: 'cost', scope: 'file', sign: null, lines: 1, amount: -5, lines_without_amount: 0, reason: null },
      ]
    }],
    ['the not-testable list', (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes as unknown as Record<string, unknown>).not_testable = null
    }],
    ['the suggested classes', (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes as unknown as Record<string, unknown>).suggested_classes = null
    }],
    ['the headline', (report: ReturnType<typeof makeReport>) => {
      ;(report.layer_2_causes as unknown as Record<string, unknown>).headline = null
    }],
  ])('checks %s', async (_label, spoil) => {
    const report = makeReport()
    spoil(report)
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
      { from: 'predict', diagnosis: { tree: 'kept' }, ordersBasis: 'order_id' },
    )

    expect(result.ordersBasis).toBe('order_id')
    expect(steps).toEqual(['predict', 'report'])
    expect(fetchMock.mock.calls.map((call) => String(call[0]).split('/').pop())).toEqual(['predict', 'report'])
    expect(result.diagnosis).toEqual({ tree: 'kept' })
  })

  it('hands over the diagnosis and the order basis as soon as it has them, so a later failure can resume', async () => {
    stubSteps('predict')
    const onDiagnosis = vi.fn()
    const onOrdersBasis = vi.fn()

    await expect(
      runAnalysis('http://localhost:8000', 'run-1', { onStep: () => undefined, onDiagnosis, onOrdersBasis }),
    ).rejects.toThrow(ApiError)
    expect(onDiagnosis).toHaveBeenCalledWith({ tree: null, calendar: null })
    expect(onOrdersBasis).toHaveBeenCalledWith('lines')
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
