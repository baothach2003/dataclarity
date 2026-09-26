import { describe, expect, it } from 'vitest'
import { confirmedPlaceholders, formatShare, placeholderCandidates } from './customerChecks.ts'
import type { StoredPlaceholders } from './customerChecks.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  CustomerPlaceholder,
  ProfileContract,
  SchemaInferenceContract,
  TopValue,
  TransformAction,
} from '../types/contracts.ts'

// Session 2E-k (Thach): walk-in placeholders ("Guest", "Walk-in", "0").
// Review asks about each candidate; written before the code.

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
  ['Day', 'transaction_date'],
  ['Qty', 'quantity'],
  ['Price', 'unit_price'],
  ['Cust', 'customer'],
  ['Buyer', 'ignore'],
]

function plan(mapping: [string, CanonicalField][] = MAPPED, actions: Record<string, TransformAction> = {}): CleaningPlan {
  return {
    schema_version: '2.2',
    generated_at: '2026-09-26T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: mapping.map(([name, field]) => action(name, field, actions[name])),
  }
}

function profile(topValues: Record<string, TopValue[]> = {}): ProfileContract {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-26T00:00:00Z',
    dataset: { rows: 200, columns: 5, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
    columns: MAPPED.map(([name]) => ({
      name,
      dtype: 'object',
      null_count: 0,
      null_pct: 0,
      unique_count: 50,
      min: null,
      max: null,
      mean: null,
      median: null,
      q1: null,
      q3: null,
      top_values: topValues[name] ?? [],
      sample_values: [],
    })),
  }
}

const GUEST: CustomerPlaceholder = { value: 'Guest', lines: 60, lines_pct: 30, revenue_pct: 25, why: 'word' }

function schema(placeholders: CustomerPlaceholder[] = [GUEST]): SchemaInferenceContract {
  return {
    schema_version: '2.2',
    generated_at: '2026-09-26T00:00:00Z',
    model_used: 'm',
    domain_confidence: 0.9,
    domain_reasoning: 'r',
    dataset_issues: [],
    columns: MAPPED.map(([name, field]) => ({
      source_name: name,
      semantic_type: 'text',
      canonical_field: field,
      confidence: 0.9,
      issues: [],
    })),
    customer_placeholders: placeholders,
  }
}

const remapped: [string, CanonicalField][] = MAPPED.map(([name, field]) => [
  name,
  name === 'Cust' ? 'ignore' : name === 'Buyer' ? 'customer' : field,
])

describe('placeholderCandidates', () => {
  it("takes stage 1's candidates when the customer column is the one it measured", () => {
    expect(placeholderCandidates(plan(), profile(), schema())).toEqual([
      { value: 'Guest', linesPct: 30, revenuePct: 25 },
    ])
  })

  it("reads the new column's top values after a remap: a word at any share, a value at 10% or more", () => {
    const top = { Buyer: [{ value: 'ACME', count: 20 }, { value: ' walk-in ', count: 2 }, { value: 'Bob', count: 19 }] }

    expect(placeholderCandidates(plan(remapped), profile(top), schema())).toEqual([
      { value: 'ACME', linesPct: 10, revenuePct: null },
      { value: ' walk-in ', linesPct: 1, revenuePct: null },
    ])
  })

  it('has none without a customer column, or when it is dropped', () => {
    const none = MAPPED.map(([name, field]): [string, CanonicalField] => [name, field === 'customer' ? 'ignore' : field])
    expect(placeholderCandidates(plan(none), profile(), schema())).toEqual([])
    expect(placeholderCandidates(plan(MAPPED, { Cust: 'drop_column' }), profile(), schema())).toEqual([])
  })

  it("reads the profile when stage 1 could not measure the column (review cycle 1 F4)", () => {
    const top = { Cust: [{ value: 'Guest', count: 5 }] }
    expect(placeholderCandidates(plan(), profile(top), { ...schema(), customer_placeholders: null })).toEqual([
      { value: 'Guest', linesPct: 2.5, revenuePct: null },
    ])
  })

  it('matches placeholder words inside a value, zero numbers and bare marks (review cycle 1 F6)', () => {
    const spellings = ['0.0', '0000', '-', 'Cash Sale', 'Walk-In Client', 'Retail Customer', 'Ann Smith', '10023']
    const top = { Buyer: spellings.map((value) => ({ value, count: 4 })) }

    expect(placeholderCandidates(plan(remapped), profile(top), schema()).map((c) => c.value)).toEqual(
      spellings.slice(0, 6),
    )
  })

  it('mirrors the review cycle 2 words: whole words, other languages, dummy ids', () => {
    const asked = ['Khách lẻ', 'Consumidor Final', 'Público en general', 'none', '(blank)', 'N.A.', '-1']
    const notAsked = ['Walker', 'Cashmere Ltd', 'Guesthouse Ltd', 'Bigcash Ltd']
    const top = { Buyer: [...asked, ...notAsked].map((value) => ({ value, count: 2 })) }

    expect(placeholderCandidates(plan(remapped), profile(top), schema()).map((c) => c.value)).toEqual(asked)
  })

  it('asks about the largest value at four times the next one (review cycle 2 F1)', () => {
    const big = profile({ Buyer: [{ value: 'X99', count: 8 }, { value: 'A', count: 2 }] })
    const under = profile({ Buyer: [{ value: 'X99', count: 7 }, { value: 'A', count: 2 }] })

    expect(placeholderCandidates(plan(remapped), big, schema()).map((c) => c.value)).toEqual(['X99'])
    expect(placeholderCandidates(plan(remapped), under, schema())).toEqual([])
  })

  it('mirrors the review cycle 3 words: plurals, codes, underscores, more languages (F3)', () => {
    const asked = [
      'Khách hàng lẻ', 'Khách vãng lai', 'Walk-ins', 'Guests', 'Walk_In', 'CASH01', 'GUEST01', 'WALKIN1', 'Misc',
      'Non-member', 'Unregistered', 'Cliente final', 'Cliente Contado', 'Barverkauf', '散客', 'Pelanggan Umum',
    ]
    const notAsked = ['Miscellaneous Ltd', 'Guesthouse Ltd', 'Bigcash Ltd', 'Walker']
    const top = { Buyer: [...asked, ...notAsked].map((value) => ({ value, count: 2 })) }

    expect(placeholderCandidates(plan(remapped), profile(top), schema()).map((c) => c.value)).toEqual(asked)
  })

  it('takes the largest of the values not already asked about (review cycle 3 F1)', () => {
    // "Guest" is a word; "Front Desk" is 20 times the next value, under 10%.
    const top = { Buyer: [{ value: 'Guest', count: 300 }, { value: 'Front Desk', count: 80 }, { value: 'A', count: 4 }, { value: 'B', count: 4 }] }
    const large = { ...profile(top), dataset: { ...profile().dataset, rows: 5000 } }

    expect(placeholderCandidates(plan(remapped), large, schema()).map((c) => c.value)).toEqual(['Guest', 'Front Desk'])
  })

  it('takes the ratio again after each value it finds (2E-r F1)', () => {
    const top = { Buyer: [{ value: '99999', count: 560 }, { value: '88888', count: 125 }, { value: 'R1', count: 5 }, { value: 'R2', count: 5 }] }
    const large = { ...profile(top), dataset: { ...profile().dataset, rows: 5685 } }

    expect(placeholderCandidates(plan(remapped), large, schema()).map((c) => c.value)).toEqual(['99999', '88888'])
  })

  it('mirrors the 2E-r words: any separator, the Chinese default inside a name, n/a forms, NFD', () => {
    const chinese = String.fromCodePoint(0x6563, 0x5ba2)
    const asked = [
      'Retail_Customer', 'No-Customer', 'CONSUMIDOR_FINAL', 'Khach_Le', 'Retail  Customer',
      `${String.fromCodePoint(0x95e8, 0x5e97)}${chinese}`, `${chinese}${String.fromCodePoint(0x6237)}`,
      'N/A', '#n/a', 'n / a', 'Khách lẻ'.normalize('NFD'), 'Diverse', 'Laufkunden', 'Walk - In',
    ]
    const notAsked = ['Walker', 'Retailer Co', 'Nana']
    const top = { Buyer: [...asked, ...notAsked].map((value) => ({ value, count: 2 })) }

    expect(placeholderCandidates(plan(remapped), profile(top), schema()).map((c) => c.value)).toEqual(asked)
  })

  it('reads the profile when there is no schema', () => {
    const top = { Cust: [{ value: 'Guest', count: 5 }] }
    expect(placeholderCandidates(plan(), profile(top), null)).toEqual([{ value: 'Guest', linesPct: 2.5, revenuePct: null }])
  })
})

describe('formatShare', () => {
  // Review cycle 3 F7: 9.96% read "10%", the threshold it is under, and a
  // tiny share read "0.0%".
  it('floors to one decimal and never rounds up to a threshold', () => {
    expect([70, 9.96, 2.5, 0.25].map(formatShare)).toEqual(['70', '9.9', '2.5', '0.2'])
  })

  it('does not round a share just under a tenth up to it (2E-r F5)', () => {
    expect([9.9999999999, 99.99999999995].map(formatShare)).toEqual(['9.9', '99.9'])
  })

  it('keeps a whole share whole when binary arithmetic lands just under it', () => {
    // 29 of 100 lines: 100 * 0.29 is 28.999999999999996.
    expect(formatShare(100 * 0.29)).toBe('29')
  })

  it('writes a share under 0.1% as "<0.1", and nothing as 0', () => {
    expect([0.04, 0].map(formatShare)).toEqual(['<0.1', '0'])
  })
})

describe('confirmedPlaceholders', () => {
  it('sends the values answered Yes for the current customer column', () => {
    const stored: StoredPlaceholders = { guest: { value: true, column: 'Cust' } }

    expect(confirmedPlaceholders(plan(), profile(), schema(), stored)).toEqual(['Guest'])
  })

  it('drops an answer given for another column, or a No', () => {
    const top = { Buyer: [{ value: 'Guest', count: 30 }] }
    const other: StoredPlaceholders = { guest: { value: true, column: 'Cust' } }
    const no: StoredPlaceholders = { guest: { value: false, column: 'Cust' } }

    expect(confirmedPlaceholders(plan(remapped), profile(top), schema(), other)).toEqual([])
    expect(confirmedPlaceholders(plan(), profile(), schema(), no)).toEqual([])
  })
})
