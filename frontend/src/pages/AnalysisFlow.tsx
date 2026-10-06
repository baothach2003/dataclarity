// Results -> Analyzing -> Insights (docs/SPECS.md section 3; PROJECT_PLAN 6E): stages 2-5 run in order,
// the page shows which; a refusal stays on screen with its step until the user tries again - from that
// step, keeping what came before (the 6E1 review #7) - or goes back.

import { useCallback, useEffect, useRef, useState } from 'react'
import { runAnalysis } from '../api/analysis.ts'
import type { AnalysisResult, AnalysisResume, OrdersBasis } from '../api/analysis.ts'
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

interface Reached {
  step: AnalysisStep
  diagnosis: unknown
  ordersBasis: OrdersBasis | undefined
}

/** Where a retry picks up: the failed step, with what the earlier steps gave when it needs it. */
function resumeAt({ step, diagnosis, ordersBasis }: Reached): AnalysisResume | undefined {
  if (ordersBasis === undefined || step === 'analyze') {
    return undefined
  }
  if (step === 'predict' || step === 'report') {
    return diagnosis === undefined ? { from: 'diagnose', ordersBasis } : { from: step, diagnosis, ordersBasis }
  }
  return { from: 'diagnose', ordersBasis }
}

export function AnalysisFlow({ baseUrl, runId, filename, rows, onBack }: AnalysisFlowProps) {
  const [step, setStep] = useState<AnalysisStep>('analyze')
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const started = useRef(false)
  // What the last attempt reached: the step it was on and the diagnosis it got.
  const reached = useRef<Reached>({ step: 'analyze', diagnosis: undefined, ordersBasis: undefined })

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
        onOrdersBasis: (basis: OrdersBasis) => {
          reached.current.ordersBasis = basis
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
    return (
      <InsightsPage baseUrl={baseUrl} runId={runId} report={result.report} />
    )
  }
  return (
    <InsightsAnalyzingPage
      filename={filename}
      rows={rows}
      step={step}
      error={error}
      onRetry={() => {
        start(resumeAt(reached.current))
      }}
      onBack={onBack}
    />
  )
}
