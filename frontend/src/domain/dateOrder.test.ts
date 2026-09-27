import { describe, expect, it } from 'vitest'
import { appliedOrder, applicableDateAnswer, dateQuestion, parseConflict } from './dateOrder.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  DateOrderMeasure,
  Params,
  ProfileContract,
  TransformAction,
} from '../types/contracts.ts'

// Session 2E-j (Thach): how the date column's day-month-year cells are
// written is decided at stage 1 - the file's proof (profile.json, per
// column), else the user's answer in Review. Written before the code.

const AMBIGUOUS: DateOrderMeasure = {
  shaped: 3,
  day_first: 0,
  month_first: 0,
  ambiguous: 3,
  day_first_example: null,
  month_first_example: null,
  decision: 'ask',
  hint: null,
}
const DAY_FIRST: DateOrderMeasure = {
  ...AMBIGUOUS,
  day_first: 1,
  ambiguous: 2,
  day_first_example: '13/01/2026',
  decision: 'day_first',
}
const ALL_DAY_FIRST: DateOrderMeasure = { ...DAY_FIRST, shaped: 1, ambiguous: 0 }

function action(name: string, field: CanonicalField, act: TransformAction = 'flag_only', params: Params = {}): ColumnAction {
  return {
    source_name: name,
    semantic_type: 'text',
    canonical_field: field,
    action: act,
    params,
    rationale: '',
    alternatives: [],
    edited_by_user: false,
  }
}

function plan(day: ColumnAction = action('Day', 'transaction_date')): CleaningPlan {
  return {
    schema_version: '3.1',
    generated_at: '2026-09-27T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: [day, action('Other', 'ignore'), action('Qty', 'quantity')],
  }
}

function profile(day: DateOrderMeasure | null, other: DateOrderMeasure | null = null): ProfileContract {
  const column = (name: string, measure: DateOrderMeasure | null) => ({
    name,
    dtype: 'str',
    null_count: 0,
    null_pct: 0,
    unique_count: 3,
    min: null,
    max: null,
    mean: null,
    median: null,
    q1: null,
    q3: null,
    top_values: [],
    sample_values: [],
    date_order: measure,
  })
  return {
    schema_version: '1.1',
    generated_at: '2026-09-27T00:00:00Z',
    dataset: { rows: 3, columns: 3, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
    columns: [column('Day', day), column('Other', other), column('Qty', null)],
  }
}

describe('dateQuestion', () => {
  it('asks when the date column proves neither order', () => {
    expect(dateQuestion(plan(), profile(AMBIGUOUS))).toEqual({ column: 'Day', measure: AMBIGUOUS })
  })

  it('does not ask when the file proves the order, or has no such date', () => {
    expect(dateQuestion(plan(), profile(DAY_FIRST))).toBeNull()
    expect(dateQuestion(plan(), profile(null))).toBeNull()
  })

  it("reads the mapped column's own measure: a remap asks about the new column", () => {
    const remapped: CleaningPlan = {
      ...plan(action('Day', 'ignore')),
      column_actions: [action('Day', 'ignore'), action('Other', 'transaction_date'), action('Qty', 'quantity')],
    }

    expect(dateQuestion(remapped, profile(DAY_FIRST, AMBIGUOUS))).toEqual({ column: 'Other', measure: AMBIGUOUS })
  })

  it('asks nothing when the date column is dropped or not mapped', () => {
    expect(dateQuestion(plan(action('Day', 'transaction_date', 'drop_column')), profile(AMBIGUOUS))).toBeNull()
    expect(dateQuestion(plan(action('Day', 'ignore')), profile(AMBIGUOUS))).toBeNull()
  })
})

describe('applicableDateAnswer and appliedOrder', () => {
  it('keeps an answer only for the column it was given for, while asked', () => {
    expect(applicableDateAnswer(plan(), profile(AMBIGUOUS), { value: true, column: 'Day' })).toBe(true)
    expect(applicableDateAnswer(plan(), profile(AMBIGUOUS), { value: true, column: 'Other' })).toBeNull()
    expect(applicableDateAnswer(plan(), profile(DAY_FIRST), { value: false, column: 'Day' })).toBeNull()
    expect(applicableDateAnswer(plan(), profile(AMBIGUOUS), null)).toBeNull()
  })

  it('is the answer, else the proof', () => {
    expect(appliedOrder(plan(), profile(AMBIGUOUS), true)).toBe('day_first')
    expect(appliedOrder(plan(), profile(AMBIGUOUS), false)).toBe('month_first')
    expect(appliedOrder(plan(), profile(AMBIGUOUS), null)).toBeNull()
    expect(appliedOrder(plan(), profile(DAY_FIRST), null)).toBe('day_first')
    expect(appliedOrder(plan(), profile(null), null)).toBeNull()
  })
})

describe('parseConflict', () => {
  const parse = (params: Params) => plan(action('Day', 'transaction_date', 'parse_datetime', params))

  it('finds a parse step reading month first when the dates are day first', () => {
    expect(parseConflict(parse({}), profile(AMBIGUOUS), true)).toEqual({
      column: 'Day',
      order: 'day_first',
      fix: { dayfirst: true },
    })
    expect(parseConflict(parse({ format: '%m/%d/%Y' }), profile(DAY_FIRST), null)?.order).toBe('day_first')
  })

  it('finds dayfirst on month-first dates', () => {
    expect(parseConflict(parse({ dayfirst: true }), profile(AMBIGUOUS), false)).toEqual({
      column: 'Day',
      order: 'month_first',
      fix: {},
    })
  })

  it('finds nothing when the step reads as the order does', () => {
    expect(parseConflict(parse({ dayfirst: true }), profile(AMBIGUOUS), true)).toBeNull()
    expect(parseConflict(parse({ format: '%d.%m.%Y' }), profile(DAY_FIRST), null)).toBeNull()
    expect(parseConflict(parse({}), profile(AMBIGUOUS), false)).toBeNull()
    expect(parseConflict(plan(), profile(AMBIGUOUS), true)).toBeNull()
  })

  it('finds nothing when every such date proves day first: per cell, pandas reads them right', () => {
    expect(parseConflict(parse({}), profile(ALL_DAY_FIRST), null)).toBeNull()
  })

  // A file holding both proofs, answered (mutation check).
  const BOTH: DateOrderMeasure = {
    ...AMBIGUOUS,
    shaped: 2,
    day_first: 1,
    month_first: 1,
    ambiguous: 0,
    day_first_example: '13/01/2026',
    month_first_example: '01/13/2026',
  }

  it('finds a per-cell step on a day-first answer when a date proves month first', () => {
    // Per cell, pandas reads 01/13/2026 as 13 January; read day first it is no date.
    expect(parseConflict(parse({}), profile(BOTH), true)).toEqual({ column: 'Day', order: 'day_first', fix: { dayfirst: true } })
  })

  it('finds dayfirst on a month-first answer when a date proves day first, and needs a format to fix', () => {
    expect(parseConflict(parse({ dayfirst: true }), profile(BOTH), false)).toEqual({
      column: 'Day',
      order: 'month_first',
      fix: null,
    })
  })

  it('finds a format reading the proven other way even with no ambiguous cell (review cycle 1 #8)', () => {
    // 01/13/2026 read by %m/%d/%Y is 13 January; answered day first it is no date.
    expect(parseConflict(parse({ format: '%m/%d/%Y' }), profile(BOTH), true)?.order).toBe('day_first')
  })

  it('finds nothing for a year-first format: it never reads such a date (review cycle 1 #8)', () => {
    expect(parseConflict(parse({ format: '%Y-%m-%d' }), profile(DAY_FIRST), null)).toBeNull()
  })

  it('drops the format that read the other way', () => {
    expect(parseConflict(parse({ format: '%m/%d/%Y' }), profile(AMBIGUOUS), true)?.fix).toEqual({ dayfirst: true })
  })
})
