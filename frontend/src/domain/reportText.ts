// Words the Insights cards share, so one rule is said one way.

import { monthLabel } from './reportFormat.ts'
import type { ReportPeriod, Scope } from '../types/report.ts'

// A previous-month figure withheld because that month is incomplete; its reason is said once, above it
// (CONTRACTS 11; stage 5's "not compared - see why above").
export const NOT_COMPARED_ABOVE = 'not compared (see above)'

/** A note's or a row's scope as the page names months: "whole file", "June 2026". */
export function scopeLabel(scope: Scope, period: ReportPeriod): string {
  return scope === 'file' ? 'whole file' : monthLabel(scope === 'current' ? period.current : period.previous)
}
