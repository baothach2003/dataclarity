import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { NO_AI_RECOMMENDATIONS, RecommendationsSection } from './RecommendationsSection.tsx'

afterEach(() => {
  cleanup()
})

// The design gap review: the recommendation cards are REMOVED and an info
// Notice stands in their place (ADD 14). No AI writes a recommendation in v1
// (the report redesign's step 4, Thach's option (d)); an older report's free
// text is shown nowhere (Q42).
describe('RecommendationsSection', () => {
  it('says no AI writes recommendations - no cards', () => {
    render(<RecommendationsSection />)

    expect(screen.getByRole('heading', { name: 'Recommendations' })).toBeDefined()
    expect(screen.getByText(NO_AI_RECOMMENDATIONS)).toBeDefined()
    expect(screen.queryByText(/switched off/)).toBeNull()
    expect(screen.queryByRole('list')).toBeNull()
  })
})
