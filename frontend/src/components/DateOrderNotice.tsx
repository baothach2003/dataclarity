// The Review screen's date question (session 2E-j, Thach), built on the
// Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`):
// how the date column's day-month-year cells are written, when the file
// cannot say. Unlike the order questions it blocks Confirm until answered
// (the action bar says so): stage 1 refuses to run without it, because
// either default fabricates dates. A proven order is shown with its proof
// and may be overridden (Thach, 2E-o Q8: the answer wins, the cells against it
// become undated),
// and a parse step reading the other way is shown with its fix.

import { Notice } from './Notice.tsx'
import { dateMeasure, parseConflict } from '../domain/dateOrder.ts'
import type { CleaningPlan, DateOrder, DateOrderMeasure, Params, ProfileContract } from '../types/contracts.ts'

interface DateOrderNoticeProps {
  plan: CleaningPlan
  profile: ProfileContract
  answer: boolean | null
  onAnswer: (dayFirst: boolean | null) => void
  onFixParse: (column: string, params: Params) => void
}

const WORDS: Record<DateOrder, string> = { day_first: 'day first', month_first: 'month first' }

function other(order: DateOrder): DateOrder {
  return order === 'day_first' ? 'month_first' : 'day_first'
}

function count(value: number, singular: string, plural: string): string {
  return `${value.toLocaleString('en-US')} ${value === 1 ? singular : plural}`
}

function why(measure: DateOrderMeasure): string {
  if (measure.day_first > 0 && measure.month_first > 0) {
    return `Some dates prove each way: "${measure.day_first_example ?? ''}" can only be day first and "${measure.month_first_example ?? ''}" only month first, so the dates the other way will be left without a date.`
  }
  return `${count(measure.ambiguous, 'date such as 05/01/2026 can', 'dates such as 05/01/2026 can')} be read two ways - 5 January or 1 May - and none of the file's dates says which.`
}

function hint(measure: DateOrderMeasure): string {
  if (measure.hint === 'day_first') {
    return ' Read day first, every date is the 1st of a month, as in a file of monthly figures; read month first, they all fall in the first days of January.'
  }
  if (measure.hint === 'month_first') {
    return ' Read month first, every date is the 1st of a month, as in a file of monthly figures; read day first, they all fall in the first days of January.'
  }
  return ''
}

export function DateOrderNotice({ plan, profile, answer, onAnswer, onFixParse }: DateOrderNoticeProps) {
  const found = dateMeasure(plan, profile)
  if (found === null) {
    return null
  }
  const { column, measure } = found
  const conflict = parseConflict(plan, profile, answer)
  const fix = conflict?.fix ?? null
  const proven = measure.decision === 'ask' ? null : measure.decision
  const proof = proven === 'day_first' ? measure.day_first : measure.month_first
  const example = proven === 'day_first' ? measure.day_first_example : measure.month_first_example
  const answerOrder: DateOrder | null = answer === null ? null : answer ? 'day_first' : 'month_first'

  return (
    <>
      {proven === null && answer === null && (
        <Notice
          tone="warning"
          title={`How are the dates in "${column}" written?`}
          actions={
            <>
              <button type="button" className="button button--secondary" onClick={() => { onAnswer(true) }}>
                Day first (31/12/2026)
              </button>
              <button type="button" className="button button--secondary" onClick={() => { onAnswer(false) }}>
                Month first (12/31/2026)
              </button>
            </>
          }
        >
          {why(measure)}
          {hint(measure)} Read the wrong way, sales move to other months.
        </Notice>
      )}
      {proven === null && answer !== null && (
        <Notice
          tone="info"
          title={`Dates in "${column}" are read ${answer ? 'day first' : 'month first'}`}
          actions={
            <button type="button" className="link-button" onClick={() => { onAnswer(null) }}>
              Change
            </button>
          }
        >
          As you answered.
        </Notice>
      )}
      {proven !== null && (answerOrder === null || answerOrder === proven) && (
        <Notice
          tone="info"
          title={`Dates in "${column}" are read ${WORDS[proven]}`}
          actions={
            // Thach, 2E-o Q8: the user may override a proof - a typo can prove an order.
            <button type="button" className="link-button" onClick={() => { onAnswer(proven !== 'day_first') }}>
              {`They are written ${WORDS[other(proven)]}`}
            </button>
          }
        >
          {`${count(proof, 'date', 'dates')}, such as "${example ?? ''}", can only be read that way.`}
        </Notice>
      )}
      {proven !== null && answerOrder !== null && answerOrder !== proven && (
        <Notice
          // A warning: overriding a proof leaves dates undated and moves others (2E-o review cycle 2 #9).
          tone="warning"
          title={`Dates in "${column}" are read ${WORDS[answerOrder]}`}
          actions={
            <button type="button" className="link-button" onClick={() => { onAnswer(null) }}>
              Change
            </button>
          }
        >
          {`As you answered: ${count(proof, 'date that can only be read', 'dates that can only be read')} ${WORDS[proven]}, such as "${example ?? ''}", will have no date, and ${proof === 1 ? 'is' : 'are'} counted as undated; ${count(measure.ambiguous, 'date that reads', 'dates that read')} either way ${measure.ambiguous === 1 ? 'is' : 'are'} read ${WORDS[answerOrder]}.`}
        </Notice>
      )}
      {conflict !== null && (
        <Notice
          tone="warning"
          title={`The parse step on "${column}" reads these dates ${WORDS[conflict.order === 'day_first' ? 'month_first' : 'day_first']}`}
          actions={
            fix !== null && (
              <button type="button" className="button button--secondary" onClick={() => { onFixParse(column, fix) }}>
                {`Read them ${WORDS[conflict.order]}`}
              </button>
            )
          }
        >
          {fix !== null
            ? `Cleaning would write some dates wrong, so it will not run until the step reads them ${WORDS[conflict.order]}.`
            : `Cleaning would write some dates wrong, so it will not run until the step reads them ${WORDS[conflict.order]}: give it a format such as %m/%d/%Y.`}
        </Notice>
      )}
    </>
  )
}
