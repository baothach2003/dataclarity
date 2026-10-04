// The analysis in progress (docs/FIGMA_DESIGN_NOTES.md frame "Insights - Analyzing", node 7:1032; the
// design gap review's CHANGE: a fourth step, the report, is built in v1). The frame's footnote is not
// true of v1 - no AI is asked in stages 2-5, no time was measured, and a step can wait for a free slot
// whatever the file's size - so this one says only what is.

import { ApiError } from '../api/errors.ts'
import { ANALYSIS_STEPS } from '../domain/analysisSteps.ts'
import type { AnalysisStep } from '../domain/analysisSteps.ts'
import { CheckIcon, LoaderIcon, XCircleIcon } from '../components/Icon.tsx'
import { Notice } from '../components/Notice.tsx'
import { Stepper } from '../components/Stepper.tsx'
import { describeError } from '../domain/errorCopy.ts'
import { count } from '../domain/reportFormat.ts'

const LABELS: Record<AnalysisStep, string> = {
  analyze: 'Computing metrics',
  diagnose: 'Diagnosing causes',
  predict: 'Forecasting',
  report: 'Building the report',
}

/** Whether trying again can help: never for a refusal the run's data or files decide - a field not
 * mapped, not sales data, amounts too large, line classes changed (ANALYSIS_FAILED), files gone
 * (EXPIRED), a request the server cannot read (INVALID_REQUEST, NOT_FOUND) - the 6E1 review #7. */
function retryHelps(error: unknown): boolean {
  return !(error instanceof ApiError && ['ANALYSIS_FAILED', 'EXPIRED', 'INVALID_REQUEST', 'NOT_FOUND'].includes(error.code))
}

interface InsightsAnalyzingPageProps {
  filename: string
  rows: number
  step: AnalysisStep
  // The refusal that stopped `step`; null while it runs.
  error: unknown
  onRetry: () => void
  onBack: () => void
}

export function InsightsAnalyzingPage({ filename, rows, step, error, onRetry, onBack }: InsightsAnalyzingPageProps) {
  const activeIndex = ANALYSIS_STEPS.indexOf(step)
  const failed = error !== null
  const copy = failed ? describeError(error) : null
  return (
    <div className="app-shell">
      {/* Stages 2-5 are header stages 1-4: Collect is done. Nothing spins once a step failed. */}
      <Stepper progress={{ done: activeIndex + 1, active: failed ? null : activeIndex + 1 }} />
      <div className="page">
        <div className="card analyzing-card">
          <h1 className="page__title">Building your insights</h1>
          <p className="analyzing-card__meta">
            {filename} · {count(rows)} {rows === 1 ? 'row' : 'rows'}
          </p>
          <ol className="analyzing-steps">
            {ANALYSIS_STEPS.map((key, index) => {
              const status =
                index < activeIndex ? 'done' : index === activeIndex ? (failed ? 'failed' : 'active') : 'pending'
              return (
                <li key={key} className={`analyzing-step analyzing-step--${status}`}>
                  <span className="analyzing-step__badge">
                    {status === 'done' ? (
                      <CheckIcon />
                    ) : status === 'active' ? (
                      <LoaderIcon />
                    ) : status === 'failed' ? (
                      <XCircleIcon />
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span>{LABELS[key]}</span>
                </li>
              )
            })}
          </ol>
          <p className="analyzing-card__footnote">
            Every figure is computed from your data. A large file takes longer.
          </p>
        </div>
        {copy && (
          <Notice
            tone="error"
            title={copy.title}
            actions={
              <>
                <button type="button" className="button button--secondary" onClick={onBack}>
                  Back to results
                </button>
                {retryHelps(error) && (
                  <button type="button" className="button button--primary" onClick={onRetry}>
                    Try again
                  </button>
                )}
              </>
            }
          >
            {copy.detail}
          </Notice>
        )}
      </div>
    </div>
  )
}
