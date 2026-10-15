// Review's sales breakdowns (the dashboard, Thach's D4; docs/DASHBOARD_DESIGN.md 5.4), on the Notice component
// (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`) with a Dropdown (`1:321`): the columns that will split
// sales, each removable, and the other eligible columns to add, at most two. Column names and values are the
// file's own text, shown as text; stage 1's line says where the suggestion came from. Thach's Q7 (2026-10-16): stage
// 1's question for each column written on each order's first line only, answered Yes or No (unanswered: not offered).

import { describeError } from '../domain/errorCopy.ts'
import type { BreakdownState } from '../pages/useBreakdowns.ts'
import type { WholeOrderQuestion } from '../types/breakdowns.ts'
import { MAX_BREAKDOWNS } from '../types/breakdowns.ts'
import { Notice } from './Notice.tsx'

const TITLE = 'Split sales by'
const ADD = 'Add a column to split sales by'

/** Each Q7 question as stage 1 words it: Yes / No, or the answer given with a way to change it. The answer shown
 * is the page's own until stage 1 has measured it, so a click is seen at once. */
function WholeOrderQuestions({ state, asked }: { state: BreakdownState; asked: WholeOrderQuestion[] }) {
  return (
    <>
      {asked.map((q) => {
        const answer = q.column in state.wholeOrder ? state.wholeOrder[q.column] : q.answer
        return (
          <Notice
            key={q.column}
            tone={answer === null ? 'warning' : 'info'}
            title={q.question}
            actions={
              answer === null ? (
                <>
                  <button type="button" className="button button--secondary" onClick={() => { state.answer(q.column, true) }}>
                    Yes, the whole order
                  </button>
                  <button type="button" className="link-button" onClick={() => { state.answer(q.column, false) }}>
                    No
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="link-button"
                  aria-label={`Change the answer for ${q.column}`}
                  onClick={() => { state.answer(q.column, null) }}
                >
                  Change
                </button>
              )
            }
          >
            {answer === null
              ? 'If it does, every line of an order is counted under the value on its first line; if not, or until you answer, sales are not split by it.'
              : answer
                ? 'Every line of an order is counted under the value on its first line.'
                : 'Sales are not split by it.'}
          </Notice>
        )
      })}
    </>
  )
}

export function BreakdownNotice({ state }: { state: BreakdownState }) {
  const { question, error } = state
  if (error !== null) {
    return (
      <Notice
        tone="warning"
        title="The columns to split sales by could not be read"
        actions={
          <button type="button" className="button button--secondary" onClick={state.retry}>
            Ask again
          </button>
        }
      >
        {describeError(error).detail} If you confirm now, sales are not split by any column.
      </Notice>
    )
  }
  if (question === null) {
    return state.loading ? (
      // Confirm is never held for it (design 5.2): confirming now splits sales by no column, and the page says so
      // rather than leave out unseen a suggestion that arrives later (the step 4 review #6).
      <Notice tone="info" title={TITLE}>
        Looking at your file&apos;s columns… If you confirm now, sales are not split by any column.
      </Notice>
    ) : null
  }
  const asked = question.whole_order ?? []
  if (question.eligible.length === 0) {
    return (
      <>
        <Notice tone="info" title={TITLE}>
          {question.message}
        </Notice>
        <WholeOrderQuestions state={state} asked={asked} />
      </>
    )
  }
  const others = question.eligible.filter((c) => !state.selected.includes(c.column))
  const full = state.selected.length >= MAX_BREAKDOWNS
  return (
    <>
      <Notice
        tone="info"
        title={TITLE}
        actions={
          <select
            className="select"
            aria-label={ADD}
            value=""
            disabled={full || others.length === 0}
            onChange={(event) => {
              state.add(event.target.value)
            }}
          >
            <option value="">{full ? `At most ${String(MAX_BREAKDOWNS)} columns` : 'Add a column'}</option>
            {others.map((c) => (
              <option key={c.column} value={c.column}>
                {c.column}
              </option>
            ))}
          </select>
        }
      >
        <span className="notice__line">{question.message}</span>
        {state.stale && (
          // The doubt review's R1: an edit is being measured; what is selected stays, and is checked again.
          <span className="notice__line">
            Checking the columns again for your edits… If you confirm now, the columns selected are checked again when
            the file is cleaned.
          </span>
        )}
        {state.selected.length === 0 ? (
          <span className="notice__line">Sales will not be split by any column.</span>
        ) : (
          state.selected.map((column) => {
            const values = question.eligible.find((c) => c.column === column)?.values ?? []
            return (
              <span className="notice__line" key={column}>
                <strong>{column}</strong>
                {values.length > 0 ? ` (${values.join(', ')})` : ''}{' '}
                <button
                  type="button"
                  className="button button--ghost"
                  aria-label={`Remove ${column}`}
                  onClick={() => {
                    state.remove(column)
                  }}
                >
                  Remove
                </button>
              </span>
            )
          })
        )}
      </Notice>
      <WholeOrderQuestions state={state} asked={asked} />
    </>
  )
}
