// Final UI copy for every error and notice case (design/mockups/Errors.png:
// "One Notice per case in SPECS section 10. Copy is final; the code column
// maps to the API error code."). Server messages are for logs and for cases
// this table has no fixed line for; the fixed copy is what the user sees.

import { ApiError, UnreachableError } from '../api/errors.ts'

export interface ErrorCopy {
  title: string
  detail: string
}

function formatMb(bytes: number): string {
  return `${(bytes / 1_048_576).toFixed(1)}MB`
}

function detailOf(details: Record<string, unknown> | undefined, key: string): unknown {
  return details?.[key]
}

/** `error` and, for FILE_TOO_LARGE, the file size the browser already knows
 * (the server does not report the size of a file it stopped reading partway
 * through: `backend/app/services/uploads.py` only knows the limit). */
export function describeError(error: unknown, context?: { fileSizeBytes?: number }): ErrorCopy {
  if (error instanceof ApiError) {
    return describeApiError(error, context)
  }
  if (error instanceof UnreachableError) {
    return {
      title: 'The server could not be reached',
      detail: 'Check that the backend is running and try again.',
    }
  }
  if (error instanceof Error) {
    return { title: 'The server could not be reached', detail: error.message }
  }
  return { title: 'Something went wrong', detail: 'Please try again.' }
}

function describeApiError(error: ApiError, context?: { fileSizeBytes?: number }): ErrorCopy {
  switch (error.code) {
    case 'FILE_TOO_LARGE': {
      const maxBytes = detailOf(error.details, 'max_bytes')
      const limit = typeof maxBytes === 'number' ? formatMb(maxBytes) : null
      const actual = context?.fileSizeBytes !== undefined ? formatMb(context.fileSizeBytes) : null
      return {
        title: 'This file is too large',
        detail:
          limit && actual
            ? `The limit is ${limit} and this file is ${actual}. Split it into smaller files or ` +
              'remove unused columns, then upload again.'
            : error.message,
      }
    }
    case 'UNSUPPORTED_TYPE':
      return {
        title: 'Only CSV files are supported',
        detail: 'Save the file as .csv from Excel or Google Sheets, then upload it again.',
      }
    case 'EMPTY_FILE':
      return {
        title: 'This file has no data',
        detail: 'We found a header row but no data rows. Check that you exported the right sheet.',
      }
    case 'PARSE_FAILED':
      return {
        title: "We couldn't read this file",
        detail:
          "We tried comma, semicolon, tab and pipe separators, but the rows don't line up. " +
          'Open the file in a text editor to check its format.',
      }
    case 'INVALID_STATE':
      return {
        title: "This step isn't available yet",
        detail:
          'The run is at a different stage than expected, often because it was opened in two ' +
          'tabs. Reload to continue from the current step.',
      }
    case 'INVALID_PLAN':
      return {
        title: "The cleaning plan couldn't be applied",
        detail:
          "One or more actions aren't allowed for their column type, so nothing was changed. " +
          'Review the highlighted rows and confirm again.',
      }
    case 'CLEANING_FAILED':
      return {
        title: "The cleaning plan couldn't be applied to this data",
        detail: error.message,
      }
    case 'RATE_LIMITED':
      return {
        title: 'Too many uploads',
        detail: 'The demo limits uploads per hour from one network. Try again later.',
      }
    case 'EXPIRED':
      return {
        title: 'This run has expired',
        detail: 'Files are deleted 24 hours after upload to protect your data. Upload the file again to start a new run.',
      }
    case 'NOT_FOUND':
      return {
        title: 'This run could not be found',
        detail: 'It may have expired, or the link is wrong. Upload the file again.',
      }
    case 'INVALID_REQUEST':
    case 'INTERNAL_ERROR':
      return { title: 'Something went wrong', detail: error.message }
  }
}
