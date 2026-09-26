import { describe, expect, it } from 'vitest'
import { answeredLineClasses, nonProductCandidates } from './lineClasses.ts'
import type { StoredLineClasses } from './lineClasses.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  NonProductCandidate,
  ProfileContract,
  SchemaInferenceContract,
  TopValue,
  TransformAction,
} from '../types/contracts.ts'

// Session 2E-d2 (Thach): lines that may not be products - postage, fees,
// discounts, accounting adjustments. Stage 1 proposes; the user classes each
// in Review; unanswered, a line stays a product. Written before the code.

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
  ['Code', 'sku'],
  ['Item', 'product_name'],
  ['Other', 'ignore'],
]

function plan(mapping: [string, CanonicalField][] = MAPPED, actions: Record<string, TransformAction> = {}): CleaningPlan {
  return {
    schema_version: '2.3',
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
    dataset: { rows: 1000, columns: 6, duplicate_rows: 0, missing_cells_pct: 0, encoding_used: 'utf-8', delimiter: ',' },
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

const POST: NonProductCandidate = {
  value: 'POST',
  field: 'sku',
  name: 'POSTAGE',
  lines: 2122,
  positive: 127597.42,
  negative: -15256.42,
  suggested: 'charge',
  word: 'postage',
}

function schema(candidates: NonProductCandidate[] | null = [POST]): SchemaInferenceContract {
  return {
    schema_version: '2.3',
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
    non_product_candidates: candidates,
  }
}

// The SKU moved to another column: stage 1's candidates were for "Code".
const remapped: [string, CanonicalField][] = MAPPED.map(([name, field]) => [
  name,
  name === 'Code' ? 'ignore' : name === 'Other' ? 'sku' : field,
])

describe('nonProductCandidates', () => {
  it("takes stage 1's candidates when the product columns are the ones it measured", () => {
    expect(nonProductCandidates(plan(), profile(), schema())).toEqual([
      {
        key: 'sku:post',
        value: 'POST',
        field: 'sku',
        name: 'POSTAGE',
        lines: 2122,
        positive: 127597.42,
        negative: -15256.42,
        suggested: 'charge',
      },
    ])
  })

  it("reads the new SKU column's top values after a remap, first or last word only", () => {
    const top = {
      Other: [
        { value: 'BANK CHARGES', count: 90 },
        { value: 'FRENCH CARRIAGE LANTERN', count: 60 },
        { value: 'Next Day Carriage', count: 40 },
        { value: 'SAMPLES', count: 20 },
        { value: '85123A', count: 10 },
      ],
    }

    expect(nonProductCandidates(plan(remapped), profile(top), schema())).toEqual([
      { key: 'sku:bank charges', value: 'BANK CHARGES', field: 'sku', name: null, lines: 90, positive: null, negative: null, suggested: 'cost' },
      { key: 'sku:next day carriage', value: 'Next Day Carriage', field: 'sku', name: null, lines: 40, positive: null, negative: null, suggested: 'charge' },
      { key: 'sku:samples', value: 'SAMPLES', field: 'sku', name: null, lines: 20, positive: null, negative: null, suggested: null },
    ])
  })

  it('reads a value as stage 1 does: an invisible character is no character (mutation check F7)', () => {
    const zeroWidth = String.fromCodePoint(0x200b)
    const top = { Other: [{ value: `BANK${zeroWidth} CHARGES`, count: 9 }] }

    expect(nonProductCandidates(plan(remapped), profile(top), schema()).map((c) => [c.key, c.suggested])).toEqual([
      ['sku:bank charges', 'cost'],
    ])
  })

  it("keeps stage 1's SKU candidates when only the name column is remapped (review F4)", () => {
    const nameRemapped: [string, CanonicalField][] = MAPPED.map(([name, field]) => [
      name,
      name === 'Item' ? 'ignore' : name === 'Other' ? 'product_name' : field,
    ])
    const stored: StoredLineClasses = { 'sku:post': { value: 'charge', column: 'Code' } }

    expect(nonProductCandidates(plan(nameRemapped), profile(), schema()).map((c) => c.key)).toEqual(['sku:post'])
    expect(answeredLineClasses(plan(nameRemapped), profile(), schema(), stored)).toEqual([
      { value: 'POST', field: 'sku', line_class: 'charge' },
    ])
  })

  it('does not read roses as a commission (review F7)', () => {
    const top = { Other: [{ value: 'Hoa hồng đỏ', count: 30 }, { value: 'Bó hoa hồng', count: 20 }] }

    expect(nonProductCandidates(plan(remapped), profile(top), schema())).toEqual([])
  })

  it('asks once about profile values that read the same (review F12)', () => {
    const top = { Other: [{ value: 'POSTAGE', count: 30 }, { value: 'Postage ', count: 5 }] }

    expect(nonProductCandidates(plan(remapped), profile(top), schema()).map((c) => [c.key, c.value, c.lines])).toEqual([
      ['sku:postage', 'POSTAGE', 35],
    ])
  })

  it('reads the name column when no SKU is mapped', () => {
    const noSku: [string, CanonicalField][] = MAPPED.map(([name, field]) => [name, field === 'sku' ? 'ignore' : field])
    const top = { Item: [{ value: 'Adjust bad debt', count: 6 }, { value: 'Discount', count: 3 }] }

    expect(nonProductCandidates(plan(noSku), profile(top), schema()).map((c) => [c.key, c.field, c.suggested])).toEqual([
      ['product_name:adjust bad debt', 'product_name', 'adjustment'],
      ['product_name:discount', 'product_name', 'discount'],
    ])
  })

  it("reads the profile when stage 1 could not measure", () => {
    const top = { Code: [{ value: 'AMAZONFEE', count: 5 }, { value: 'CRUK Commission', count: 4 }] }

    expect(nonProductCandidates(plan(), profile(top), schema(null)).map((c) => c.value)).toEqual(['CRUK Commission'])
  })

  it('has none without a product column, or when both are dropped', () => {
    const none: [string, CanonicalField][] = MAPPED.map(([name, field]) => [
      name,
      field === 'sku' || field === 'product_name' ? 'ignore' : field,
    ])
    expect(nonProductCandidates(plan(none), profile(), schema())).toEqual([])
    expect(nonProductCandidates(plan(MAPPED, { Code: 'drop_column', Item: 'drop_column' }), profile(), schema())).toEqual([])
  })
})

describe('answeredLineClasses', () => {
  it('sends each class answered for the current product column', () => {
    const stored: StoredLineClasses = { 'sku:post': { value: 'charge', column: 'Code' } }

    expect(answeredLineClasses(plan(), profile(), schema(), stored)).toEqual([
      { value: 'POST', field: 'sku', line_class: 'charge' },
    ])
  })

  it('sends nothing for "a product", for no answer, or for an answer given for another column', () => {
    const product: StoredLineClasses = { 'sku:post': { value: 'product', column: 'Code' } }
    const other: StoredLineClasses = { 'sku:post': { value: 'charge', column: 'Other' } }

    expect(answeredLineClasses(plan(), profile(), schema(), product)).toEqual([])
    expect(answeredLineClasses(plan(), profile(), schema(), {})).toEqual([])
    expect(answeredLineClasses(plan(), profile(), schema(), other)).toEqual([])
  })
})
