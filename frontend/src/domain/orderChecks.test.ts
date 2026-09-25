import { describe, expect, it } from 'vitest'
import {
  NO_ANSWERS,
  answerKey,
  applicableAnswers,
  blankOrderIds,
  fillQuestion,
  needsReceiptConfirmation,
  withApplicableConfirmations,
} from './orderChecks.ts'
import type { StoredAnswers } from './orderChecks.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  ColumnProfile,
  ProfileContract,
  SchemaInferenceContract,
  TransformAction,
} from '../types/contracts.ts'

// Session 2E-e2 (Thach): what the Review screen asks about orders, written
// before the code; the API since doubt-review cycle 1 (answers remember the
// mapping they were given for, dropped columns are unmapped, a customer
// column that names nobody is no customer column).

function action(source_name: string, canonical_field: CanonicalField, act: TransformAction = 'flag_only'): ColumnAction {
  return {
    source_name,
    semantic_type: 'text',
    canonical_field,
    action: act,
    params: {},
    rationale: '',
    alternatives: [],
    edited_by_user: false,
  }
}

const MAPPED: [string, CanonicalField][] = [
  ['Inv', 'order_id'],
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Cust', 'customer'],
  ['Item', 'product_name'],
]

function plan(mapping: [string, CanonicalField][] = MAPPED, actions: Record<string, TransformAction> = {}): CleaningPlan {
  return {
    schema_version: '2.1',
    generated_at: '2026-09-26T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: mapping.map(([name, field]) => action(name, field, actions[name])),
  }
}

function profileColumn(name: string, null_count: number, unique_count = 10): ColumnProfile {
  return {
    name,
    dtype: 'object',
    null_count,
    null_pct: 0,
    unique_count,
    min: null,
    max: null,
    mean: null,
    median: null,
    q1: null,
    q3: null,
    top_values: [],
    sample_values: [],
  }
}

function profile(blankIds = 0, blankCustomers = 0, distinctCustomers = 10): ProfileContract {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-26T00:00:00Z',
    dataset: { rows: 100, columns: 6, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
    columns: [...MAPPED.map(([name]) => name), 'Batch', 'Buyer'].map((name) =>
      profileColumn(
        name,
        name === 'Inv' ? blankIds : name === 'Cust' ? blankCustomers : 0,
        name === 'Cust' ? distinctCustomers : 10,
      ),
    ),
  }
}

function schema(receiptFillLines: number | null, mapping: [string, CanonicalField][] = MAPPED): SchemaInferenceContract {
  return {
    schema_version: '2.1',
    generated_at: '2026-09-26T00:00:00Z',
    model_used: 'm',
    domain_confidence: 0.9,
    domain_reasoning: 'r',
    dataset_issues: [],
    columns: mapping.map(([name, field]) => ({
      source_name: name,
      semantic_type: 'text',
      canonical_field: field,
      confidence: 0.9,
      issues: [],
    })),
    receipt_fill_lines: receiptFillLines,
  }
}

const withoutCustomer = MAPPED.map(([name, field]): [string, CanonicalField] => [
  name,
  field === 'customer' ? 'ignore' : field,
])

describe('blankOrderIds', () => {
  it('counts the blank cells of the column mapped to order_id on the raw file', () => {
    expect(blankOrderIds(plan(), profile(7))).toEqual({ column: 'Inv', count: 7 })
  })

  it('is null when no id is blank or no column is mapped to order_id', () => {
    expect(blankOrderIds(plan(), profile(0))).toBeNull()
    const noOrderId = MAPPED.filter(([, field]) => field !== 'order_id')
    expect(blankOrderIds(plan(noOrderId), profile(7))).toBeNull()
  })

  it('is null when the order id column is dropped (review K)', () => {
    expect(blankOrderIds(plan(MAPPED, { Inv: 'drop_column' }), profile(7))).toBeNull()
  })
})

describe('needsReceiptConfirmation', () => {
  it('names the order id column when there is no customer column', () => {
    expect(needsReceiptConfirmation(plan(withoutCustomer), profile())).toBe('Inv')
  })

  it('is null with a customer column, or with no order id', () => {
    expect(needsReceiptConfirmation(plan(), profile())).toBeNull()
    const noOrderId = withoutCustomer.filter(([, field]) => field !== 'order_id')
    expect(needsReceiptConfirmation(plan(noOrderId), profile())).toBeNull()
  })

  it('asks when the customer column is dropped (review E)', () => {
    expect(needsReceiptConfirmation(plan(MAPPED, { Cust: 'drop_column' }), profile())).toBe('Inv')
  })

  it('asks when the customer column names nobody (review C)', () => {
    expect(needsReceiptConfirmation(plan(), profile(0, 100))).toBe('Inv')
  })

  it('asks when the customer column never names two different customers (cycle 2 F4)', () => {
    // "Walk-in" on every line gives the check no customer to read.
    expect(needsReceiptConfirmation(plan(), profile(0, 0, 1))).toBe('Inv')
  })

  it('does not ask about a dropped order id column (review K)', () => {
    expect(needsReceiptConfirmation(plan(withoutCustomer, { Inv: 'drop_column' }), profile())).toBeNull()
  })
})

describe('fillQuestion', () => {
  it('asks with the count when stage 1 measured a fill on this mapping', () => {
    expect(fillQuestion(plan(), schema(12), profile())).toEqual({ lines: 12 })
  })

  it('does not ask when stage 1 measured no fill on this mapping', () => {
    expect(fillQuestion(plan(), schema(0), profile())).toBeNull()
  })

  it('does not ask without an order id and a customer who is named', () => {
    expect(fillQuestion(plan(withoutCustomer), schema(12), profile())).toBeNull()
    expect(fillQuestion(plan(), schema(12), profile(0, 100))).toBeNull()
  })

  it('asks without a count when the user remapped a field the measure read', () => {
    const remapped = MAPPED.map(([name, field]): [string, CanonicalField] => [
      name,
      name === 'Cust' ? 'ignore' : field,
    ])
    remapped.push(['Buyer', 'customer'])
    expect(fillQuestion(plan(remapped), schema(0), profile())).toEqual({ lines: null })
  })

  it('ignores a remapped field the measure does not read', () => {
    const renamed = MAPPED.map(([name, field]): [string, CanonicalField] => [
      name,
      name === 'Item' ? 'ignore' : field,
    ])
    expect(fillQuestion(plan(renamed), schema(0), profile())).toBeNull()
  })

  it('asks without a count when there is no schema at all', () => {
    expect(fillQuestion(plan(), null, profile())).toEqual({ lines: null })
  })

  it('asks without a count when stage 1 could not measure the fill (cycle 2 F5)', () => {
    expect(fillQuestion(plan(), schema(null), profile())).toEqual({ lines: null })
  })

  it('does not ask when the plan imputes the customer column: nothing is left to fill (cycle 2 F11)', () => {
    expect(fillQuestion(plan(MAPPED, { Cust: 'impute_constant' }), schema(12), profile())).toBeNull()
  })

  it('does not ask about lines the plan deletes (cycle 3 F5)', () => {
    expect(fillQuestion(plan(MAPPED, { Cust: 'drop_rows_missing' }), schema(12), profile())).toBeNull()
  })

  it('asks without a count once the blank-id lines are dropped (review D)', () => {
    // Measured on the raw file, any blank id made the file count lines, so
    // the fill read 0; without those lines it may happen.
    expect(fillQuestion(plan(MAPPED, { Inv: 'drop_rows_missing' }), schema(0), profile(3))).toEqual({ lines: null })
  })
})

describe('answers', () => {
  const yesToBoth: StoredAnswers = {
    order_id_is_receipt: { value: true, key: answerKey(plan(withoutCustomer), 'order_id_is_receipt') },
    customer_on_first_line_only: { value: false, key: answerKey(plan(), 'customer_on_first_line_only') },
  }

  it('sends only the answers to questions that apply, and none unanswered', () => {
    expect(applicableAnswers(plan(), schema(3), profile(), yesToBoth)).toEqual({
      order_id_is_receipt: null,
      customer_on_first_line_only: false,
    })
    expect(withApplicableConfirmations(plan(), schema(3), profile(), NO_ANSWERS).confirmations).toEqual({
      order_id_is_receipt: null,
      customer_on_first_line_only: null,
    })
  })

  it('drops a fill answer once the question is gone on the same columns (mutation check F3)', () => {
    // Answered while the blank-id lines were being dropped, then kept: the
    // raw file counts lines, no fill happens, and nothing was asked.
    const whileDropping = plan(MAPPED, { Inv: 'drop_rows_missing' })
    const stored: StoredAnswers = {
      order_id_is_receipt: null,
      customer_on_first_line_only: { value: false, key: answerKey(whileDropping, 'customer_on_first_line_only') },
    }

    expect(applicableAnswers(whileDropping, schema(0), profile(3), stored).customer_on_first_line_only).toBe(false)
    expect(applicableAnswers(plan(), schema(0), profile(3), stored).customer_on_first_line_only).toBeNull()
  })

  it('keeps a No about the same column after a customer column is mapped (cycle 3 F2)', () => {
    const no: StoredAnswers = {
      order_id_is_receipt: { value: false, key: answerKey(plan(withoutCustomer), 'order_id_is_receipt') },
      customer_on_first_line_only: null,
    }

    expect(applicableAnswers(plan(), schema(0), profile(), no).order_id_is_receipt).toBe(false)
  })

  it('keeps the receipt answer where there is no customer column', () => {
    expect(applicableAnswers(plan(withoutCustomer), schema(3), profile(), yesToBoth)).toEqual({
      order_id_is_receipt: true,
      customer_on_first_line_only: null,
    })
  })

  it('drops an answer given for another column (review B)', () => {
    const batch: [string, CanonicalField][] = withoutCustomer.map(([name, field]) => [
      name === 'Inv' ? 'Batch' : name,
      field,
    ])
    expect(applicableAnswers(plan(batch), schema(3), profile(), yesToBoth).order_id_is_receipt).toBeNull()

    const otherCustomer: [string, CanonicalField][] = MAPPED.map(([name, field]) => [
      name === 'Inv' ? 'Batch' : name,
      field,
    ])
    expect(
      applicableAnswers(plan(otherCustomer), schema(3), profile(), yesToBoth).customer_on_first_line_only,
    ).toBeNull()
  })
})
