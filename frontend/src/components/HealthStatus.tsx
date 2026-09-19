import { useEffect, useState } from 'react'
import { fetchHealth } from '../api/health.ts'

type HealthState =
  | { kind: 'checking' }
  | { kind: 'ok'; status: string }
  | { kind: 'error'; reason: string }

interface HealthStatusProps {
  /** Backend origin, from VITE_API_BASE_URL; undefined when not configured. */
  baseUrl: string | undefined
}

export function HealthStatus({ baseUrl }: HealthStatusProps) {
  const [state, setState] = useState<HealthState>({ kind: 'checking' })

  useEffect(() => {
    if (!baseUrl) {
      return
    }
    // StrictMode runs effects twice in development: abort the first request so
    // a late answer cannot overwrite the state of the second.
    const controller = new AbortController()
    fetchHealth(baseUrl, controller.signal)
      .then((result) => {
        setState({ kind: 'ok', status: result.status })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return
        }
        const reason = error instanceof Error ? error.message : String(error)
        setState({ kind: 'error', reason })
      })
    return () => {
      controller.abort()
    }
  }, [baseUrl])

  return <p role="status">{describe(baseUrl, state)}</p>
}

function describe(baseUrl: string | undefined, state: HealthState): string {
  if (!baseUrl) {
    return 'Backend: not configured (set VITE_API_BASE_URL in .env)'
  }
  switch (state.kind) {
    case 'checking':
      return 'Backend: checking…'
    case 'ok':
      return `Backend: ${state.status}`
    case 'error':
      return `Backend: unreachable (${state.reason})`
  }
}
