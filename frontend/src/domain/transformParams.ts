// Reading and defaulting an action's params (docs/AI_PIPELINE.md section 6,
// stages/ingest/transform_params.py). The backend re-validates every value at
// preview and execute time; this module only picks sane defaults when the user
// switches actions and reads values back out of the untyped `Params` bag
// without `any` (CLAUDE.md section 5).

import { CASE_MODES, CAST_TARGETS, NEGATIVE_STRATEGIES } from './transformCatalog.ts'
import type { Params, TransformAction } from '../types/contracts.ts'

/** A safe starting `params` for `action` freshly chosen in the dropdown: every
 * required param present with its recommended default, and nothing left over
 * from a previously chosen action (an unknown param fails `params_problem`). */
export function defaultParams(action: TransformAction): Params {
  switch (action) {
    case 'impute_constant':
      return { value: 'Unknown' }
    case 'cast_type':
      return { target: CAST_TARGETS[0] }
    case 'normalize_case':
      return { mode: CASE_MODES[0] }
    case 'standardize_categories':
      return { mapping: {} }
    case 'fix_negative':
      return { strategy: NEGATIVE_STRATEGIES[0] }
    case 'clip_outliers_iqr':
      return { k: 1.5 }
    case 'flag_only':
      return { note: '' }
    case 'parse_datetime':
    case 'flag_duplicate_keys':
    case 'impute_median':
    case 'impute_mean':
    case 'impute_mode':
    case 'drop_rows_missing':
    case 'drop_column':
    case 'trim_whitespace':
    case 'remove_exact_duplicates':
      return {}
  }
}

export function stringParam(params: Params, key: string, fallback = ''): string {
  const value = params[key]
  return typeof value === 'string' ? value : fallback
}

export function numberParam(params: Params, key: string, fallback = 0): number {
  const value = params[key]
  return typeof value === 'number' ? value : fallback
}

export function boolParam(params: Params, key: string, fallback = false): boolean {
  const value = params[key]
  return typeof value === 'boolean' ? value : fallback
}

export function mappingParam(params: Params, key: string): Record<string, string> {
  const value = params[key]
  return typeof value === 'object' && !Array.isArray(value) ? value : {}
}

/** Whether `action` takes any params at all: only then does the Action cell
 * show a params editor under the dropdown. */
export function hasParams(action: TransformAction): boolean {
  return Object.keys(defaultParams(action)).length > 0
}
