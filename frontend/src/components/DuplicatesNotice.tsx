// The Review screen's exact copies (session 2E-u4, Thach, 2026-10-02), built
// on the Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node
// `1:271`), as every Review question is. The AI never proposes removing them:
// a copy cannot be told from a genuine repeat sale (CLAUDE.md 3.3a). The user
// may add the step; then the notice says what it takes - the lines and their
// revenue, as stage 1's whole-file summary counts them (nothing here computes
// a figure).

import { Notice } from './Notice.tsx'
import { count, money } from '../domain/lineSummary.ts'
import type { LineSummaryState } from '../pages/useLineSummary.ts'

interface DuplicatesNoticeProps {
  // profile.json's count of rows that are exact copies of an earlier one.
  duplicateRows: number
  removes: boolean
  summary: LineSummaryState
  onChange: (remove: boolean) => void
}

export function DuplicatesNotice({ duplicateRows, removes, summary, onChange }: DuplicatesNoticeProps) {
  if (duplicateRows === 0 && !removes) {
    return null
  }
  if (!removes) {
    return (
      <Notice
        tone="info"
        title={`${count(duplicateRows, 'row is an exact copy', 'rows are exact copies')} of another row`}
        actions={
          <button type="button" className="button button--secondary" onClick={() => { onChange(true) }}>
            Remove the copies
          </button>
        }
      >
        They are kept: a copy cannot be told from a genuine repeat sale (the same item rung up the same way). Remove
        them only if you know the export repeated lines.
      </Notice>
    )
  }
  const keep = (
    <button type="button" className="link-button" onClick={() => { onChange(false) }}>
      Keep them
    </button>
  )
  // The summary's figures only while they are this plan's.
  const removed = summary.stale || summary.loading ? null : (summary.response?.summary?.duplicates_removed ?? null)
  if (removed !== null) {
    return (
      <Notice
        tone="warning"
        title={`The plan removes ${count(removed.lines, 'line that is an exact copy', 'lines that are exact copies')}, holding ${money(removed.revenue)} of revenue`}
        actions={keep}
      >
        As counted in the whole file below.
      </Notice>
    )
  }
  return (
    <Notice
      tone="warning"
      title="The plan removes the exact copies"
      actions={keep}
    >
      Add up the whole file again to see how many lines and how much revenue they hold.
    </Notice>
  )
}
