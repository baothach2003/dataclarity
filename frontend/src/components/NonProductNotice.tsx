// The Review screen's question about lines that may not be products (session
// 2E-d2, Thach): postage, fees, discounts, accounting adjustments. Built on
// the Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`)
// with one choice per candidate below it. Nothing is chosen for the user: a
// suggestion is only shown, and unanswered lines stay products.

import { Notice } from './Notice.tsx'
import type { LineCandidate } from '../domain/lineClasses.ts'
import type { LineClass } from '../types/contracts.ts'

type Choice = LineClass | 'product'

// Each choice, and what it does to the lines.
const CHOICES: { value: Choice; label: string }[] = [
  { value: 'product', label: 'A product' },
  { value: 'charge', label: 'A charge paid by the customer (stays in revenue)' },
  { value: 'discount', label: 'A discount (stays in revenue)' },
  { value: 'cost', label: 'A fee or cost (leaves revenue)' },
  { value: 'adjustment', label: 'An accounting adjustment (leaves revenue)' },
]

const SUGGESTIONS: Record<LineClass, string> = {
  charge: 'a charge paid by the customer',
  discount: 'a discount',
  cost: 'a fee or cost',
  adjustment: 'an accounting adjustment',
}

const MONEY = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

interface NonProductNoticeProps {
  candidates: LineCandidate[]
  // The answer that applies to each candidate, by its key.
  answers: ReadonlyMap<string, Choice>
  onAnswer: (candidate: LineCandidate, choice: Choice | null) => void
}

function describe(candidate: LineCandidate): string {
  const named = candidate.name !== null && candidate.name !== candidate.value ? ` (${candidate.name})` : ''
  const lines = `${candidate.lines.toLocaleString('en-US')} ${candidate.lines === 1 ? 'line' : 'lines'}`
  // Both signs, never only the net: M "Manual" on Online Retail II hides
  // +341,104.90 of positive lines inside a net of -82,781.27.
  const money =
    candidate.positive === null || candidate.negative === null
      ? ''
      : `, +${MONEY.format(candidate.positive)} and ${MONEY.format(candidate.negative)}`
  const suggestion = candidate.suggested === null ? 'no suggestion' : `suggested: ${SUGGESTIONS[candidate.suggested]}`
  return `"${candidate.value}"${named}: ${lines}${money} - ${suggestion}`
}

function parseChoice(value: string): Choice | null {
  return CHOICES.find((choice) => choice.value === value)?.value ?? null
}

export function NonProductNotice({ candidates, answers, onAnswer }: NonProductNoticeProps) {
  if (candidates.length === 0) {
    return null
  }
  return (
    <div className="line-classes">
      <Notice tone="warning" title="Lines that may not be products">
        Postage, fees, discounts and accounting adjustments are often booked as products. Say what each of these is;
        unanswered, its lines stay products.
      </Notice>
      <ul className="line-classes__list">
        {candidates.map((candidate) => (
          <li key={candidate.key} className="line-classes__row">
            <span>{describe(candidate)}</span>
            <select
              className="select"
              aria-label={`What is "${candidate.value}"?`}
              value={answers.get(candidate.key) ?? ''}
              onChange={(event) => {
                onAnswer(candidate, parseChoice(event.target.value))
              }}
            >
              <option value="">Not answered</option>
              {CHOICES.map((choice) => (
                <option key={choice.value} value={choice.value}>
                  {choice.label}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
    </div>
  )
}
