import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/errors.ts'
import { describeError } from './errorCopy.ts'

// PROJECT_PLAN 6D (2E-v): a run file another version of DataClarity wrote is
// answered EXPIRED (a stage 1 file: upload again) or INVALID_STATE (a later
// stage's file: run that stage again), with details.reason "another_version".
// The fixed lines "files are deleted 24 hours after upload" and "opened in two
// tabs" are false for it.
describe('describeError for a run another version wrote', () => {
  it('says EXPIRED came from another version, not from the cleanup', () => {
    const copy = describeError(
      new ApiError('EXPIRED', 'This run was prepared by another version of DataClarity. Upload the file again.', {
        reason: 'another_version',
      }),
    )

    expect(copy.title).toBe('This run was prepared by another version of DataClarity')
    // An older OR newer version (contracts/_base.py refuses any other major):
    // never "has been updated since" (6A-6D review, B4).
    expect(copy.detail).toBe('This run was made by a different version of DataClarity. Upload the file again to start a new run.')
    expect(copy.detail).not.toMatch(/updated|deleted/)
  })

  it("says which step to run again for a later stage's file, as the server names it", () => {
    const message =
      "This run's metrics.json was written by another version of DataClarity. Run the analysis again."
    const copy = describeError(
      new ApiError('INVALID_STATE', message, { reason: 'another_version', file: 'metrics.json' }),
    )

    expect(copy.title).toBe('This step needs to run again')
    expect(copy.detail).toBe(message)
    expect(copy.detail).not.toMatch(/two tabs/)
  })

  it('keeps the fixed line for an INVALID_STATE with no reason it knows', () => {
    expect(describeError(new ApiError('INVALID_STATE', 'Cannot analyze: the run is profiled.')).detail).toMatch(/two tabs/)
  })
})

// The 6E1 review (#5): there is no saved state, so a reload goes back to
// Upload and the run is lost - never advised. The reasons the analysis flow
// can meet say what helps (run_memory.py, reporting.py, prediction.py).
describe('describeError for INVALID_STATE in the analysis', () => {
  it('says to wait while another step runs', () => {
    const message = 'Another step is already running for this run. Wait for it to finish.'
    const copy = describeError(new ApiError('INVALID_STATE', message, { reason: 'step_in_progress' }))

    expect(copy.title).toBe('Another step is still running for this run')
    expect(copy.detail).toBe(message)
  })

  it.each([
    ['files_mismatch', "The run's files do not describe the same months: forecast.json starts at 2026-08."],
    ['diagnosis_mismatch', 'The diagnosis describes other months than the metrics.'],
    ['unreadable', "This run's report.json cannot be read. Build the report again."],
  ])("asks for the step again on %s, as the server words it", (reason, message) => {
    const copy = describeError(new ApiError('INVALID_STATE', message, { reason }))

    expect(copy.title).toBe('This step needs to run again')
    expect(copy.detail).toBe(message)
  })

  it('never advises a reload, which would lose the run', () => {
    expect(describeError(new ApiError('INVALID_STATE', 'Cannot analyze: the run is profiled.')).detail).not.toMatch(/[Rr]eload/)
  })
})

// The 6A-6D review (S5): retention is a setting (RETENTION_HOURS) and a run's
// files can be gone for any reason (stage_errors.files_gone) - no fixed number
// of hours, no claimed cause.
describe('describeError for any other EXPIRED', () => {
  it('says the files are gone without naming a cause or a time', () => {
    const copy = describeError(new ApiError('EXPIRED', "The run's files are gone. Upload the file again."))

    expect(copy.title).toBe("This run's files are no longer available")
    expect(copy.detail).toBe(
      'Uploaded files are deleted after a while to protect your data. Upload the file again to start a new run.',
    )
  })
})

// The design gap review's Errors ADD: an INVALID_PLAN states its true reason.
// The fixed line "actions aren't allowed for their column type" was false. A
// date or number reading refusal carries details.reason "reading" and problems
// that say what to do; any other INVALID_PLAN's problems can be validation
// dumps (parse_plan), so they are not shown (6A-6D review, S1).
describe('describeError for INVALID_PLAN', () => {
  const DATES =
    "The dates in column 'Date' can be read day first or month first (such as '03/04/2024', which could be either), and nobody said which: answer the date question in Review (if Review shows none, upload the file again)"
  const NUMBERS =
    "The numbers in column 'Price' can be read two ways - '1.500' is one and a half with a decimal point, or fifteen hundred with a thousands point - and nothing in the file says which: answer the number question in Review"

  it("shows a reading refusal's problems as sentences", () => {
    const copy = describeError(
      new ApiError('INVALID_PLAN', 'The plan cannot run.', { problems: [DATES, NUMBERS], problem_count: 2, reason: 'reading' }),
    )

    expect(copy.title).toBe("The cleaning plan couldn't be applied")
    expect(copy.detail).toBe(`${DATES}. ${NUMBERS}.`)
  })

  it('lists at most three and counts the rest from the server', () => {
    const copy = describeError(
      new ApiError('INVALID_PLAN', 'The plan cannot run.', { problems: ['a', 'b', 'c', 'd'], problem_count: 6, reason: 'reading' }),
    )

    expect(copy.detail).toBe('a. b. c. 3 more not listed.')
  })

  it('shows no validation dump for any other INVALID_PLAN', () => {
    const copy = describeError(
      new ApiError('INVALID_PLAN', 'The plan cannot run.', {
        problems: ["column_actions.3.canonical_field: Input should be 'product_name', 'sku'"],
        problem_count: 1,
      }),
    )

    expect(copy.detail).toBe('Nothing was changed. Check the plan in Review and confirm again.')
  })
})

// The 6A-6D review (B5): the only RATE_LIMITED the backend sends today is the
// per-run cap on asking the AI (run_memory.ai_step, details.step) - "too many
// uploads, try later" is false for it and waiting never helps.
describe('describeError for RATE_LIMITED', () => {
  it("shows the AI cap's own message", () => {
    const message =
      'The AI has already been asked 3 times to propose a plan for this run. Build the plan by hand, or upload the file again.'
    const copy = describeError(new ApiError('RATE_LIMITED', message, { step: 'propose a plan', attempts: 3 }))

    expect(copy.title).toBe("The AI can't be asked again for this run")
    expect(copy.detail).toBe(message)
  })
})

// The 6A-6D review (M8): EMPTY_FILE also answers a 0-byte file and a file with
// no header; PARSE_FAILED also answers binary data and broken UTF-16.
describe('describeError for files that cannot be read', () => {
  it('claims no header row for an empty file', () => {
    expect(describeError(new ApiError('EMPTY_FILE', 'The file is empty.')).detail).toBe(
      'This file has no data rows. Check that you exported the right sheet.',
    )
  })

  it('claims no separator search for a file that is not text', () => {
    expect(
      describeError(new ApiError('PARSE_FAILED', 'The file is not a text CSV file: it contains binary data.')).detail,
    ).toBe("The rows don't line up into columns, or the file is not plain text. Open the file in a text editor to check its format.")
  })
})

describe('describeError for FILE_TOO_LARGE', () => {
  it('never shows a file over the limit as the same size (6A-6D review, M3)', () => {
    const tenMb = 10 * 1_048_576
    const copy = describeError(new ApiError('FILE_TOO_LARGE', 'too large', { max_bytes: tenMb }), { fileSizeBytes: tenMb + 1 })

    expect(copy.detail).toBe('The limit is 10.0MB and this file is 10.1MB. Split it into smaller files or remove unused columns, then upload again.')
  })

  it("names the ceiling, not a server limit, when the server's limit is unknown (6A-6D review, B3)", () => {
    const fiftyMb = 50 * 1_048_576
    const copy = describeError(new ApiError('FILE_TOO_LARGE', 'too large', { max_bytes: fiftyMb, limit_known: false }), {
      fileSizeBytes: 61 * 1_048_576,
    })

    expect(copy.detail).toBe('Files over 50.0MB are never accepted, and this file is 61.0MB. Split it into smaller files or remove unused columns, then upload again.')
  })
})

// The design gap review's Errors ADD (6E1): ANALYSIS_FAILED with its reasons.
// A missing field is told by its code; the other reasons' messages say what
// happened and what to do (backend/app/services/metrics.py, stage_errors.py).
describe('describeError for ANALYSIS_FAILED', () => {
  it('names the field no column was mapped to', () => {
    const copy = describeError(
      new ApiError('ANALYSIS_FAILED', "cleaned.csv has no column mapped to 'unit_price'; metrics cannot be computed without it", {
        canonical_field: 'unit_price',
      }),
    )

    expect(copy.title).toBe("The analysis can't run on this file")
    expect(copy.detail).toBe(
      'No column was mapped as the unit price, which the figures need. If the file has one, upload it again and map it in Review.',
    )
  })

  // The 6E1 review (#18): decided by code, never the server's technical words.
  it('says a file that is not sales data is not analysed', () => {
    const copy = describeError(
      new ApiError('ANALYSIS_FAILED', 'This file was not identified as inventory or sales data; stages 2-5 are unavailable.', {
        domain_confidence: 0.2,
        domain_reasoning: 'a staff roster',
      }),
    )

    expect(copy.detail).toBe('This file did not look like sales data, so the analysis does not run on it.')
  })

  it("says a cleaned file whose line classes changed must be uploaded again", () => {
    const copy = describeError(
      new ApiError('ANALYSIS_FAILED', "cleaned.csv's line classes cannot be read: line_class holds values outside its closed list: ['x']; re-upload the file", {
        line_classes: "line_class holds values outside its closed list: ['x']",
      }),
    )

    expect(copy.detail).toBe('The cleaned file no longer matches what cleaning wrote. Upload the file again.')
  })

  it("shows the server's own reason otherwise", () => {
    const message =
      "The file's amounts or quantities are too large to work with, so its metrics cannot be computed. Correct them in the file and upload it again."
    const copy = describeError(new ApiError('ANALYSIS_FAILED', message, { reason: 'amounts_too_large' }))

    expect(copy.title).toBe("The analysis can't run on this file")
    expect(copy.detail).toBe(message)
  })
})
