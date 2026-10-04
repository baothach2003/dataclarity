import { ApiError } from '../api/errors.ts'

// SPECS section 1's hard ceiling ("max 50MB"); SEC-1 says the server's
// `MAX_UPLOAD_MB` may only lower this, never raise it. The page learns the
// server's own value from GET /api/limits (PROJECT_PLAN 6A: one source of
// truth for a number that can differ per deployment) and checks against it;
// until it is known - or if it cannot be read - this ceiling is the check. The
// server's own FILE_TOO_LARGE answer (backend/app/services/uploads.py) stays
// authoritative and is shown the same way (domain/errorCopy.ts).
export const UPLOAD_CEILING_MB = 50
export const UPLOAD_CEILING_BYTES = UPLOAD_CEILING_MB * 1024 * 1024

/** The client-side half of SEC-1: extension and size, against the server's
 * limit when known (`maxUploadMb`, never above the SPECS ceiling), else the
 * ceiling - which no server exceeds - marked `limit_known: false` so the copy
 * never shows it as the server's (6A-6D review B3). Null means the browser
 * found nothing wrong; the server still decides. */
export function validateFile(file: File, maxUploadMb: number | null = null): ApiError | null {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    return new ApiError('UNSUPPORTED_TYPE', 'Only .csv files are accepted.', {
      filename: file.name,
    })
  }
  const limitMb = Math.min(maxUploadMb ?? UPLOAD_CEILING_MB, UPLOAD_CEILING_MB)
  const limitBytes = limitMb * 1024 * 1024
  if (file.size > limitBytes) {
    return new ApiError(
      'FILE_TOO_LARGE',
      `The file is larger than the ${String(limitMb)} MB limit.`,
      maxUploadMb === null ? { max_bytes: limitBytes, limit_known: false } : { max_bytes: limitBytes },
    )
  }
  return null
}

export function formatBytes(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
