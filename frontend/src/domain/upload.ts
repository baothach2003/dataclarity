import { ApiError } from '../api/errors.ts'

// SPECS section 1's hard ceiling ("max 50MB"); SEC-1 says the server's
// `MAX_UPLOAD_MB` may only lower this, never raise it. The server's own
// configured value is not exposed to the client (no second source of truth for
// a number that can differ per deployment - open question left by PROJECT_PLAN
// 6A), so this pre-upload check only catches what SPECS guarantees will always
// be rejected; the server's own FILE_TOO_LARGE answer
// (backend/app/services/uploads.py) is still authoritative and is shown the
// same way (domain/errorCopy.ts) when a smaller configured limit rejects a
// file this check let through.
export const UPLOAD_CEILING_MB = 50
export const UPLOAD_CEILING_BYTES = UPLOAD_CEILING_MB * 1024 * 1024

/** The client-side half of SEC-1: extension and the SPECS ceiling. Null means
 * the browser found nothing wrong; the upload can still be rejected by the
 * server's real, possibly lower, limit. */
export function validateFile(file: File): ApiError | null {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    return new ApiError('UNSUPPORTED_TYPE', 'Only .csv files are accepted.', {
      filename: file.name,
    })
  }
  if (file.size > UPLOAD_CEILING_BYTES) {
    return new ApiError(
      'FILE_TOO_LARGE',
      `The file is larger than the ${String(UPLOAD_CEILING_MB)} MB limit.`,
      { max_bytes: UPLOAD_CEILING_BYTES },
    )
  }
  return null
}

export function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
