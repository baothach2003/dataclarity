// The recommendations' place (the design gap review: the cards REMOVED, an info Notice in their place, ADD 14).
// No AI writes a recommendation in v1 (the report redesign's step 4, Thach's option (d)), and the free text of an
// older report is shown nowhere (Q42): one Notice, whatever the file holds. The code-written suggested actions
// belong to the report's front section (step 5 brings it to the page).

import type { ReactNode } from 'react'
import { Notice } from './Notice.tsx'

function Place({ children }: { children: ReactNode }) {
  // A heading in the recommendations' place, so a reader finds it whatever it holds (the 6E3 review).
  return (
    <section className="insights-section">
      <h2 className="insights-section__title">Recommendations</h2>
      {children}
    </section>
  )
}

export const NO_AI_RECOMMENDATIONS = 'No AI writes recommendations in this version.'

export function RecommendationsSection() {
  return (
    <Place>
      <Notice tone="info" title={NO_AI_RECOMMENDATIONS} />
    </Place>
  )
}
