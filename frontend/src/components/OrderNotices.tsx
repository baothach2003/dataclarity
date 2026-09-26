// The Review screen's order notices (session 2E-e2, Thach), built on the
// Notice component (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:271`):
// blank order ids, whether the order id is a receipt number when there is no
// customer column, and whether the customer is written on a receipt's first
// line only. An unanswered question never blocks Confirm: stage 2 reads the
// receipt question as "no" (unconfirmed means untrusted) and the fill
// question as "yes" (2E-f's rule; doubt-review A).

import { useState } from 'react'
import { Notice } from './Notice.tsx'
import {
  blankOrderIds,
  customerImputed,
  fillQuestion,
  needsReceiptConfirmation,
  orderIdColumn,
} from '../domain/orderChecks.ts'
import type { Question } from '../domain/orderChecks.ts'
import type { CleaningPlan, OrderConfirmations, ProfileContract, SchemaInferenceContract } from '../types/contracts.ts'

interface OrderNoticesProps {
  plan: CleaningPlan
  answers: OrderConfirmations
  // Customer values confirmed as walk-in placeholders (2E-k): no customer.
  placeholders: string[]
  profile: ProfileContract
  schema: SchemaInferenceContract | null
  onAnswer: (key: Question, value: boolean | null) => void
  onDropBlankIds: (column: string) => void
  onUploadFixed: () => void
}

function lines(count: number, singular: string, plural: string): string {
  return `${count.toLocaleString('en-US')} ${count === 1 ? singular : plural}`
}

export function OrderNotices({
  plan,
  answers,
  placeholders,
  profile,
  schema,
  onAnswer,
  onDropBlankIds,
  onUploadFixed,
}: OrderNoticesProps) {
  // The column whose blank ids the user chose to keep: a remap asks again (cycle 2 F8).
  const [keptBlankIdsOf, setKeptBlankIdsOf] = useState<string | null>(null)
  const blank = blankOrderIds(plan, profile)
  // A restock has no receipt, so its id is often blank: dropping the blank-id
  // lines drops such stock-in lines too (cycle 2 F7).
  const stockLines = plan.column_actions.some(
    (c) => c.canonical_field === 'transaction_type' && c.action !== 'drop_column',
  )
  const dropping =
    blank !== null && plan.column_actions.some((c) => c.source_name === blank.column && c.action === 'drop_rows_missing')
  const orderColumn = orderIdColumn(plan)
  const receiptColumn = needsReceiptConfirmation(plan, profile, schema, placeholders)
  const fill = fillQuestion(plan, schema, profile, placeholders)
  // Stage 1's own check found this column's ids spanning days or customers:
  // a Yes does not make stage 2 count orders (cycle 3 F4).
  const flagged =
    schema?.columns
      .find((c) => c.source_name === orderColumn)
      ?.issues.some((issue) => issue.code === 'order_id_not_one_order') ?? false
  const keptBlankIds = blank !== null && !dropping

  function change(key: Question) {
    return (
      <button type="button" className="link-button" onClick={() => { onAnswer(key, null) }}>
        Change
      </button>
    )
  }

  return (
    <>
      {blank !== null && dropping && (
        <Notice tone="info" title={`Up to ${lines(blank.count, 'line', 'lines')} with no order id will be dropped`}>
          Those lines are removed, and their revenue leaves every figure.
          {stockLines && ' Stock-in lines with no order id are dropped too, and leave the stock figures.'}
        </Notice>
      )}
      {blank !== null && !dropping && keptBlankIdsOf !== blank.column && (
        <Notice
          tone="warning"
          title={`Up to ${lines(blank.count, 'line has', 'lines have')} no order id`}
          actions={
            <>
              <button type="button" className="button button--secondary" onClick={() => { onDropBlankIds(blank.column) }}>
                Drop these lines
              </button>
              <button type="button" className="link-button" onClick={onUploadFixed}>
                Upload a fixed file
              </button>
              <button type="button" className="link-button" onClick={() => { setKeptBlankIdsOf(blank.column) }}>
                Keep and count lines
              </button>
            </>
          }
        >
          While any sale or return line has no order id, the whole file counts lines, not orders, and
          average order value reads as average line value. Ids cannot be filled in: one made-up id
          would merge every blank line into a single order.
          {stockLines && ' If you drop these lines, stock-in lines with no order id are dropped too, and leave the stock figures.'}
        </Notice>
      )}

      {receiptColumn !== null && answers.order_id_is_receipt === null && (
        <Notice
          tone="warning"
          title={`Is "${receiptColumn}" a receipt number?`}
          actions={
            <>
              <button type="button" className="button button--secondary" onClick={() => { onAnswer('order_id_is_receipt', true) }}>
                Yes, a receipt number
              </button>
              <button type="button" className="link-button" onClick={() => { onAnswer('order_id_is_receipt', false) }}>
                No, a batch code
              </button>
            </>
          }
        >
          Without enough customer names on the receipts, this column could be checked by date only,
          and a daily batch or Z-report code passes that check.{' '}
          {customerImputed(plan)
            ? 'Your plan fills the blank customers in, so the cleaned file seems to name customers and this column can pass as a receipt number: answer No if it is a batch code.'
            : 'Unless you confirm it is a receipt or invoice number, orders may be counted as lines.'}
        </Notice>
      )}
      {orderColumn !== null && answers.order_id_is_receipt === true && (
        <Notice tone="info" title={`"${orderColumn}" is a receipt number`} actions={change('order_id_is_receipt')}>
          {flagged
            ? "Stage 1 found this column's ids spanning several days or customers, so the file counts lines."
            : keptBlankIds
              ? 'Orders will be counted by this column once every sale and return line has an id; until then the file counts lines.'
              : 'Orders are counted by this column.'}
        </Notice>
      )}
      {orderColumn !== null && answers.order_id_is_receipt === false && (
        <Notice tone="info" title={`"${orderColumn}" is not a receipt number`} actions={change('order_id_is_receipt')}>
          Orders are counted as lines.
        </Notice>
      )}

      {fill !== null && answers.customer_on_first_line_only === null && (
        <Notice
          tone="warning"
          title="Is the customer written on a receipt's first line only?"
          actions={
            <>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => { onAnswer('customer_on_first_line_only', true) }}
              >
                Yes, the first line only
              </button>
              <button type="button" className="link-button" onClick={() => { onAnswer('customer_on_first_line_only', false) }}>
                No, leave them without a customer
              </button>
            </>
          }
        >
          {fill.lines === null
            ? 'DataClarity could not count these lines for the current columns: some lines may have no customer but share a receipt number with a line that names one.'
            : `${lines(fill.lines, 'line has no customer but shares', 'lines have no customer but share')} a receipt number with a line that names one.`}{' '}
          If the customer is written once per receipt, those lines are that customer&apos;s - and they
          are taken to be unless you answer No. If not - a daily batch code with walk-in sales, for
          example - answer No and they stay without a customer.
        </Notice>
      )}
      {fill !== null && answers.customer_on_first_line_only === true && (
        <Notice
          tone="info"
          title="The customer is written on a receipt's first line only"
          actions={change('customer_on_first_line_only')}
        >
          {keptBlankIds
            ? "Once every sale and return line has an order id, lines with no customer take their receipt's customer; until then the file counts lines and nothing is filled."
            : "Lines with no customer take their receipt's customer."}
        </Notice>
      )}
      {fill !== null && answers.customer_on_first_line_only === false && (
        <Notice
          tone="info"
          title="The customer is not written on a receipt's first line only"
          actions={change('customer_on_first_line_only')}
        >
          Lines with no customer stay without one.
        </Notice>
      )}
    </>
  )
}
