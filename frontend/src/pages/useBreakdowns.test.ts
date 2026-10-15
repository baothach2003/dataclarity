import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useBreakdowns } from './useBreakdowns.ts'
import * as runsApi from '../api/runs.ts'
import type { CleaningPlan, ColumnAction } from '../types/contracts.ts'

// Thach's Q3-Q5 (2026-10-15): which columns can split sales is read on the plan's LINES, so every step and answer
// of the plan matters - not only a column's field, type or drop. The server's answer is faked.

vi.mock('../api/runs.ts', () => ({ breakdownQuestion: vi.fn() }))

function action(name: string, field: ColumnAction['canonical_field']): ColumnAction {
  return { source_name: name, semantic_type: 'text', canonical_field: field, action: 'flag_only', params: {}, rationale: '', alternatives: [], edited_by_user: false }
}

const PLAN: CleaningPlan = {
  schema_version: '4.4',
  generated_at: '2026-10-15T00:00:00Z',
  source: 'ai',
  dataset_actions: [],
  column_actions: [action('Day', 'transaction_date'), action('Store', 'ignore')],
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useBreakdowns', () => {
  it('asks again when a step or an answer of the plan changes, not only a column field', async () => {
    const ask = vi.mocked(runsApi.breakdownQuestion).mockResolvedValue({
      run_id: 'run-1', question: { eligible: [], suggested: [], status: 'none_eligible', message: 'm' },
    })
    const { rerender } = renderHook(({ plan }) => useBreakdowns('http://x', 'run-1', plan, true), {
      initialProps: { plan: PLAN },
    })
    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(1)
    })
    const deduplicated: CleaningPlan = {
      ...PLAN,
      dataset_actions: [{ action: 'remove_exact_duplicates', params: {}, rationale: '', alternatives: [], edited_by_user: true }],
    }
    rerender({ plan: deduplicated })
    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(2)
    })
    rerender({ plan: { ...deduplicated, confirmations: { order_id_is_receipt: true, customer_on_first_line_only: null } } })
    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(3)
    })
    // The same plan again (a new object): no new ask.
    rerender({ plan: { ...deduplicated, confirmations: { order_id_is_receipt: true, customer_on_first_line_only: null } } })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(ask).toHaveBeenCalledTimes(3)
  })
})

describe('useBreakdowns: the doubt review of Q3-Q5', () => {
  it('R1: an edit keeps the columns selected while stage 1 measures again - never dropped unseen', async () => {
    const ask = vi
      .mocked(runsApi.breakdownQuestion)
      .mockResolvedValueOnce({
        run_id: 'run-1',
        question: { eligible: [{ column: 'Store', values: ['A', 'B'] }], suggested: ['Store'], status: 'chosen', message: 'm' },
      })
      .mockReturnValue(new Promise(() => undefined))
    const { result, rerender } = renderHook(({ plan }) => useBreakdowns('http://x', 'run-1', plan, true), {
      initialProps: { plan: PLAN },
    })
    await waitFor(() => {
      expect(result.current.selected).toEqual(['Store'])
    })
    rerender({ plan: { ...PLAN, dataset_actions: [{ action: 'remove_exact_duplicates', params: {}, rationale: '', alternatives: [], edited_by_user: true }] } })
    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(2)
    })
    expect(result.current.loading).toBe(true)
    expect(result.current.stale).toBe(true)
    expect(result.current.selected).toEqual(['Store'])
  })

  it('R2: edits in quick succession ask once, after the last', async () => {
    const ask = vi.mocked(runsApi.breakdownQuestion).mockResolvedValue({
      run_id: 'run-1', question: { eligible: [], suggested: [], status: 'none_eligible', message: 'm' },
    })
    const { rerender } = renderHook(({ plan }) => useBreakdowns('http://x', 'run-1', plan, true), {
      initialProps: { plan: PLAN },
    })
    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(1)
    })
    for (const value of ['U', 'Un', 'Unk']) {
      rerender({ plan: { ...PLAN, column_actions: [PLAN.column_actions[0], { ...PLAN.column_actions[1], params: { value } }] } })
    }
    await waitFor(() => {
      expect(ask).toHaveBeenCalledTimes(2)
    })
    await new Promise((resolve) => setTimeout(resolve, 600))
    expect(ask).toHaveBeenCalledTimes(2)
    expect(ask.mock.calls[1][2].column_actions[1].params).toEqual({ value: 'Unk' })
  })
})

describe('useBreakdowns: the scoped review of the fixes', () => {
  it('#2: a column the same edit drops or maps is never sent, even while the answer is the last one', async () => {
    vi.mocked(runsApi.breakdownQuestion)
      .mockResolvedValueOnce({
        run_id: 'run-1',
        question: { eligible: [{ column: 'Store', values: ['A', 'B'] }], suggested: ['Store'], status: 'chosen', message: 'm' },
      })
      .mockReturnValue(new Promise(() => undefined))
    const { result, rerender } = renderHook(({ plan }) => useBreakdowns('http://x', 'run-1', plan, true), {
      initialProps: { plan: PLAN },
    })
    await waitFor(() => {
      expect(result.current.selected).toEqual(['Store'])
    })
    rerender({ plan: { ...PLAN, column_actions: [PLAN.column_actions[0], { ...PLAN.column_actions[1], action: 'drop_column' }] } })
    expect(result.current.selected).toEqual([])
    rerender({ plan: { ...PLAN, column_actions: [PLAN.column_actions[0], { ...PLAN.column_actions[1], canonical_field: 'category' }] } })
    expect(result.current.selected).toEqual([])
  })
})
