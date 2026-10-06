// Review's currency question (the report redesign's step 5; design 6.2 and 6.3), on the Notice component
// (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`). Always asked (D6): shown while stage 1 reads the file;
// a currency found is pre-selected with where it was found; otherwise "Not stated" - never assumed. More than
// one currency is stage 1's block, worded by stage 1: no answer is offered, the file cannot run (Q7 = A). Every
// sentence here with a count is stage 1's; the file's own text (evidence, hint) is shown as text, never markup.

import { describeError } from '../domain/errorCopy.ts'
import type { CurrencyState } from '../pages/useCurrencyQuestion.ts'
import { NOT_STATED } from '../types/currency.ts'
import { Notice } from './Notice.tsx'

const TITLE = 'Which currency are the amounts in?'

export function CurrencyNotice({ state }: { state: CurrencyState }) {
  const { question, error } = state
  if (error !== null) {
    const copy = describeError(error)
    return (
      <Notice
        tone="warning"
        title="The file's currency could not be read"
        actions={
          <button type="button" className="button button--secondary" onClick={state.retry}>
            Ask again
          </button>
        }
      >
        {copy.detail}
      </Notice>
    )
  }
  if (question === null) {
    return state.loading ? (
      <Notice tone="info" title={TITLE}>
        Reading the file&apos;s currency…
      </Notice>
    ) : null
  }
  if (question.blocked !== null) {
    return (
      <Notice tone="error" title="More than one currency">
        {question.blocked}
      </Notice>
    )
  }
  const { finding } = question
  // A sign several currencies share ($, ¥): where it is, and why its family comes first (step 5's review).
  const narrowed =
    finding.kind !== 'narrowed'
      ? null
      : finding.evidence
        ? `The sign in your file (${finding.evidence}) is used by several currencies; those are listed first.`
        : 'The sign in your file is used by several currencies; those are listed first.'
  const lines = [
    finding.kind === 'found' && finding.evidence ? `Found in your file: ${finding.evidence}` : null,
    narrowed,
    question.hint,
    question.unreadable,
    finding.kind === 'found'
      ? null
      : "Left as \"Not stated\", amounts are shown without a currency code and the report says they are in your file's currency.",
  ].filter((line): line is string => line !== null)
  return (
    <Notice
      tone="info"
      title={TITLE}
      actions={
        <select
          className="select"
          aria-label={TITLE}
          value={state.selected ?? NOT_STATED}
          onChange={(event) => {
            state.choose(event.target.value)
          }}
        >
          <option value={NOT_STATED}>Not stated</option>
          {question.options.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      }
    >
      {lines.map((line) => (
        <span className="notice__line" key={line}>
          {line}
        </span>
      ))}
    </Notice>
  )
}
