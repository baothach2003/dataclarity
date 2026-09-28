// Review's whole-file view of the line taxonomy (session 2E-t3). Stage 1 reads
// the whole file for it - seconds on a large one, and nothing stops the server
// once asked - so it is asked once when Review opens and then when the user
// asks again, never on every edit (review 1 #1: answers piled up minutes of
// work). An answer for an earlier plan stays on screen, marked as such.

import { useEffect, useState } from 'react'
import { lineSummary } from '../api/runs.ts'
import type { CleaningPlan } from '../types/contracts.ts'
import type { LineSummaryResponse } from '../types/lineSummary.ts'

export interface LineSummaryState {
  response: LineSummaryResponse | null
  loading: boolean
  // The plan or its answers changed since the answer shown - also when a
  // later ask failed and the earlier answer is still what is shown.
  stale: boolean
  error: unknown
  refresh: () => void
}

// One request: the plan as sent. A new object for every ask, so asking again
// for the same plan (after an error) is a new request.
interface Ask {
  body: string
}

interface Answer {
  body: string
  response: LineSummaryResponse
}

export function useLineSummary(baseUrl: string, runId: string, plan: CleaningPlan, enabled: boolean): LineSummaryState {
  // The answers are applied to a fresh object on every render: a request
  // follows the plan's content, not its identity.
  const body = JSON.stringify(plan)
  const [requested, setRequested] = useState<Ask | null>(() => (enabled ? { body } : null))
  const [settled, setSettled] = useState<Ask | null>(null)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    if (requested === null || !enabled) {
      return
    }
    const controller = new AbortController()
    lineSummary(baseUrl, runId, JSON.parse(requested.body) as CleaningPlan, controller.signal)
      .then((found) => {
        setAnswer({ body: requested.body, response: found })
        setError(null)
        setSettled(requested)
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) {
          setError(failure)
          setSettled(requested)
        }
      })
    return () => {
      controller.abort()
    }
  }, [baseUrl, runId, requested, enabled])

  const loading = enabled && requested !== null && requested !== settled
  return {
    response: answer?.response ?? null,
    loading,
    stale: answer !== null && answer.body !== body,
    error,
    refresh: () => {
      if (!loading) {
        setRequested({ body })
      }
    },
  }
}
