import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { makeReport, SAME_DAY_TEXT } from '../pages/insightsFixture.ts'
import type { Actions } from '../types/report.ts'
import { RecommendationsSection } from './RecommendationsSection.tsx'

afterEach(() => {
  cleanup()
})

const REPORT = makeReport()
const ACTIONS = REPORT.layer_3_actions

function show(actions: Actions = ACTIONS) {
  return render(<RecommendationsSection actions={actions} notes={REPORT.layer_1_numbers.notes} period={REPORT.layer_1_numbers.period} />)
}

// The design gap review: the recommendation cards are REMOVED (stage 4's AI
// step is off in v1) and an info Notice says so in their place (ADD 14), in
// stage 5's words (html_report._actions). Shown only while the backend shows
// them; their notes beside them by construction (CONTRACTS 11).
describe('RecommendationsSection', () => {
  it('says the AI recommendations are switched off - no cards', () => {
    show()

    expect(screen.getByRole('heading', { name: 'Recommendations' })).toBeDefined()
    expect(screen.getByText('The AI recommendations are switched off for this report.')).toBeDefined()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('says none is available when the AI gave no answer', () => {
    show({ ...ACTIONS, recommendations_status: 'unavailable' })

    expect(screen.getByText('No AI recommendation is available for this run.')).toBeDefined()
  })

  it('says none is available when the AI gave an empty list', () => {
    show({ ...ACTIONS, recommendations_status: 'shown', recommendations: [], do_not_do: [] })

    expect(screen.getByText('No AI recommendation is available for this run.')).toBeDefined()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('lists them as written, with what not to do and every note beside them, when they are shown', () => {
    show({
      ...ACTIONS,
      recommendations_status: 'shown',
      recommendations: [
        {
          priority: 1,
          insight: '<b>128 customers</b> did not return.',
          cause: 'Fewer active customers.',
          action: 'Send a win-back offer.',
          expected_impact: 'Some of the lapsed customers return.',
          how_to_measure: 'Active customers after 4 weeks.',
          confidence_label: 'medium',
        },
      ],
      do_not_do: [{ tempting_action: 'Cut prices', why_wrong_here: 'Prices did not cause it.' }],
      notes: ['same_day_cancellations'],
    })

    expect(screen.getByText('Send a win-back offer.')).toBeDefined()
    expect(screen.getByText('Insight: <b>128 customers</b> did not return.')).toBeDefined()
    expect(document.querySelector('b')).toBeNull()
    expect(screen.getByText('Confidence: medium')).toBeDefined()
    expect(screen.getByText('Do not: Cut prices - Prices did not cause it.')).toBeDefined()
    expect(screen.getByText(SAME_DAY_TEXT)).toBeDefined()
  })
})
