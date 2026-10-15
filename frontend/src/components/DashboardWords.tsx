// Technical details' first part on Insights (Thach's layout, 2026-10-15; docs/DASHBOARD_DESIGN.md section 10):
// every sentence the dashboard leaves out of its rows - the front section whole (the summary, the data checks,
// the full checklist, what to do next with why and what to watch, next month, what this report cannot know),
// each chart's caption, each "not shown" line. Nothing is deleted; report.html prints the same
// (html_dashboard.words_html). Every sentence is stage 5's own.

import type { NoteCode } from '../types/report.ts'
import type { Dashboard } from '../types/reportDashboard.ts'
import type { Front } from '../types/reportFront.ts'
import {
  FrontCannotKnowBody,
  FrontCard,
  FrontCheckedBody,
  FrontNextMonthBody,
  FrontNextStepsBody,
  FrontSummaryBody,
} from './FrontSection.tsx'

interface DashboardWordsProps {
  dashboard: Dashboard
  front: Front
  onOpenNote: (code: NoteCode) => void
}

export function DashboardWords({ dashboard, front, onOpenNote }: DashboardWordsProps) {
  const captions = [
    ...dashboard.widgets.flatMap((widget) => widget.caption.map((line) => `${widget.title ?? ''}: ${line}`)),
    ...(front.waterfall ? [`Where the change came from: ${front.waterfall.caption}`] : []),
    ...(front.waterfall?.note ? [`Where the change came from: ${front.waterfall.note}`] : []),
  ]
  const compared = front.state === 'compared'
  return (
    <FrontCard title="The dashboard in words" className="dashboard-words">
      <h3 className="front__group-title">In short</h3>
      <FrontSummaryBody front={front} onOpenNote={onOpenNote} withCaution />
      {/* Why no chart of the change is drawn: the front's change card said it; here, as report.html says it. */}
      {front.waterfall_note && <p className="front__small">{front.waterfall_note}</p>}
      {dashboard.not_shown.map((line, index) => (
        // Two lines may read alike; their place is their identity.
        <p className="front__small" key={index}>
          {line}
        </p>
      ))}
      {captions.length > 0 && (
        <>
          <h3 className="front__group-title">About the charts</h3>
          {captions.map((line, index) => (
            <p key={index}>{line}</p>
          ))}
        </>
      )}
      {compared && (
        <>
          <h3 className="front__group-title">What was checked</h3>
          <FrontCheckedBody front={front} onOpenNote={onOpenNote} />
        </>
      )}
      {compared && front.next_steps !== null && (
        <>
          <h3 className="front__group-title">What to do next</h3>
          <FrontNextStepsBody front={front} onOpenNote={onOpenNote} />
        </>
      )}
      <h3 className="front__group-title">Next month</h3>
      <FrontNextMonthBody front={front} onOpenNote={onOpenNote} />
      <h3 className="front__group-title">What this report cannot know</h3>
      <FrontCannotKnowBody front={front} />
    </FrontCard>
  )
}
