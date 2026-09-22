// The "Analyzing" state after upload (docs/SPECS.md section 3 step 2;
// design/mockups/Upload - Analyzing.png): a 3-step indicator while
// POST /analyze-schema then POST /plan run in sequence. Profiling happens
// inside analyze-schema itself (no separate endpoint call), so steps 1 and 2
// both complete when that single call returns.

import { CheckIcon, LoaderIcon } from '../components/Icon.tsx'
import { Stepper } from '../components/Stepper.tsx'

export type AnalyzingStep = 'profiling' | 'schema' | 'plan'

const STEPS: { key: AnalyzingStep; label: string }[] = [
  { key: 'profiling', label: 'Profiling data' },
  { key: 'schema', label: 'Inferring schema' },
  { key: 'plan', label: 'Drafting cleaning plan' },
]

interface AnalyzingPageProps {
  filename: string
  rows: number | undefined
  columns: number | undefined
  step: AnalyzingStep
}

export function AnalyzingPage({ filename, rows, columns, step }: AnalyzingPageProps) {
  const activeIndex = STEPS.findIndex((s) => s.key === step)
  return (
    <div className="app-shell">
      <Stepper collectStatus="active" />
      <div className="page">
        <div className="card analyzing-card">
          <h1 className="page__title">Preparing your cleaning plan</h1>
          <p className="analyzing-card__meta">
            {filename}
            {rows !== undefined && columns !== undefined && (
              <>
                {' '}
                · {rows.toLocaleString()} rows · {columns.toLocaleString()} columns
              </>
            )}
          </p>
          <ol className="analyzing-steps">
            {STEPS.map((s, index) => {
              const status = index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending'
              return (
                <li key={s.key} className={`analyzing-step analyzing-step--${status}`}>
                  <span className="analyzing-step__badge">
                    {status === 'done' ? <CheckIcon /> : status === 'active' ? <LoaderIcon /> : index + 1}
                  </span>
                  <span>{s.label}</span>
                </li>
              )
            })}
          </ol>
          <p className="analyzing-card__footnote">
            Usually under 30 seconds. Nothing is changed until you confirm the plan.
          </p>
        </div>
      </div>
    </div>
  )
}
