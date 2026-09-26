// The Review screen's walk-in placeholder questions (session 2E-k, Thach),
// built on the Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node
// `1:271`): one per candidate value. Yes makes its lines unattributed in
// stages 2 and 3; a false question only costs the user one answer.

import { Notice } from './Notice.tsx'
import { customerIdentity, formatShare } from '../domain/customerChecks.ts'
import type { PlaceholderCandidate } from '../domain/customerChecks.ts'

interface PlaceholderNoticesProps {
  candidates: PlaceholderCandidate[]
  // The answer that applies to each candidate, by customer identity.
  answers: ReadonlyMap<string, boolean>
  onAnswer: (value: string, placeholder: boolean | null) => void
}

function shares(candidate: PlaceholderCandidate): string {
  const lines = `${formatShare(candidate.linesPct)}% of the lines`
  return candidate.revenuePct === null ? lines : `${lines} and ${formatShare(candidate.revenuePct)}% of the sale revenue`
}

export function PlaceholderNotices({ candidates, answers, onAnswer }: PlaceholderNoticesProps) {
  return (
    <>
      {candidates.map((candidate) => {
        const answer = answers.get(customerIdentity(candidate.value))
        if (answer !== undefined) {
          return (
            <Notice
              key={candidate.value}
              tone="info"
              title={answer ? `"${candidate.value}" is a placeholder for walk-ins` : `"${candidate.value}" is a real customer`}
              actions={
                <button type="button" className="link-button" onClick={() => { onAnswer(candidate.value, null) }}>
                  Change
                </button>
              }
            >
              {answer ? 'Its lines are counted with no customer.' : 'Its lines are its own.'}
            </Notice>
          )
        }
        return (
          <Notice
            key={candidate.value}
            tone="warning"
            title={`Is "${candidate.value}" a placeholder for walk-ins?`}
            actions={
              <>
                <button type="button" className="button button--secondary" onClick={() => { onAnswer(candidate.value, true) }}>
                  Yes, a placeholder
                </button>
                <button type="button" className="link-button" onClick={() => { onAnswer(candidate.value, false) }}>
                  No, a real customer
                </button>
              </>
            }
          >
            {`It is on ${shares(candidate)}. If it stands for customers the shop did not record, answer Yes: those lines are counted with no customer.`}
          </Notice>
        )
      })}
    </>
  )
}
