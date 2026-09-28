import { describe, expect, it } from 'vitest'
import {
  identityCaveats,
  identityLine,
  measureLine,
  outsideRevenueLines,
  renameLine,
  unclassifiedLine,
  unmeasurableLine,
} from './lineSummary.ts'
import type { FigureNote, LineSummary } from '../types/lineSummary.ts'

// Session 2E-t3: Review's whole-file view, worded - written before the code.
// The figures are 2E-t3's hand-built file (tests/stages/ingest/test_2et3_summary.py).

const SUMMARY: LineSummary = {
  lines: 17,
  undated_lines: 1,
  identity: {
    gross_sales: 65,
    returns: 13,
    discounts: 5,
    other_deductions: 2,
    other_revenue: 4,
    net_revenue: 49,
    returns_on_suggested_keys: 3,
    money_moved: 89,
  },
  outside_revenue: [
    { line_class: 'cost', scope: 'file', sign: null, lines: 1, amount: -7, lines_without_amount: 0 },
    { line_class: 'stock_in', scope: 'file', sign: 'positive', lines: 1, amount: 10, lines_without_amount: 0 },
    { line_class: 'stock_in', scope: 'file', sign: 'no_money', lines: 1, amount: 0, lines_without_amount: 1 },
  ],
  unclassified: { lines: 0, amount: 0, share_of_money_moved: 0 },
  unmeasurable: [
    { scope: 'file', reason: 'no quantity', lines: 2 },
    { scope: 'file', reason: 'no price', lines: 1 },
  ],
  notes: [],
}

describe('the whole file as the answers stand, in words (2E-t3)', () => {
  it('writes the identity as its terms add up', () => {
    expect(identityLine(SUMMARY.identity)).toBe(
      'Gross sales 65.00 − returns 13.00 − discounts 5.00 − other deductions (unconfirmed) 2.00 + other revenue ' +
        '4.00 = net revenue 49.00',
    )
  })

  it('says what the identity cannot tell apart and what it leaves out', () => {
    expect(identityCaveats(SUMMARY)).toEqual([
      '3.00 of the returns are on codes the file suggests are not products, which nobody has confirmed.',
      '1 line has no date, so it is in no month; the revenue above counts dated lines only.',
    ])
    expect(identityCaveats({ ...SUMMARY, undated_lines: 0, identity: { ...SUMMARY.identity, returns_on_suggested_keys: 0 } })).toEqual([])
  })

  it('lists what is outside revenue, stock received by sign, an unknown amount said', () => {
    expect(outsideRevenueLines(SUMMARY.outside_revenue)).toEqual([
      'Fees and costs: 1 line (-7.00)',
      'Stock received, positive amounts: 1 line (+10.00)',
      'Stock received, no money: 1 line, 1 line with no amount',
    ])
  })

  it('words the unmeasurable lines per reason as stage 1 counted them, adding nothing up', () => {
    expect(unmeasurableLine(SUMMARY.unmeasurable)).toBe(
      'Lines that cannot be measured: 2 lines with no quantity, 1 line with no price. Their money is unknown and in ' +
        'no figure.',
    )
    expect(unmeasurableLine([])).toBeNull()
  })

  it('shows the lines no rule placed with their share of the money moved (review 1 #5)', () => {
    expect(unclassifiedLine(SUMMARY.unclassified)).toBeNull()
    expect(unclassifiedLine({ lines: 2, amount: -8.9, share_of_money_moved: 0.1 })).toBe(
      '2 lines match no rule (-8.90, 10.0% of the money moved): outside revenue.',
    )
    expect(unclassifiedLine({ lines: 1, amount: 0, share_of_money_moved: null })).toBe(
      '1 line matches no rule (0.00): outside revenue.',
    )
  })

  it("names each note's measures, a transaction type by the file's own value", () => {
    const sameDay: FigureNote = {
      code: 'same_day_cancellations',
      figures: [],
      text: '',
      measures: [{ name: 'returns_unchecked', scope: 'file', lines: 749, amount: -431904.64, orders: 390, keys: null }],
    }
    expect(measureLine(sameDay, sameDay.measures[0])).toBe('returns no match can check: 749 lines, -431,904.64, 390 orders')
    const types: FigureNote = {
      code: 'other_transaction_types',
      figures: [],
      text: '',
      measures: [{ name: '(other values)', scope: 'file', lines: 28, amount: 140, orders: null, keys: 7 }],
    }
    expect(measureLine(types, types.measures[0])).toBe('"(other values)": 28 lines, +140.00, 7 values')
  })

  it("says a source column will be written under another name, and why, in stage 1's words", () => {
    expect(renameLine({ source: 'line_class', written_as: 'line_class_source', holds: "each line's class" })).toBe(
      '"line_class" will be written as "line_class_source": the cleaned file\'s "line_class" holds each line\'s class.',
    )
  })
})
