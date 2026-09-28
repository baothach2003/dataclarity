// Review's whole-file view of the line taxonomy (session 2E-t3;
// docs/LINE_TAXONOMY.md section 5): the revenue identity for the answers as
// they stand, the lines outside revenue beside it, the lines no rule placed or
// could measure, and the notes the data cannot fully tell apart (CLAUDE.md
// 3.3a). Built on the Notice component (docs/FIGMA_DESIGN_NOTES.md section 5,
// node `1:271`) with its lines below it, as the line-class question is. Every
// figure is stage 1's; nothing here computes one. And the source columns the
// run will write under another name (Thach's Q24).

import { Notice } from './Notice.tsx'
import { ApiError } from '../api/errors.ts'
import { describeError } from '../domain/errorCopy.ts'
import {
  count,
  identityCaveats,
  identityLine,
  measureLine,
  outsideRevenueLines,
  renameLine,
  unclassifiedLine,
  unmeasurableLine,
} from '../domain/lineSummary.ts'
import type { LineSummary } from '../types/lineSummary.ts'
import type { LineSummaryState } from '../pages/useLineSummary.ts'

const TITLE = 'The whole file, as your answers stand'

function SummaryLines({ summary }: { summary: LineSummary }) {
  const outside = outsideRevenueLines(summary.outside_revenue)
  const unmeasurable = unmeasurableLine(summary.unmeasurable)
  const unclassified = unclassifiedLine(summary.unclassified)
  return (
    <ul className="line-summary__list">
      {identityCaveats(summary).map((caveat) => (
        <li key={caveat}>{caveat}</li>
      ))}
      {outside.length > 0 && <li>Outside revenue, reported apart: {outside.join('; ')}.</li>}
      {unmeasurable !== null && <li>{unmeasurable}</li>}
      {unclassified !== null && <li>{unclassified}</li>}
      {summary.notes.map((note) => (
        <li key={note.code}>
          {note.text}
          {note.measures.length > 0 && ` ${note.measures.map((measure) => measureLine(note, measure)).join('; ')}.`}
        </li>
      ))}
    </ul>
  )
}

function title(state: LineSummaryState): string {
  if (state.loading) {
    return `${TITLE} (updating…)`
  }
  return state.stale ? `${TITLE} (before your latest changes)` : TITLE
}

function errorText(error: unknown): string {
  // A second ask while the first still runs is refused (409): waiting helps,
  // reloading does not (review 2 #6).
  if (error instanceof ApiError && error.code === 'INVALID_STATE' && error.details?.reason === 'summary_in_progress') {
    return 'The whole file is still being added up from an earlier request. Try again in a moment.'
  }
  return describeError(error).detail
}

export function LineSummaryNotice({ state }: { state: LineSummaryState }) {
  const { response, loading, stale, error, refresh } = state
  const again =
    !loading && (stale || error !== null) ? (
      <button type="button" className="button button--secondary" onClick={refresh}>
        {error !== null ? 'Try again' : 'Add up again'}
      </button>
    ) : undefined
  const renames = response?.reserved_renames ?? []
  const summary = response?.summary ?? null
  // Shown from the last answer: marked whenever it may not be the plan's now.
  const renameTitle = `Columns the cleaned file writes under another name${
    stale || loading || error !== null ? ' (as last checked)' : ''
  }`
  return (
    <>
      {renames.length > 0 && (
        <Notice tone="info" title={renameTitle}>
          {renames.map(renameLine).join(' ')}
        </Notice>
      )}
      <div className="line-summary">
        {error !== null && (
          <Notice tone="warning" title={`${TITLE}: not added up`} actions={again}>
            {errorText(error)}
          </Notice>
        )}
        {response === null ? (
          error === null && (
            <Notice tone="info" title={TITLE}>
              Adding up the whole file…
            </Notice>
          )
        ) : summary === null ? (
          <Notice tone="info" title={title(state)} actions={error === null ? again : undefined}>
            {response.summary_unavailable_reason}
          </Notice>
        ) : (
          <>
            <Notice tone="info" title={title(state)} actions={error === null ? again : undefined}>
              {identityLine(summary.identity)} - the plan keeps {count(summary.lines, 'line', 'lines')}.
            </Notice>
            <SummaryLines summary={summary} />
          </>
        )}
      </div>
    </>
  )
}
