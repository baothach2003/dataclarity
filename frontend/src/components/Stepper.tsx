// The 5-stage header (docs/FIGMA_DESIGN_NOTES.md frame `Upload` node 7:851 and
// every screen after it). Only Collect (stage 1) is reachable in this build
// (Phase 2-5 do not exist yet), so the other four stages are always pending.

import { CheckIcon, LoaderIcon } from './Icon.tsx'

const STAGES = ['Collect', 'Analyze', 'Diagnose', 'Predict', 'Report'] as const

export type CollectStatus = 'active' | 'done'

interface StepperProps {
  collectStatus: CollectStatus
}

export function Stepper({ collectStatus }: StepperProps) {
  return (
    <header className="app-header">
      <span className="app-brand">CleanStock</span>
      <ol className="stepper" aria-label="Pipeline progress">
        {STAGES.map((name, index) => {
          const isCollect = index === 0
          const done = isCollect && collectStatus === 'done'
          const active = isCollect && collectStatus === 'active'
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
