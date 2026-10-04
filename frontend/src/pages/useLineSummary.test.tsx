import { act, cleanup, render, screen } from '@testing-library/react'
import { StrictMode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as runsApi from '../api/runs.ts'
import type { CleaningPlan } from '../types/contracts.ts'
import type { LineSummaryResponse } from '../types/lineSummary.ts'
import { useLineSummary } from './useLineSummary.ts'

vi.mock('../api/runs.ts', () => ({ lineSummary: vi.fn() }))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const PLAN = { column_actions: [], dataset_actions: [] } as unknown as CleaningPlan
const ANSWER = { run_id: 'r1', reserved_renames: [], summary: null, summary_unavailable_reason: 'none yet' } as unknown as LineSummaryResponse

function Probe({ runId = 'r1' }: { runId?: string }) {
  const state = useLineSummary('http://localhost:8000', runId, PLAN, true)
  return <p>{state.loading ? 'loading' : (state.response?.summary_unavailable_reason ?? 'nothing')}</p>
}

async function tick() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

// Browser check of 6B/6C (2026-10-04): StrictMode runs the effect twice in
// development; the first request was aborted in the browser but not on the
// server, which allows one whole-file summary per run - the second got 409
// summary_in_progress and the console logged it. One request, not two.
describe('useLineSummary', () => {
  it('asks the server once when Review opens, even when React runs the effect twice', async () => {
    let resolve: ((answer: LineSummaryResponse) => void) | undefined
    vi.mocked(runsApi.lineSummary).mockImplementation(
      () => new Promise((r) => { resolve = r }),
    )

    render(<StrictMode><Probe /></StrictMode>)
    expect(screen.getByText('loading')).toBeDefined()
    await act(async () => {
      resolve?.(ANSWER)
      await Promise.resolve()
    })

    expect(vi.mocked(runsApi.lineSummary)).toHaveBeenCalledTimes(1)
    expect(screen.getByText('none yet')).toBeDefined()
  })

  // The 6A-6D review (S2): a shared request must not outlive every listener -
  // a hung one would keep a later Review "adding up" forever.
  it('aborts the request once nobody listens, and asks afresh when Review opens again', async () => {
    const signals: (AbortSignal | undefined)[] = []
    vi.mocked(runsApi.lineSummary).mockImplementation((_base, _run, _plan, signal) => {
      signals.push(signal)
      return new Promise(() => undefined)
    })

    const first = render(<StrictMode><Probe runId="r2" /></StrictMode>)
    first.unmount()
    await tick()

    expect(signals).toHaveLength(1)
    expect(signals[0]?.aborted).toBe(true)

    render(<Probe runId="r2" />)
    expect(vi.mocked(runsApi.lineSummary)).toHaveBeenCalledTimes(2)
    expect(signals[1]?.aborted).toBe(false)
  })
})
