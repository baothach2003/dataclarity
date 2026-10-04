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

// One request per identical ask in flight, shared by every effect that wants
// it. The server allows one whole-file summary per run at a time and answers a
// second one 409 summary_in_progress; aborting in the browser never stopped the
// server, so StrictMode's second effect run collided with the first (the
// browser check of 6B/6C, 2026-10-04). A request nobody listens to any more is
// aborted and forgotten, one task later - StrictMode's remount comes before
// it - so a hung one never outlives Review (6A-6D review S2).
interface Shared {
  request: Promise<LineSummaryResponse>
  controller: AbortController
  listeners: number
}

const inFlight = new Map<string, Shared>()

function ask(baseUrl: string, runId: string, body: string): { request: Promise<LineSummaryResponse>; release: () => void } {
  const key = JSON.stringify([baseUrl, runId, body])
  let shared = inFlight.get(key)
  if (shared === undefined) {
    const controller = new AbortController()
    const request = lineSummary(baseUrl, runId, JSON.parse(body) as CleaningPlan, controller.signal)
    const entry: Shared = { request, controller, listeners: 0 }
    const forget = () => {
      if (inFlight.get(key) === entry) {
        inFlight.delete(key)
      }
    }
    request.then(forget, forget)
    inFlight.set(key, entry)
    shared = entry
  }
  const entry = shared
  entry.listeners += 1
  return {
    request: entry.request,
    release: () => {
      entry.listeners -= 1
      setTimeout(() => {
        if (entry.listeners === 0 && inFlight.get(key) === entry) {
          inFlight.delete(key)
          entry.controller.abort()
        }
      }, 0)
    },
  }
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
    let listening = true
    const { request, release } = ask(baseUrl, runId, requested.body)
    request
      .then((found) => {
        if (listening) {
          setAnswer({ body: requested.body, response: found })
          setError(null)
          setSettled(requested)
        }
      })
      .catch((failure: unknown) => {
        if (listening) {
          setError(failure)
          setSettled(requested)
        }
      })
    return () => {
      listening = false
      release()
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
