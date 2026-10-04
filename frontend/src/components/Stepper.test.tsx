import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Stepper } from './Stepper.tsx'

afterEach(() => {
  cleanup()
})

// The design gap review's GLOBAL CHANGE: the frames say "CleanStock"; the
// repo, README and report say DataClarity.
describe('Stepper', () => {
  it('names the product DataClarity', () => {
    render(<Stepper collectStatus="active" />)
    expect(screen.getByText('DataClarity')).toBeDefined()
    expect(screen.queryByText('CleanStock')).toBeNull()
  })

  // 6E: stages 2-5 run after Results - the stages done, and the one running.
  it('marks the stages done and the one in progress', () => {
    render(<Stepper progress={{ done: 2, active: 2 }} />)
    const steps = screen.getAllByRole('listitem')

    expect(steps.map((step) => step.querySelector('.stepper__badge--done') !== null)).toEqual([true, true, false, false, false])
    expect(steps.map((step) => step.getAttribute('aria-current'))).toEqual([null, null, 'step', null, null])
  })
})
