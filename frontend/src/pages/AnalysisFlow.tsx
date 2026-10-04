// Results -> Analyzing -> Insights (docs/SPECS.md section 3; PROJECT_PLAN 6E): stages 2-5 run in order,
// the page shows which; a refusal stays on screen with its step until the user tries again - from that
// step, keeping what came before (the 6E1 review #7) - or goes back.

import { useCallback, useEffect, useRef, useState } from 'react'
import { runAnalysis } from '../api/analysis.ts'
import type { AnalysisResult, AnalysisResume } from '../api/analysis.ts'
import type { AnalysisStep } from '../domain/analysisSteps.ts'
import { InsightsAnalyzingPage } from './InsightsAnalyzingPage.tsx'
import { InsightsPage } from './InsightsPage.tsx'

interface AnalysisFlowProps {
  baseUrl: string
  runId: string
  filename: string
  // cleaning_report.json's rows out, the meta line's count.
  rows: number
  onBack: () => void
}

/** Where a retry picks up: the failed step, with the diagnosis when that step needs it. */
function resumeAt(step: AnalysisStep, diagnosis: unknown): AnalysisResume | undefined {
  if (step === 'diagnose') {
    return { from: 'diagnose' }
  }
  if (step === 'predict' || step === 'report') {
    return diagnosis === undefined ? { from: 'diagnose' } : { from: step, diagnosis }
  }
  return undefined
}

export function AnalysisFlow({ baseUrl, runId, filename, rows, onBack }: AnalysisFlowProps) {
  const [step, setStep] = useState<AnalysisStep>('analyze')
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const started = useRef(false)
  // What the last attempt reached: the step it was on and the diagnosis it got.
  const reached = useRef<{ step: AnalysisStep; diagnosis: unknown }>({ step: 'analyze', diagnosis: undefined })

  // Never aborted: the server runs a step to its end whatever the browser does, and refuses a second
  // one for the run while it does (INVALID_STATE step_in_progress).
  const start = useCallback(
    (resume?: AnalysisResume) => {
      setError(null)
      const progress = {
        onStep: (next: AnalysisStep) => {
          reached.current.step = next
          setStep(next)
        },
        onDiagnosis: (diagnosis: unknown) => {
          reached.current.diagnosis = diagnosis
        },
      }
      runAnalysis(baseUrl, runId, progress, resume).then(setResult, setError)
    },
    [baseUrl, runId],
  )

  // Once per mount: StrictMode runs effects twice in development, and a second run would be refused.
  useEffect(() => {
    if (!started.current) {
      started.current = true
      start()
    }
  }, [start])

  if (result !== null) {
    return <InsightsPage baseUrl={baseUrl} runId={runId} report={result.report} />
  }
  return (
    <InsightsAnalyzingPage
      filename={filename}
      rows={rows}
      step={step}
      error={error}
      onRetry={() => {
        start(resumeAt(reached.current.step, reached.current.diagnosis))
      }}
      onBack={onBack}
    />
  )
}
