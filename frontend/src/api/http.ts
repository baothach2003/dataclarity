// The fetch helpers every typed client here shares (api/runs.ts, api/analysis.ts):
// one base-URL rule, one way to read a JSON body, one error envelope (api/errors.ts).

import { throwApiError, UnreachableError } from './errors.ts'

export function trimSlash(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}

export async function parseJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T
  } catch {
    throw new UnreachableError('unexpected response body')
  }
}

export async function getJson<T>(baseUrl: string, path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${trimSlash(baseUrl)}${path}`, { signal })
  if (!response.ok) {
    await throwApiError(response)
  }
  return parseJson<T>(response)
}

export async function postJson<T>(
  baseUrl: string,
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${trimSlash(baseUrl)}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
    signal,
  })
  if (!response.ok) {
    await throwApiError(response)
  }
  return parseJson<T>(response)
}
