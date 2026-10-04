import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, UnreachableError } from '../api/errors.ts'
import { InsightsAnalyzingPage } from './InsightsAnalyzingPage.tsx'

afterEach(() => {
  cleanup()
})

function analysisSteps() {
  return screen.getAllByRole('listitem').filter((item) => item.classList.contains('analyzing-step'))
}

// Frame "Insights - Analyzing" (7:1032) with the design gap review's CHANGE: a
// fourth step, the report, is built in v1. Its footnote's "the AI only
// proposes explanations" and "usually under a minute" are not true of v1 (no
// AI is asked in stages 2-5; no time was measured, and a step can wait for a
// slot whatever the file's size), so neither is said.
describe('InsightsAnalyzingPage', () => {
  it('shows the four steps, those done and the one running', () => {
    render(<InsightsAnalyzingPage filename="sales.csv" rows={12301} step="predict" error={null} onRetry={vi.fn()} onBack={vi.fn()} />)

    expect(screen.getByRole('heading', { name: 'Building your insights' })).toBeDefined()
    expect(screen.getByText('sales.csv · 12,301 rows')).toBeDefined()
    expect(analysisSteps().map((step) => step.lastElementChild?.textContent)).toEqual([
      'Computing metrics',
      'Diagnosing causes',
      'Forecasting',
      'Building the report',
    ])
    expect(analysisSteps().map((step) => step.className.replace('analyzing-step ', ''))).toEqual([
      'analyzing-step--done',
      'analyzing-step--done',
      'analyzing-step--active',
      'analyzing-step--pending',
    ])
    expect(screen.getByText('Every figure is computed from your data. A large file takes longer.')).toBeDefined()
    expect(screen.queryByText(/AI/)).toBeNull()
  })

  it('counts one row as one', () => {
    render(<InsightsAnalyzingPage filename="one.csv" rows={1} step="analyze" error={null} onRetry={vi.fn()} onBack={vi.fn()} />)

    expect(screen.getByText('one.csv · 1 row')).toBeDefined()
  })

  // The 6E1 review (#6, #7): nothing spins once a step failed, and "Try again"
  // is offered only where trying again can help.
  it('says why a step failed with nothing left spinning, and offers only to go back when retrying cannot help', () => {
    const onBack = vi.fn()
    const error = new ApiError('ANALYSIS_FAILED', "cleaned.csv has no column mapped to 'unit_price'", { canonical_field: 'unit_price' })
    render(<InsightsAnalyzingPage filename="sales.csv" rows={12301} step="analyze" error={error} onRetry={vi.fn()} onBack={onBack} />)

    expect(screen.getByRole('alert').textContent).toContain('No column was mapped as the unit price')
    expect(analysisSteps()[0]?.className).toBe('analyzing-step analyzing-step--failed')
    expect(document.querySelector('.stepper [aria-current]')).toBeNull()
    expect(document.querySelector('.icon-spin')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Back to results' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['a lost connection', new UnreachableError('the server could not be reached')],
    ['a server error', new ApiError('INTERNAL_ERROR', 'boom')],
    ['a step still running', new ApiError('INVALID_STATE', 'Wait for it to finish.', { reason: 'step_in_progress' })],
  ])('offers to try again after %s', (_label, error) => {
    const onRetry = vi.fn()
    render(<InsightsAnalyzingPage filename="sales.csv" rows={12301} step="report" error={error} onRetry={onRetry} onBack={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('offers no retry for a run whose files are gone', () => {
    render(
      <InsightsAnalyzingPage
        filename="sales.csv"
        rows={12301}
        step="analyze"
        error={new ApiError('EXPIRED', "The run's files are gone.")}
        onRetry={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })
})
