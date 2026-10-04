// The recommendations' place (the design gap review: the cards REMOVED - stage 4's AI step is off in v1 -
// an info Notice in their place, ADD 14), in stage 5's words (html_report._actions). When the backend shows
// them, they are listed as written (AI text, rendered escaped - SEC-3) with every note beside them, by
// construction (CONTRACTS 11: the AI's free text maps back to no figure).

import type { ReactNode } from 'react'
import type { Actions, NoteView, ReportPeriod } from '../types/report.ts'
import { Notice } from './Notice.tsx'
import { NotesBeside } from './NotesBeside.tsx'

interface RecommendationsSectionProps {
  actions: Actions
  notes: NoteView[]
  period: ReportPeriod
}

function Place({ children }: { children: ReactNode }) {
  // A heading in the recommendations' place, so a reader finds it whatever it holds (the 6E3 review).
  return (
    <section className="insights-section">
      <h2 className="insights-section__title">Recommendations</h2>
      {children}
    </section>
  )
}

export function RecommendationsSection({ actions, notes, period }: RecommendationsSectionProps) {
  if (actions.recommendations_status === 'switched_off') {
    return (
      <Place>
        <Notice tone="info" title="The AI recommendations are switched off for this report." />
      </Place>
    )
  }
  const { recommendations, do_not_do: doNotDo } = actions
  if (recommendations === null || doNotDo === null || recommendations.length === 0 || actions.recommendations_status === 'unavailable') {
    return (
      <Place>
        <Notice tone="info" title="No AI recommendation is available for this run." />
      </Place>
    )
  }
  return (
    <section className="card insights-card">
      <h2 className="insights-card__title">Recommendations</h2>
      <ol className="recommendations">
        {recommendations.map((item, index) => (
          // The AI's priorities are not unique by contract; their place is their identity.
          <li key={index}>
            <p className="recommendations__action">{item.action}</p>
            <p>{`Insight: ${item.insight}`}</p>
            <p>{`Cause: ${item.cause}`}</p>
            <p>{`Expected impact: ${item.expected_impact}`}</p>
            <p>{`How to measure: ${item.how_to_measure}`}</p>
            <p>{`Confidence: ${item.confidence_label}`}</p>
          </li>
        ))}
      </ol>
      {doNotDo.length > 0 && (
        <ul>
          {doNotDo.map((item, index) => (
            <li key={index}>{`Do not: ${item.tempting_action} - ${item.why_wrong_here}`}</li>
          ))}
        </ul>
      )}
      <NotesBeside codes={actions.notes} notes={notes} period={period} />
    </section>
  )
}
