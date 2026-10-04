import { describe, expect, it } from 'vitest'
import type { ChangeLogEntry, CleaningReport } from '../types/contracts.ts'
import { buildSummaryTiles } from './resultsSummary.ts'

function report(changes: ChangeLogEntry[]): CleaningReport {
  return {
    schema_version: '4.2',
    generated_at: '2026-10-04T00:00:00Z',
    rows_in: 10,
    rows_out: 10,
    columns_in: 2,
    columns_out: 2,
    changes,
    warnings: [],
    column_mapping: {},
  }
}

const DEDUPE: ChangeLogEntry = {
  action: 'remove_exact_duplicates',
  column: null,
  cells_affected: 0,
  rows_affected: 0,
  params: {},
  detail: 'removed 0 exact-duplicate rows',
}

// The design gap review's Results CHANGE: the AI never proposes removing exact
// copies (2E-u4) - "Duplicates removed 0" when nobody asked would read as "the
// file has none". The tile appears only when the plan ran the action.
describe('buildSummaryTiles', () => {
  it('has no duplicates tile when the plan did not remove exact copies', () => {
    expect(buildSummaryTiles(report([])).map((t) => t.label)).not.toContain('Duplicates removed')
  })

  it('shows the duplicates tile, even at 0, when the plan removed exact copies', () => {
    const tile = buildSummaryTiles(report([DEDUPE])).find((t) => t.label === 'Duplicates removed')
    expect(tile?.value).toBe(0)
  })
})
