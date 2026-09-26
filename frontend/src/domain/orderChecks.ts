// What the Review screen asks about orders (session 2E-e2, Thach), and which
// answers are sent. Stage 2 counts lines unless the user confirms the order
// id is a receipt number (unconfirmed means untrusted), and fills a receipt's
// unnamed lines from its named customer unless the user answers No (2E-f's
// rule; doubt-review A). These functions only decide what is asked and sent.

import type {
  CanonicalField,
  CleaningPlan,
  OrderConfirmations,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'
import { customerIdentity } from './customerChecks.ts'
import { IMPUTATION_ACTIONS } from './transformCatalog.ts'

// The fields stage 1's fill measure reads (shared/transactions.py
// order_checks): which lines are sales, their day, their receipt and their
// customer. Remapping any of them leaves the measure stale.
const FILL_FIELDS: CanonicalField[] = [
  'order_id',
  'customer',
  'transaction_date',
  'quantity',
  'unit_price',
  'transaction_type',
]

/** An answer remembers the mapping it was given for: after a remap it no
 * longer applies, and "yes, Inv is a receipt number" never reaches a Batch
 * column (doubt-review B). */
export interface StoredAnswer {
  value: boolean
  key: string
}
/** Review's two yes/no questions about orders. */
export type Question = 'order_id_is_receipt' | 'customer_on_first_line_only'
export type StoredAnswers = Record<Question, StoredAnswer | null>

export const NO_ANSWERS: StoredAnswers = { order_id_is_receipt: null, customer_on_first_line_only: null }

/** The plan's column for `field`, or null; a dropped column is not mapped
 * (planRules.droppedColumnNames, CONTRACTS section 5; doubt-review E, K). */
function mappedColumn(plan: CleaningPlan, field: CanonicalField): string | null {
  return (
    plan.column_actions.find((column) => column.canonical_field === field && column.action !== 'drop_column')
      ?.source_name ?? null
  )
}

function schemaColumn(schema: SchemaInferenceContract, field: CanonicalField): string | null {
  return schema.columns.find((column) => column.canonical_field === field)?.source_name ?? null
}

function blankCells(profile: ProfileContract, column: string | null): number {
  return profile.columns.find((c) => c.name === column)?.null_count ?? 0
}

/** The customer column, when it names at least two different customers: a
 * column blank on every line (review C), or "Walk-in" on every line (cycle 2
 * F4), leaves the check on the date alone, like no column - stage 2's rule
 * (shared/transactions._refused), read here from the raw file's profile. */
function namedCustomerColumn(plan: CleaningPlan, profile: ProfileContract): string | null {
  const column = mappedColumn(plan, 'customer')
  const distinct = profile.columns.find((c) => c.name === column)?.unique_count ?? 0
  return column !== null && distinct >= 2 && blankCells(profile, column) < profile.dataset.rows ? column : null
}

/** The column mapped to order_id, or null. */
export function orderIdColumn(plan: CleaningPlan): string | null {
  return mappedColumn(plan, 'order_id')
}

/** Whether the plan fills the customer column's blanks in: the cleaned file
 * then seems to name customers the raw file did not (cycle 3 F1). */
export function customerImputed(plan: CleaningPlan): boolean {
  const column = mappedColumn(plan, 'customer')
  return plan.column_actions.some((c) => c.source_name === column && IMPUTATION_ACTIONS.has(c.action))
}

/** The column mapped to order_id and how many of its cells are blank on the
 * raw file (profile.json's missing cells): "up to" that many sale and return
 * lines have no id, and any one of them makes the whole file count lines. */
export function blankOrderIds(plan: CleaningPlan, profile: ProfileContract): { column: string; count: number } | null {
  const column = mappedColumn(plan, 'order_id')
  const count = blankCells(profile, column)
  return column === null || count === 0 ? null : { column, count }
}

/** The order id column, when the order-id check could read dates only - a
 * daily batch code passes it. Stage 2 judges it per receipt (2E-k: most
 * receipts name no customer, one customer is on most, or fewer than two are
 * named); stage 1 measured that verdict on the raw file
 * (`order_id_date_only`), used while the columns are the ones it measured and
 * no placeholder is confirmed. Otherwise it is approximated per line from
 * profile.json, a confirmed placeholder counted as blank. */
export function needsReceiptConfirmation(
  plan: CleaningPlan,
  profile: ProfileContract,
  schema: SchemaInferenceContract | null = null,
  placeholders: readonly string[] = [],
): string | null {
  const column = mappedColumn(plan, 'order_id')
  if (column === null) {
    return null
  }
  const verdict = schema?.order_id_date_only ?? null
  const measured =
    schema !== null &&
    verdict !== null &&
    placeholders.length === 0 &&
    FILL_FIELDS.every((field) => mappedColumn(plan, field) === schemaColumn(schema, field))
  const dateOnly = measured ? verdict : approximatelyDateOnly(plan, profile, placeholders)
  return dateOnly ? column : null
}

/** Stage 2's rule read per line from profile.json ("mostly" = more than
 * half): mostly blank, one value on most lines, or fewer than two values. */
function approximatelyDateOnly(plan: CleaningPlan, profile: ProfileContract, placeholders: readonly string[]): boolean {
  const column = mappedColumn(plan, 'customer')
  const stats = profile.columns.find((c) => c.name === column)
  if (column === null || stats === undefined) {
    return true
  }
  const confirmed = new Set(placeholders.map(customerIdentity))
  const isPlaceholder = (value: string) => confirmed.has(customerIdentity(value))
  const placeholderValues = stats.top_values.filter((t) => isPlaceholder(t.value))
  const blank = stats.null_count + placeholderValues.reduce((sum, t) => sum + t.count, 0)
  const topReal = Math.max(0, ...stats.top_values.filter((t) => !isPlaceholder(t.value)).map((t) => t.count))
  const rows = profile.dataset.rows
  return blank * 2 > rows || topReal * 2 > rows || stats.unique_count - placeholderValues.length < 2
}

/** Whether to ask that the customer is written on a receipt's first line
 * only. `lines` is stage 1's count on the mapping it measured; null when
 * there is no count for this mapping - the user remapped a field the measure
 * reads, dropped the blank-id lines that made the raw file count lines
 * (review D), or the schema step did not run - so the question is asked
 * rather than left out. */
export function fillQuestion(
  plan: CleaningPlan,
  schema: SchemaInferenceContract | null,
  profile: ProfileContract,
  placeholders: readonly string[] = [],
): { lines: number | null } | null {
  const orderColumn = mappedColumn(plan, 'order_id')
  const customerColumn = namedCustomerColumn(plan, profile)
  if (orderColumn === null || customerColumn === null) {
    return null
  }
  // An imputed customer column has no blank left to fill (cycle 2 F11), and
  // a plan that drops the rows with no customer leaves none (cycle 3 F5).
  if (
    plan.column_actions.some(
      (c) =>
        c.source_name === customerColumn && (IMPUTATION_ACTIONS.has(c.action) || c.action === 'drop_rows_missing'),
    )
  ) {
    return null
  }
  const droppingBlankIds =
    blankCells(profile, orderColumn) > 0 &&
    plan.column_actions.some((c) => c.source_name === orderColumn && c.action === 'drop_rows_missing')
  // Stage 1 says null when the raw file could not tell (cycle 2 F5, F6).
  const lines = schema?.receipt_fill_lines ?? null
  // A confirmed placeholder changes which lines are named, and stage 1
  // measured without it: its 0 hid a fill that happens (2E-r F3), as its
  // date-only verdict would (needsReceiptConfirmation).
  const measured =
    schema !== null &&
    lines !== null &&
    !droppingBlankIds &&
    placeholders.length === 0 &&
    FILL_FIELDS.every((field) => mappedColumn(plan, field) === schemaColumn(schema, field))
  if (!measured) {
    return { lines: null }
  }
  return lines > 0 ? { lines } : null
}

/** What an answer is about: the order id column for the receipt question,
 * the columns the fill reads for the fill question. */
export function answerKey(plan: CleaningPlan, question: Question): string {
  return question === 'order_id_is_receipt'
    ? (mappedColumn(plan, 'order_id') ?? '')
    : JSON.stringify(FILL_FIELDS.map((field) => mappedColumn(plan, field)))
}

/** The answers that still apply to `plan`: the question is still asked, and
 * about the same columns as when it was answered. The user's No about an
 * order id column counts as long as that column is the order id, asked or
 * not (cycle 3 F2): stage 2 honours it whatever the customer column holds. */
export function applicableAnswers(
  plan: CleaningPlan,
  schema: SchemaInferenceContract | null,
  profile: ProfileContract,
  stored: StoredAnswers,
  placeholders: readonly string[] = [],
): OrderConfirmations {
  function current(question: Question, asked: boolean): boolean | null {
    const answer = stored[question]
    if (answer === null || answer.key !== answerKey(plan, question)) {
      return null
    }
    // An answer about the order id column holds while that column is the
    // order id, asked or not: a No always counts (2E-e2 cycle 3 F2), and a
    // Yes must not vanish when a remap or a placeholder hides the question
    // (2E-k doubt-review F3).
    if (question === 'order_id_is_receipt') {
      return answer.value
    }
    return asked ? answer.value : null
  }
  return {
    order_id_is_receipt: current(
      'order_id_is_receipt',
      needsReceiptConfirmation(plan, profile, schema, placeholders) !== null,
    ),
    customer_on_first_line_only: current(
      'customer_on_first_line_only',
      fillQuestion(plan, schema, profile, placeholders) !== null,
    ),
  }
}

/** The plan as sent: only real answers, so cleaning_report.json records
 * what the user said about the columns that ran. */
export function withApplicableConfirmations(
  plan: CleaningPlan,
  schema: SchemaInferenceContract | null,
  profile: ProfileContract,
  stored: StoredAnswers,
  placeholders: readonly string[] = [],
): CleaningPlan {
  const answers = applicableAnswers(plan, schema, profile, stored, placeholders)
  // The confirmed walk-in placeholders (2E-k) go only when there are some.
  return {
    ...plan,
    confirmations: placeholders.length > 0 ? { ...answers, customer_placeholders: [...placeholders] } : answers,
  }
}
