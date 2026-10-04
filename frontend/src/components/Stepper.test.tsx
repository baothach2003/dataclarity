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
})
