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

// A file over the limit never reads as the limit's size: one byte over 10MB
// is 10.1MB, not 10.0MB (6A-6D review, M3).
function formatMbUp(bytes: number): string {
  return `${(Math.ceil((bytes / 1_048_576) * 10) / 10).toFixed(1)}MB`
}

function detailOf(details: Record<string, unknown> | undefined, key: string): unknown {
  return details?.[key]
}

const MAX_PROBLEMS_SHOWN = 3

/** A date or number reading refusal (`details.reason` "reading") states its
 * true reason: its problems are sentences that say what to do in Review. Any
 * other INVALID_PLAN's problems can be validation dumps, never shown (design
 * gap review, Errors ADD; 6A-6D review S1). */
function planProblems(details: Record<string, unknown> | undefined): string {
  const given = detailOf(details, 'problems')
  const problems = Array.isArray(given) ? given.filter((p): p is string => typeof p === 'string' && p !== '') : []
  if (detailOf(details, 'reason') !== 'reading' || problems.length === 0) {
    return 'Nothing was changed. Check the plan in Review and confirm again.'
  }
  const shown = problems.slice(0, MAX_PROBLEMS_SHOWN)
  // The server's own count, of which it sends at most MAX_PROBLEMS.
  const count = detailOf(details, 'problem_count')
  const total = typeof count === 'number' ? count : problems.length
  const more = total > shown.length ? ` ${(total - shown.length).toLocaleString()} more not listed.` : ''
  return shown.map((problem) => `${problem}.`).join(' ') + more
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
      const actual = context?.fileSizeBytes !== undefined ? formatMbUp(context.fileSizeBytes) : null
      // The client checks only the SPECS ceiling until the server says its
      // limit (useUploadLimit): never shown as the server's (6A-6D review B3).
      const lead = detailOf(error.details, 'limit_known') === false
        ? `Files over ${limit ?? ''} are never accepted, and this file is ${actual ?? ''}.`
        : `The limit is ${limit ?? ''} and this file is ${actual ?? ''}.`
      return {
        title: 'This file is too large',
        detail:
          limit && actual
            ? `${lead} Split it into smaller files or remove unused columns, then upload again.`
            : error.message,
      }
    }
    case 'UNSUPPORTED_TYPE':
      return {
        title: 'Only CSV files are supported',
        detail: 'Save the file as .csv from Excel or Google Sheets, then upload it again.',
      }
    case 'EMPTY_FILE':
      // Also a 0-byte file and one with no header (uploads.py, profiling.py).
      return {
        title: 'This file has no data',
        detail: 'This file has no data rows. Check that you exported the right sheet.',
      }
    case 'PARSE_FAILED':
      return {
        title: "We couldn't read this file",
        // Also binary data and broken UTF-16 (uploads.py, profiling.py).
        detail:
          "The rows don't line up into columns, or the file is not plain text. " +
          'Open the file in a text editor to check its format.',
      }
    case 'INVALID_STATE':
      // A later stage's file another version wrote (2E-v): the server names
      // the file and the step to run again - no fixed line can (PROJECT_PLAN 6D).
      if (detailOf(error.details, 'reason') === 'another_version') {
        return { title: 'This step needs to run again', detail: error.message }
      }
      return {
        title: "This step isn't available yet",
        detail:
          'The run is at a different stage than expected, often because it was opened in two ' +
          'tabs. Reload to continue from the current step.',
      }
    case 'INVALID_PLAN':
      // The server's problems are the true reason and say what to do (an
      // unanswered date or number question, an unmapped required field): no
      // fixed line fits them all (design gap review, Errors ADD).
      return { title: "The cleaning plan couldn't be applied", detail: planProblems(error.details) }
    case 'CLEANING_FAILED':
      return {
        title: "The cleaning plan couldn't be applied to this data",
        detail: error.message,
      }
    case 'RATE_LIMITED':
      // The per-run cap on asking the AI (run_memory.ai_step) - the only
      // RATE_LIMITED the backend sends today; waiting never helps it, and the
      // server says what does (6A-6D review B5).
      if (detailOf(error.details, 'step') !== undefined) {
        return { title: "The AI can't be asked again for this run", detail: error.message }
      }
      return {
        title: 'Too many uploads',
        detail: 'The demo limits uploads per hour from one network. Try again later.',
      }
    case 'EXPIRED':
      // A stage 1 file another version wrote (2E-v): the 24-hour cleanup line
      // would be false (PROJECT_PLAN 6D).
      if (detailOf(error.details, 'reason') === 'another_version') {
        // An older or newer version (contracts/_base.py refuses any other
        // major): never "updated since" (6A-6D review B4).
        return {
          title: 'This run was prepared by another version of DataClarity',
          detail: 'This run was made by a different version of DataClarity. Upload the file again to start a new run.',
        }
      }
      // Retention is a setting (RETENTION_HOURS), and a run's files can be
      // gone for any reason (stage_errors.files_gone): no hours, no cause
      // (6A-6D review S5).
      return {
        title: "This run's files are no longer available",
        detail: 'Uploaded files are deleted after a while to protect your data. Upload the file again to start a new run.',
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
