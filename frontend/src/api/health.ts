export interface HealthResult {
  status: string
}

export class HealthCheckError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'HealthCheckError'
  }
}

/** GET /health on the backend. The body is checked, not trusted: a proxy or a
 * wrong URL can answer 200 with an HTML page. */
export async function fetchHealth(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<HealthResult> {
  const response = await fetch(`${baseUrl.replace(/\/+$/, '')}/health`, { signal })
  if (!response.ok) {
    throw new HealthCheckError(`HTTP ${String(response.status)}`)
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new HealthCheckError('unexpected response body')
  }
  if (
    typeof body !== 'object' ||
    body === null ||
    !('status' in body) ||
    typeof body.status !== 'string'
  ) {
    throw new HealthCheckError('unexpected response body')
  }
  return { status: body.status }
}
