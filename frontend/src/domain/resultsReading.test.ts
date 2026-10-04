import { describe, expect, it } from 'vitest'
import type { CleaningReport } from '../types/contracts.ts'
import { describeReading } from './resultsReading.ts'

function report(overrides: Partial<CleaningReport> = {}): CleaningReport {
  return {
    schema_version: '4.2',
    generated_at: '2026-10-04T00:00:00Z',
    rows_in: 10,
    rows_out: 10,
    columns_in: 4,
    columns_out: 4,
    changes: [],
    warnings: [],
    column_mapping: { Date: 'transaction_date', Price: 'unit_price', Qty: 'quantity', Buyer: 'customer' },
    ...overrides,
  }
}

const ANALYSIS = { analysis: true }

// PROJECT_PLAN 6D, the design gap review's Results ADD: how stage 1 read the
// file - the date order applied, the numbers rewritten, the walk-in candidates
// left unconfirmed - from cleaning_report.json alone, saying only what stage 1
// measured (6A-6D review B1, B2).
describe('describeReading', () => {
  it('says nothing for a file that needed no reading decision', () => {
    expect(describeReading(report(), ANALYSIS)).toEqual([])
    expect(describeReading(report({ date_order: null, number_formats: {}, unconfirmed_placeholders: [] }), ANALYSIS)).toEqual([])
  })

  it("names the date order for day-month-year dates, and whether it was the user's answer or the file's proof", () => {
    expect(
      describeReading(
        report({ date_order: 'day_first', confirmations: { order_id_is_receipt: null, customer_on_first_line_only: null, dates_day_first: true } }),
        ANALYSIS,
      ),
    ).toEqual(['Dates in "Date" written like 05/01/2026 were read day first, as you answered in Review.'])
    expect(describeReading(report({ date_order: 'month_first' }), ANALYSIS)).toEqual([
      'Dates in "Date" written like 05/01/2026 were read month first, as the file\'s own dates show.',
    ])
  })

  it('counts the numbers rewritten, and gives the decimal mark to the numbers that read two ways only', () => {
    const sentences = describeReading(
      report({
        number_formats: {
          Price: { format: 'decimal_comma', rewritten: 1204, unreadable: 3, answered: true },
          Qty: { format: null, rewritten: 1, unreadable: 0, answered: false },
          Untouched: { format: null, rewritten: 0, unreadable: 0, answered: false },
        },
      }),
      ANALYSIS,
    )

    expect(sentences).toEqual([
      '1,204 numbers in "Price" were rewritten as plain numbers. Those that could be read two ways were read with a decimal comma, as you answered in Review. 3 cells in "Price" could not be read as numbers in the uploaded file.',
      '1 number in "Qty" was rewritten as a plain number.',
    ])
  })

  it("says a decimal mark the file proved is the file's, and a column with only unreadable cells", () => {
    expect(
      describeReading(report({ number_formats: { Price: { format: 'decimal_point', rewritten: 2, unreadable: 0, answered: false } } }), ANALYSIS),
    ).toEqual([
      '2 numbers in "Price" were rewritten as plain numbers. Those that could be read two ways were read with a decimal point, as the file\'s own numbers show.',
    ])
    expect(
      describeReading(report({ number_formats: { Price: { format: null, rewritten: 0, unreadable: 1, answered: false } } }), ANALYSIS),
    ).toEqual(['1 cell in "Price" could not be read as a number in the uploaded file.'])
  })

  it('lists the walk-in candidates left unconfirmed, at most five, as written', () => {
    expect(describeReading(report({ unconfirmed_placeholders: ['Guest', '<b>N/A</b>'] }), ANALYSIS)).toEqual([
      'Possible walk-in placeholders in "Buyer" that were not confirmed: "Guest", "<b>N/A</b>". They stay customers in every figure; the analysis marks them as suggested, not confirmed.',
    ])
    const many = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
    expect(describeReading(report({ unconfirmed_placeholders: many }), ANALYSIS)[0]).toBe(
      'Possible walk-in placeholders in "Buyer" that were not confirmed: "a", "b", "c", "d", "e" and 2 more. They stay customers in every figure; the analysis marks them as suggested, not confirmed.',
    )
  })

  it('words one candidate as one, and claims no analysis for a file the analysis will not read', () => {
    expect(describeReading(report({ unconfirmed_placeholders: ['Guest'] }), ANALYSIS)).toEqual([
      'A possible walk-in placeholder in "Buyer" that was not confirmed: "Guest". It stays a customer in every figure; the analysis marks it as suggested, not confirmed.',
    ])
    expect(describeReading(report({ unconfirmed_placeholders: ['Guest', 'Cash'] }), { analysis: false })).toEqual([
      'Possible walk-in placeholders in "Buyer" that were not confirmed: "Guest", "Cash". They are kept as written.',
    ])
  })

  it('clips a very long column name or value', () => {
    const long = 'x'.repeat(100)
    const sentence = describeReading(
      report({ column_mapping: { [long]: 'transaction_date' }, date_order: 'month_first' }),
      ANALYSIS,
    )[0]

    expect(sentence).toBe(`Dates in "${'x'.repeat(59)}…" written like 05/01/2026 were read month first, as the file's own dates show.`)
  })
})
