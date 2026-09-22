import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { PreviewPane } from './PreviewPane.tsx'
import type { CleaningPlan, ColumnAction, PreviewResult } from '../types/contracts.ts'

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

function makePlan(): CleaningPlan {
  return {
    schema_version: '1.0',
    generated_at: '2026-09-22T00:00:00Z',
    source: 'ai',
    dataset_actions: [],
    column_actions: [
      column({ source_name: 'day', semantic_type: 'datetime', canonical_field: 'transaction_date', action: 'parse_datetime' }),
      column({ source_name: 'qty', semantic_type: 'numeric_discrete', canonical_field: 'quantity', action: 'drop_rows_missing' }),
      column({ source_name: 'note', semantic_type: 'text', canonical_field: 'note', action: 'flag_only' }),
    ],
  }
}

function makePreview(): PreviewResult {
  return {
    rows_in_file: 12480,
    sample_rows: 500,
    sampled: true,
    rows_after: 12301,
    columns_after: ['day', 'qty', 'note'],
    rows: [
      {
        row: 118,
        before: { day: '04 Apr 2026', qty: '3.0', note: 'ok' },
        after: { day: '2026-04-04', qty: '3', note: 'ok' },
        changed: ['day'],
      },
      {
        row: 241,
        before: { day: '03/04/2024', qty: null, note: 'x' },
        after: null,
        changed: [],
      },
    ],
    deltas: [],
  }
}

afterEach(() => {
  cleanup()
})

describe('PreviewPane', () => {
  it('shows only columns changed in the sample, and names the hidden ones', () => {
    render(<PreviewPane preview={makePreview()} loading={false} plan={makePlan()} />)

    expect(screen.getByRole('columnheader', { name: 'day' })).toBeDefined()
    expect(screen.queryByRole('columnheader', { name: 'note' })).toBeNull()
    expect(screen.getByText('Hidden: qty, note (no changes in sample)')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Show unchanged columns (2)' })).toBeDefined()
  })

  it('appends the hidden columns after the changed ones once toggled open', () => {
    render(<PreviewPane preview={makePreview()} loading={false} plan={makePlan()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Show unchanged columns (2)' }))

    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual(['Row', 'day', 'qty', 'note'])
    expect(screen.getByRole('button', { name: 'Hide unchanged columns' })).toBeDefined()
  })

  it('strikes through a dropped row and gives it a reason derived from the plan', () => {
    render(<PreviewPane preview={makePreview()} loading={false} plan={makePlan()} />)

    // qty is required (maps to quantity) and its action is drop_rows_missing;
    // row 241's before value for qty is null.
    expect(screen.getByText('No qty')).toBeDefined()
    expect(screen.getByText('03/04/2024')).toBeDefined() // before value shown struck through
  })

  it('marks a changed cell with a keyboard-focusable tooltip naming the before value and the action', () => {
    render(<PreviewPane preview={makePreview()} loading={false} plan={makePlan()} />)

    const trigger = screen.getByText('2026-04-04').closest('[tabindex="0"]')
    if (!(trigger instanceof HTMLElement)) {
      throw new Error('expected a focusable tooltip trigger around the changed cell')
    }
    expect(trigger.getAttribute('tabindex')).toBe('0')
    const tooltipId = trigger.getAttribute('aria-describedby')
    expect(tooltipId).toBeTruthy()

    trigger.focus()

    const tooltip = document.getElementById(tooltipId ?? '')
    expect(tooltip?.textContent).toContain('Before: 04 Apr 2026')
    expect(tooltip?.textContent).toContain('Parse dates')
  })

  it('drops a trailing .0 on a numeric cell and right-aligns numeric columns', () => {
    render(<PreviewPane preview={makePreview()} loading={false} plan={makePlan()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Show unchanged columns (2)' }))

    expect(screen.getByText('3')).toBeDefined()
    expect(screen.queryByText('3.0')).toBeNull()
    expect(screen.getByRole('columnheader', { name: 'qty' }).className).toContain('preview-table--numeric')
  })

  it('shows the projected full-file row count, not the sample size', () => {
    render(<PreviewPane preview={makePreview()} loading={false} plan={makePlan()} />)

    expect(screen.getByText(/Rows 12,480 → 12,301 \(full file, projected\)/)).toBeDefined()
    expect(screen.getByText('2 of 500 sampled rows · 1 of 3 columns changed')).toBeDefined()
  })
})
