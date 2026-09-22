import { describe, expect, it } from 'vitest'
import {
  columnMeta,
  dropReason,
  formatCellValue,
  isNumeric,
  splitColumns,
} from './previewDisplay.ts'
import type { CleaningPlan, ColumnAction, PreviewResult, PreviewRow } from '../types/contracts.ts'

function column(overrides: Partial<ColumnAction> & { source_name: string }): ColumnAction {
  return {
    semantic_type: 'text',
    canonical_field: 'ignore',
    action: 'flag_only',
    params: {},
    rationale: '',
    alternatives: [],
    edited_by_user: false,
    ...overrides,
  }
}

function plan(overrides: Partial<CleaningPlan> = {}): CleaningPlan {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: [],
    ...overrides,
  }
}

function row(overrides: Partial<PreviewRow> & { row: number }): PreviewRow {
  return { before: {}, after: {}, changed: [], ...overrides }
}

describe('splitColumns', () => {
  it('shows a column with a changed cell in the sample, hides one with none', () => {
    const preview: PreviewResult = {
      rows_in_file: 10,
      sample_rows: 10,
      sampled: false,
      rows_after: 10,
      columns_after: ['a', 'b'],
      rows: [row({ row: 1, changed: ['a'] }), row({ row: 2, changed: [] })],
      deltas: [],
    }

    expect(splitColumns(preview)).toEqual({ shown: ['a'], hidden: ['b'] })
  })

  it('never marks a column changed just because some row was dropped', () => {
    // stages/ingest/preview.py: a dropped row's `changed` is always empty.
    const preview: PreviewResult = {
      rows_in_file: 10,
      sample_rows: 10,
      sampled: false,
      rows_after: 9,
      columns_after: ['qty'],
      rows: [row({ row: 1, after: null, changed: [] })],
      deltas: [],
    }

    expect(splitColumns(preview)).toEqual({ shown: [], hidden: ['qty'] })
  })
})

describe('dropReason', () => {
  it('says Duplicate when remove_exact_duplicates is planned and another row matches exactly', () => {
    const p = plan({ dataset_actions: [{ action: 'remove_exact_duplicates', params: {}, rationale: '', alternatives: [], edited_by_user: false }] })
    const kept = row({ row: 1, before: { sku: 'A1', qty: '3' } })
    const dropped = row({ row: 2, before: { sku: 'A1', qty: '3' }, after: null })

    expect(dropReason(dropped, p, [kept, dropped])).toBe('Duplicate')
  })

  it('says "No qty" when quantity is required, missing, and drop_rows_missing is its action', () => {
    const p = plan({
      column_actions: [column({ source_name: 'qty', canonical_field: 'quantity', action: 'drop_rows_missing' })],
    })
    const dropped = row({ row: 1, before: { qty: null }, after: null })

    expect(dropReason(dropped, p, [dropped])).toBe('No qty')
  })

  it('says "No name" / "No date" for the other two required fields', () => {
    const nameRow = row({ row: 1, before: { name: '' }, after: null })
    const namePlan = plan({
      column_actions: [column({ source_name: 'name', canonical_field: 'product_name', action: 'drop_rows_missing' })],
    })
    const dateRow = row({ row: 2, before: { day: null }, after: null })
    const datePlan = plan({
      column_actions: [column({ source_name: 'day', canonical_field: 'transaction_date', action: 'drop_rows_missing' })],
    })

    expect(dropReason(nameRow, namePlan, [nameRow])).toBe('No name')
    expect(dropReason(dateRow, datePlan, [dateRow])).toBe('No date')
  })

  it('prefers Duplicate over a missing required field (remove_exact_duplicates runs first)', () => {
    const p = plan({
      dataset_actions: [{ action: 'remove_exact_duplicates', params: {}, rationale: '', alternatives: [], edited_by_user: false }],
      column_actions: [column({ source_name: 'qty', canonical_field: 'quantity', action: 'drop_rows_missing' })],
    })
    const kept = row({ row: 1, before: { qty: null } })
    const dropped = row({ row: 2, before: { qty: null }, after: null })

    expect(dropReason(dropped, p, [kept, dropped])).toBe('Duplicate')
  })

  it('falls back to "Dropped" when no reason can be determined from what is on screen', () => {
    const dropped = row({ row: 1, before: { note: 'x' }, after: null })

    expect(dropReason(dropped, plan(), [dropped])).toBe('Dropped')
  })
})

describe('columnMeta', () => {
  it('maps each planned column to its semantic type and its action label', () => {
    const p = plan({
      column_actions: [column({ source_name: 'day', semantic_type: 'datetime', action: 'parse_datetime' })],
    })

    const { semanticType, actionLabel } = columnMeta(p)

    expect(semanticType.get('day')).toBe('datetime')
    expect(actionLabel.get('day')).toBe('Parse dates')
    expect(semanticType.get('__flag_x')).toBeUndefined()
  })
})

describe('isNumeric', () => {
  it('is true only for the two numeric semantic types', () => {
    expect(isNumeric('numeric_continuous')).toBe(true)
    expect(isNumeric('numeric_discrete')).toBe(true)
    expect(isNumeric('text')).toBe(false)
    expect(isNumeric(undefined)).toBe(false)
  })
})

describe('formatCellValue', () => {
  it('drops a trailing .0 on a numeric column', () => {
    expect(formatCellValue('3.0', true)).toBe('3')
    expect(formatCellValue('-2.0', true)).toBe('-2')
  })

  it('leaves a real decimal alone', () => {
    expect(formatCellValue('4.50', true)).toBe('4.50')
  })

  it('never touches a non-numeric column, even if it looks like one', () => {
    expect(formatCellValue('3.0', false)).toBe('3.0')
  })
})
