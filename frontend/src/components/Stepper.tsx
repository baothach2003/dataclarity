// The 5-stage header (docs/FIGMA_DESIGN_NOTES.md frame `Upload` node 7:851 and
// every screen after it). Stage 1 screens say how far Collect is; the analysis
// (6E) says how many stages are done and which one runs.

import { CheckIcon, LoaderIcon } from './Icon.tsx'

const STAGES = ['Collect', 'Analyze', 'Diagnose', 'Predict', 'Report'] as const

export type CollectStatus = 'active' | 'done'

export interface StageProgress {
  // Stages 0..done-1 are done; `active` is the one running or shown.
  done: number
  active: number | null
}

// One or the other, never neither (the 6E1 review #19): a screen always says where it is.
type StepperProps = { collectStatus: CollectStatus; progress?: never } | { progress: StageProgress; collectStatus?: never }

function progressOf(props: StepperProps): StageProgress {
  if (props.progress) {
    return props.progress
  }
  return props.collectStatus === 'done' ? { done: 1, active: null } : { done: 0, active: 0 }
}

export function Stepper(props: StepperProps) {
  const { done: doneCount, active: activeIndex } = progressOf(props)
  return (
    <header className="app-header">
      <span className="app-brand">DataClarity</span>
      <ol className="stepper" aria-label="Pipeline progress">
        {STAGES.map((name, index) => {
          const active = index === activeIndex
          const done = !active && index < doneCount
          return (
            <li
              key={name}
              className="stepper__step"
              aria-current={active ? 'step' : undefined}
            >
              <span
                className={
                  'stepper__badge' +
                  (done ? ' stepper__badge--done' : '') +
                  (active ? ' stepper__badge--active' : '')
                }
              >
                {done ? <CheckIcon /> : active ? <LoaderIcon /> : index + 1}
              </span>
              <span className={active || done ? 'stepper__label' : 'stepper__label stepper__label--pending'}>
                {name}
              </span>
              {index < STAGES.length - 1 && (
                <span className={'stepper__connector' + (done ? ' stepper__connector--done' : '')} />
              )}
            </li>
          )
        })}
      </ol>
    </header>
  )
}
