// The Review screen's number question (session 2E-u1, Thach), built on the
// Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`): how
// the quantity and price columns' numbers are written, when the file cannot
// say ("1,000" is one thousand or one). Like the date question it blocks
// Confirm until answered: stage 1 refuses to run without it - never a default
// either way. A proven column is shown with its proof; stage 1 refuses an
// answer against a proof, so none is offered.

import { Notice } from './Notice.tsx'
import { numberColumns } from '../domain/numberFormat.ts'
import type { CleaningPlan, NumberFormat, NumberFormatMeasure, ProfileContract } from '../types/contracts.ts'

interface NumberFormatNoticeProps {
  plan: CleaningPlan
  profile: ProfileContract
  answers: Readonly<Record<string, NumberFormat>>
  onAnswer: (column: string, format: NumberFormat | null) => void
}

const WORDS: Record<NumberFormat, string> = { decimal_point: 'a decimal point', decimal_comma: 'a decimal comma' }

function count(value: number, singular: string, plural: string): string {
  return `${value.toLocaleString('en-US')} ${value === 1 ? singular : plural}`
}

function why(measure: NumberFormatMeasure): string {
  const example = measure.ambiguous_example ?? '1,000'
  // Both marks proven is no guide either (2E-u1 review 1, F8).
  const which =
    measure.point > 0 && measure.comma > 0
      ? `the column's other numbers prove both marks ("${measure.point_example ?? ''}" and "${measure.comma_example ?? ''}")`
      : "none of the column's numbers says which"
  return `${count(measure.ambiguous, `number such as "${example}" can`, `numbers such as "${example}" can`)} be read two ways - with the comma or point grouping thousands, or as the decimal mark - and ${which}.`
}

export function NumberFormatNotice({ plan, profile, answers, onAnswer }: NumberFormatNoticeProps) {
  return (
    <>
      {numberColumns(plan, profile).map(({ column, measure }) => {
        const answer: NumberFormat | null = column in answers ? answers[column] : null
        if (measure.decision === 'ask' && answer === null) {
          return (
            <Notice
              key={column}
              tone="warning"
              title={`How are the numbers in "${column}" written?`}
              actions={
                <>
                  <button type="button" className="button button--secondary" onClick={() => { onAnswer(column, 'decimal_point') }}>
                    With a decimal point (1,000.50)
                  </button>
                  <button type="button" className="button button--secondary" onClick={() => { onAnswer(column, 'decimal_comma') }}>
                    With a decimal comma (1.000,50)
                  </button>
                </>
              }
            >
              {why(measure)} Read the wrong way, the figures are a thousand times off.
            </Notice>
          )
        }
        if (measure.decision === 'ask' && answer !== null) {
          // A column proving both marks reads each proving number by its own
          // mark; the answer decides only the two-way ones (review 2, N7).
          const both = measure.point > 0 && measure.comma > 0
          const which = both ? `Numbers such as "${measure.ambiguous_example ?? '1,000'}" in` : 'Numbers in'
          return (
            <Notice
              key={column}
              tone="info"
              title={`${which} "${column}" are read with ${WORDS[answer]}`}
              actions={
                <button type="button" className="link-button" onClick={() => { onAnswer(column, null) }}>
                  Change
                </button>
              }
            >
              {both
                ? `As you answered; a number that proves its own mark ("${measure.point_example ?? ''}", "${measure.comma_example ?? ''}") is read by it.`
                : 'As you answered.'}
            </Notice>
          )
        }
        if (measure.decision === 'decimal_point' || measure.decision === 'decimal_comma') {
          const proof = measure.decision === 'decimal_point' ? measure.point : measure.comma
          const example = measure.decision === 'decimal_point' ? measure.point_example : measure.comma_example
          return (
            <Notice key={column} tone="info" title={`Numbers in "${column}" are read with ${WORDS[measure.decision]}`}>
              {`${count(proof, 'number', 'numbers')}, such as "${example ?? ''}", can only be read that way.`}
            </Notice>
          )
        }
        return null
      })}
    </>
  )
}
