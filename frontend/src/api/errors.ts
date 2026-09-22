// The API error envelope (docs/SPECS.md section 8 and 10): every non-2xx
// response is `{error: {code, message, details?}}`. This is the only shape a
// client needs to parse (backend/app/errors.py).

export type ApiErrorCode =
  | 'FILE_TOO_LARGE'
  | 'UNSUPPORTED_TYPE'
  | 'EMPTY_FILE'
  | 'PARSE_FAILED'
  | 'INVALID_STATE'
  | 'INVALID_PLAN'
  | 'CLEANING_FAILED'
  | 'EXPIRED'
  | 'RATE_LIMITED'
  | 'NOT_FOUND'
  | 'INVALID_REQUEST'
  | 'INTERNAL_ERROR'

export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly details: Record<string, unknown> | undefined

  constructor(code: ApiErrorCode, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.details = details
  }
}

/** A response this client could not even parse as the envelope: a proxy error
 * page, a dropped connection answered with an empty body, and the like. */
export class UnreachableError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'UnreachableError'
  }
}

const KNOWN_CODES: ReadonlySet<string> = new Set<ApiErrorCode>([
  'FILE_TOO_LARGE',
  'UNSUPPORTED_TYPE',
  'EMPTY_FILE',
  'PARSE_FAILED',
  'INVALID_STATE',
  'INVALID_PLAN',
  'CLEANING_FAILED',
  'EXPIRED',
  'RATE_LIMITED',
  'NOT_FOUND',
  'INVALID_REQUEST',
  'INTERNAL_ERROR',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** `body`, already parsed as JSON, as `ApiError` when it is the envelope, or
 * `UnreachableError` when it is not that shape at all. Shared by `throwApiError`
 * (fetch) and the XMLHttpRequest upload in api/runs.ts, which parses its own
 * body (`responseType: 'json'`) and so never calls `response.json()` itself. */
export function errorFromBody(status: number, body: unknown): ApiError | UnreachableError {
  const error = isRecord(body) ? body.error : undefined
  if (
    !isRecord(error) ||
    typeof error.code !== 'string' ||
    !KNOWN_CODES.has(error.code) ||
    typeof error.message !== 'string'
  ) {
    return new UnreachableError(`HTTP ${String(status)} with an unexpected body`)
  }
  const details = isRecord(error.details) ? error.details : undefined
  return new ApiError(error.code as ApiErrorCode, error.message, details)
}

/** Parses `response`'s body as the error envelope and throws `ApiError`, or
 * `UnreachableError` when the body is not that shape at all. Never returns:
 * only called once `!response.ok`. */
export async function throwApiError(response: Response): Promise<never> {
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new UnreachableError(`HTTP ${String(response.status)} with no JSON body`)
  }
  throw errorFromBody(response.status, body)
}
