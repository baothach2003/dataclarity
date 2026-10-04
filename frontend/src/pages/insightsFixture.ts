// A report.json for the Insights tests: insightsFixture.json, docs/FIGMA_DESIGN_NOTES.md section 6's sample
// data (June vs May 2026, revenue 104,160 -> 96,152). tests/contracts/test_frontend_fixtures.py validates
// the JSON with contracts/report.py, so no test here passes on a report stage 5 could not write (the 6E1
// review, #8). Each call returns a fresh copy a test may change.

import type { ReportContract } from '../types/report.ts'
import fixture from './insightsFixture.json'

export function makeReport(): ReportContract {
  return structuredClone(fixture) as unknown as ReportContract
}

// contracts.lines.NOTE_TEXTS' own words, as in the fixture.
export const SAME_DAY_TEXT = makeReport().layer_1_numbers.notes[0]?.text ?? ''
export const DISCOUNTS_TEXT = makeReport().layer_1_numbers.how_to_read[0]?.text ?? ''
