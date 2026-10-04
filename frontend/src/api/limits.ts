export interface Limits {
  maxUploadMb: number
}

export class LimitsError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'LimitsError'
  }
}

/** GET /api/limits: the server's own upload limit (PROJECT_PLAN 6A - the one
 * source of truth for a number that can differ per deployment). The body is
 * checked, not trusted: a proxy or a wrong URL can answer 200 with HTML. */
export async function fetchLimits(baseUrl: string, signal?: AbortSignal): Promise<Limits> {
  const response = await fetch(`${baseUrl.replace(/\/+$/, '')}/api/limits`, { signal })
  if (!response.ok) {
    throw new LimitsError(`HTTP ${String(response.status)}`)
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new LimitsError('unexpected response body')
  }
  if (
    typeof body !== 'object' ||
    body === null ||
    !('max_upload_mb' in body) ||
    typeof body.max_upload_mb !== 'number' ||
    !Number.isInteger(body.max_upload_mb) ||
    body.max_upload_mb <= 0
  ) {
    throw new LimitsError('unexpected response body')
  }
  return { maxUploadMb: body.max_upload_mb }
}
