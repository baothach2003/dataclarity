// Review's sales breakdowns (the dashboard, Thach's D4; docs/DASHBOARD_DESIGN.md 5.4), on the Notice component
// (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`) with a Dropdown (`1:321`): the columns that will split
// sales, each removable, and the other eligible columns to add, at most two. Column names and values are the
// file's own text, shown as text; stage 1's line says where the suggestion came from.

import { describeError } from '../domain/errorCopy.ts'
import type { BreakdownState } from '../pages/useBreakdowns.ts'
import { MAX_BREAKDOWNS } from '../types/breakdowns.ts'
import { Notice } from './Notice.tsx'

const TITLE = 'Split sales by'
const ADD = 'Add a column to split sales by'

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
        {describeError(error).detail}
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
  if (question.eligible.length === 0) {
    return (
      <Notice tone="info" title={TITLE}>
        {question.message}
      </Notice>
    )
  }
  const others = question.eligible.filter((c) => !state.selected.includes(c.column))
  const full = state.selected.length >= MAX_BREAKDOWNS
  return (
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
  )
}
