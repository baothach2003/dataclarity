// Review's whole-file view of the line taxonomy, as sentences (session 2E-t3;
// docs/LINE_TAXONOMY.md sections 3 and 5). Stage 1 computes every figure
// (pandas, CLAUDE.md 3.2); this module only words them. A money figure is shown
// with two decimals, a count with its noun.

import type {
  FigureNote,
  IdentityTerms,
  LineSummary,
  NoteMeasure,
  OutsideRevenueLines,
  ReservedRename,
  UnclassifiedLines,
  UnmeasurableLines,
} from '../types/lineSummary.ts'

const MONEY = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function money(value: number): string {
  return MONEY.format(value)
}

function signed(value: number): string {
  return value > 0 ? `+${MONEY.format(value)}` : MONEY.format(value)
}

export function count(value: number, singular: string, plural: string): string {
  return `${value.toLocaleString('en-US')} ${value === 1 ? singular : plural}`
}

/** The identity, its terms as they add up (the returns, discounts and other
 * deductions are what they took away). */
export function identityLine(terms: IdentityTerms): string {
  return [
    `Gross sales ${money(terms.gross_sales)}`,
    `− returns ${money(terms.returns)}`,
    `− discounts ${money(terms.discounts)}`,
    `− other deductions (unconfirmed) ${money(terms.other_deductions)}`,
    `+ other revenue ${money(terms.other_revenue)}`,
    `= net revenue ${money(terms.net_revenue)}`,
  ].join(' ')
}

/** What the identity cannot tell apart, or leaves out, when there is any. */
export function identityCaveats(summary: LineSummary): string[] {
  const found: string[] = []
  if (summary.identity.returns_on_suggested_keys !== 0) {
    found.push(
      `${money(summary.identity.returns_on_suggested_keys)} of the returns are on codes the file suggests ` +
        'are not products, which nobody has confirmed.',
    )
  }
  if (summary.undated_lines > 0) {
    // Some may be outside revenue anyway: the sentence says what is true of
    // every one of them (review 3 #3).
    const them = summary.undated_lines === 1 ? 'it is' : 'they are'
    found.push(
      `${count(summary.undated_lines, 'line has', 'lines have')} no date, so ${them} in no month; the revenue ` +
        'above counts dated lines only.',
    )
  }
  return found
}

const OUTSIDE: Record<OutsideRevenueLines['line_class'], string> = {
  gift_card_sale: 'Gift cards sold',
  gift_card_redemption: 'Gift cards redeemed',
  cost: 'Fees and costs',
  adjustment: 'Accounting adjustments',
  stock_in: 'Stock received',
}

const SIGNS: Record<NonNullable<OutsideRevenueLines['sign']>, string> = {
  positive: 'positive amounts',
  negative: 'negative amounts',
  no_money: 'no money',
}

/** One line per class outside revenue - stock received per sign - with its
 * lines, its money and the lines whose money is unknown. */
export function outsideRevenueLines(rows: OutsideRevenueLines[]): string[] {
  return rows.map((row) => {
    const kind = row.sign === null ? OUTSIDE[row.line_class] : `${OUTSIDE[row.line_class]}, ${SIGNS[row.sign]}`
    const amount = row.sign === 'no_money' ? '' : ` (${signed(row.amount)})`
    const unknown =
      row.lines_without_amount > 0 ? `, ${count(row.lines_without_amount, 'line', 'lines')} with no amount` : ''
    return `${kind}: ${count(row.lines, 'line', 'lines')}${amount}${unknown}`
  })
}

const REASONS: Record<UnmeasurableLines['reason'], string> = {
  'no quantity': 'with no quantity',
  'no price': 'with no price',
  'amount too large to add': 'with an amount too large to add',
}

/** The lines counted nowhere because their numbers do not add up, per
 * reason as stage 1 counted them; their money is unknown, never derived from
 * another column. */
export function unmeasurableLine(rows: UnmeasurableLines[]): string | null {
  if (rows.length === 0) {
    return null
  }
  const reasons = rows.map((row) => count(row.lines, 'line', 'lines') + ` ${REASONS[row.reason]}`).join(', ')
  return `Lines that cannot be measured: ${reasons}. Their money is unknown and in no figure.`
}

/** The lines no rule placed - none while v1 refuses no shape - with their
 * money and its share of the money the counted lines moved. */
export function unclassifiedLine(row: UnclassifiedLines): string | null {
  if (row.lines === 0) {
    return null
  }
  const share =
    row.share_of_money_moved === null ? '' : `, ${(row.share_of_money_moved * 100).toFixed(1)}% of the money moved`
  return `${count(row.lines, 'line matches', 'lines match')} no rule (${money(row.amount)}${share}): outside revenue.`
}

// Each note's measures, by name (shared/line_report.py). A transaction type's
// measures are named by the file's own values.
const MEASURES: Partial<Record<string, Partial<Record<string, string>>>> = {
  same_day_cancellations: {
    returns: 'returns rung the day their customer bought the product',
    sales: 'those purchases',
    returns_unchecked: 'returns no match can check',
  },
  returns_booked_as_in: {
    positive: 'positive amounts',
    negative: 'negative amounts',
    zero: 'zero amounts',
    unknown: 'no amount',
  },
  unconfirmed_suggestions: { lines: 'lines on those codes', returns: 'their returns' },
  unconfirmed_deductions: { lines: 'lines at a negative price' },
}

/** A note's measure as lines, money, and orders and codes where it has them. */
export function measureLine(note: FigureNote, measure: NoteMeasure): string {
  const types = note.code === 'other_transaction_types'
  const name = types ? `"${measure.name}"` : (MEASURES[note.code]?.[measure.name] ?? measure.name)
  const parts = [count(measure.lines, 'line', 'lines')]
  if (measure.amount !== null) {
    parts.push(signed(measure.amount))
  }
  if (measure.orders !== null) {
    parts.push(count(measure.orders, 'order', 'orders'))
  }
  if (measure.keys !== null) {
    parts.push(types ? count(measure.keys, 'value', 'values') : count(measure.keys, 'code', 'codes'))
  }
  return `${name}: ${parts.join(', ')}`
}

/** A source column the run writes under another name, and what the cleaned
 * file's own column of that name holds - in stage 1's words. */
export function renameLine(rename: ReservedRename): string {
  return `"${rename.source}" will be written as "${rename.written_as}": the cleaned file's "${rename.source}" holds ${rename.holds}.`
}
