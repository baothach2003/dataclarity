// Issue badge (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:215`): severity =
// low / medium / high, text "<issue> · <count>", examples on hover.

import { ISSUE_LABELS } from '../domain/labels.ts'
import type { CanonicalField, ColumnIssue } from '../types/contracts.ts'
import { columnIssueSeverity } from '../domain/issueSeverity.ts'

interface IssueBadgesProps {
  issues: ColumnIssue[]
  canonicalField: CanonicalField
}

export function IssueBadges({ issues, canonicalField }: IssueBadgesProps) {
  if (issues.length === 0) {
    return <span className="issues-empty">None</span>
  }
  return (
    <span className="issue-badges">
      {issues.map((issue) => {
        const severity = columnIssueSeverity(issue.code, canonicalField, issue.pct)
        const title = issue.examples.length > 0 ? issue.examples.join(', ') : undefined
        return (
          <span key={issue.code} className={`badge badge--${severity}`} title={title}>
            {ISSUE_LABELS[issue.code]} · {issue.count}
          </span>
        )
      })}
    </span>
  )
}
