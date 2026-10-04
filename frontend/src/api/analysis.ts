// Stages 2-5 as the Insights flow drives them (docs/SPECS.md section 8): analyze, diagnose, predict,
// report - each POST only after the one before succeeded, since each reads the file the one before
// wrote. Stage 4 asks no AI in v1 (STRATEGY_AI_ENABLED false) and stages 2, 3 and 5 never do.

import type { AnalysisStep } from '../domain/analysisSteps.ts'
import type { ReportContract } from '../types/report.ts'
import { throwApiError, UnreachableError } from './errors.ts'
import { postJson, trimSlash } from './http.ts'

export type { AnalysisStep } from '../domain/analysisSteps.ts'

// metrics.json's core.orders_basis (a CONTRACTS 11 FE field): the lever's factors are named by it.
export type OrdersBasis = 'order_id' | 'lines' | null

export interface AnalysisResult {
  report: ReportContract
  // diagnosis.json as the diagnose answer carries it; the Insights page reads only the fields CONTRACTS
  // 11 lists for FE.
  diagnosis: unknown
  ordersBasis: OrdersBasis
}

export interface AnalysisProgress {
  // Each step, before it starts.
  onStep: (step: AnalysisStep) => void
  // What the earlier steps gave, as soon as it is in hand, so a later failure can resume after them.
  onOrdersBasis?: (basis: OrdersBasis) => void
  onDiagnosis?: (diagnosis: unknown) => void
}

/** Where to pick up after a failure: predict and report need the diagnosis already in hand. */
export type AnalysisResume =
  | { from: 'diagnose'; ordersBasis?: OrdersBasis }
  | { from: 'predict' | 'report'; diagnosis: unknown; ordersBasis?: OrdersBasis }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function field(body: unknown, key: string): unknown {
  if (!isRecord(body) || !isRecord(body[key])) {
    throw new UnreachableError('unexpected response body')
  }
  return body[key]
}

function ordersBasisOf(metrics: unknown): OrdersBasis {
  const core = isRecord(metrics) ? metrics.core : undefined
  const basis = isRecord(core) ? core.orders_basis : undefined
  return basis === 'order_id' || basis === 'lines' ? basis : null
}

function listOf(value: unknown, item: (entry: unknown) => boolean = () => true): boolean {
  return Array.isArray(value) && value.every(item)
}

/** The report body checked, not trusted: the layers and every list the page walks. */
function reportOf(body: unknown): ReportContract {
  const report = field(body, 'report') as Record<string, unknown>
  const numbers = report.layer_1_numbers
  const causes = report.layer_2_causes
  const trust = isRecord(numbers) ? numbers.trust : undefined
  const provenance = report.provenance
  const ok =
    isRecord(numbers) &&
    isRecord(numbers.period) &&
    listOf(numbers.kpis, (kpi) => isRecord(kpi) && listOf(kpi.notes)) &&
    listOf(numbers.notes, (note) => isRecord(note) && listOf(note.measures)) &&
    listOf(numbers.how_to_read, (note) => isRecord(note) && listOf(note.measures)) &&
    listOf(numbers.outside_revenue, (row) => isRecord(row) && typeof row.reason === 'string') &&
    isRecord(trust) &&
    listOf(trust.checks, isRecord) &&
    listOf(trust.limitations) &&
    isRecord(causes) &&
    listOf(causes.notes, (note) => isRecord(note) && listOf(note.measures)) &&
    isRecord(causes.headline) &&
    typeof causes.headline.message === 'string' &&
    listOf(
      causes.hypotheses,
      (hypothesis) =>
        isRecord(hypothesis) &&
        isRecord(hypothesis.evidence) &&
        typeof hypothesis.lens === 'string' &&
        typeof hypothesis.moved_against === 'boolean' &&
        typeof hypothesis.verdict_label === 'string' &&
        listOf(hypothesis.evidence_text, (line) => typeof line === 'string'),
    ) &&
    listOf(causes.not_testable, isRecord) &&
    isRecord(causes.suggested_classes) &&
    (causes.narration === null || (isRecord(causes.narration) && listOf(causes.narration.hypothesis_notes, isRecord))) &&
    isRecord(report.layer_3_actions) &&
    listOf(report.charts, isRecord) &&
    isRecord(report.data_quality) &&
    isRecord(provenance) &&
    listOf(provenance.stages_run) &&
    listOf(provenance.models_used) &&
    typeof report.source_file === 'string'
  if (!ok) {
    throw new UnreachableError('unexpected response body')
  }
  return report as unknown as ReportContract
}

/** Runs stages 2-5 in order - or from `resume.from` on - telling `progress` each step before it starts;
 * the first refusal is thrown as it came (an ApiError) and no later step is called. Resuming after the
 * diagnosis keeps analyze and diagnose, and their later outputs, as they are (the 6E1 review #7). */
export async function runAnalysis(
  baseUrl: string,
  runId: string,
  progress: AnalysisProgress,
  resume?: AnalysisResume,
): Promise<AnalysisResult> {
  const path = (step: AnalysisStep) => `/api/runs/${runId}/${step}`
  const from = resume?.from ?? 'analyze'
  let diagnosis = resume && 'diagnosis' in resume ? resume.diagnosis : undefined
  let ordersBasis: OrdersBasis = resume?.ordersBasis ?? null
  if (from === 'analyze') {
    progress.onStep('analyze')
    ordersBasis = ordersBasisOf(field(await postJson<unknown>(baseUrl, path('analyze'), undefined), 'metrics'))
    progress.onOrdersBasis?.(ordersBasis)
  }
  if (from === 'analyze' || from === 'diagnose') {
    progress.onStep('diagnose')
    diagnosis = field(await postJson<unknown>(baseUrl, path('diagnose'), undefined), 'diagnosis')
    progress.onDiagnosis?.(diagnosis)
  }
  if (from !== 'report') {
    progress.onStep('predict')
    field(await postJson<unknown>(baseUrl, path('predict'), undefined), 'forecast')
  }
  progress.onStep('report')
  const report = reportOf(await postJson<unknown>(baseUrl, path('report'), undefined))
  return { report, diagnosis, ordersBasis }
}

/** GET /api/runs/{id}/download/report.html as a Blob the caller saves (errors still come back as the
 * JSON envelope). */
export async function downloadReportHtml(baseUrl: string, runId: string): Promise<Blob> {
  const response = await fetch(`${trimSlash(baseUrl)}/api/runs/${runId}/download/report.html`)
  if (!response.ok) {
    await throwApiError(response)
  }
  return response.blob()
}
