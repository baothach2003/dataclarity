import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { IssueBadges } from './IssueBadges.tsx'

afterEach(() => {
  cleanup()
})

// PROJECT_PLAN 6B: issue examples are AI text of unknown shape - a real call
// returned the string "null". Rendered as given and escaped (SEC-3), never
// read as row references or as markup.
describe('IssueBadges', () => {
  it('shows the examples exactly as given, as text', () => {
    render(
      <IssueBadges
        canonicalField="unit_price"
        issues={[{ code: 'missing_values', count: 2, pct: 2, examples: ['null', '<b>12</b>', 'row 7?'] }]}
      />,
    )

    const badge = screen.getByText(/· 2/)
    expect(badge.getAttribute('title')).toBe('Examples: "null", "<b>12</b>", "row 7?"')
    expect(document.querySelector('b')).toBeNull()
  })

  // The 6A-6D review (S7): joined with ", " alone, ["1,000", "2,500"] read as
  // four values.
  it('keeps examples that contain commas apart', () => {
    render(
      <IssueBadges
        canonicalField="unit_price"
        issues={[{ code: 'missing_values', count: 2, pct: 2, examples: ['1,000', '2,500'] }]}
      />,
    )

    expect(screen.getByText(/· 2/).getAttribute('title')).toBe('Examples: "1,000", "2,500"')
  })

  it('shows no hover text when there is no example', () => {
    render(
      <IssueBadges canonicalField="unit_price" issues={[{ code: 'missing_values', count: 2, pct: 2, examples: [] }]} />,
    )

    expect(screen.getByText(/· 2/).getAttribute('title')).toBeNull()
  })
})
