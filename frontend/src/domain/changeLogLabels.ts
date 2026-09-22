// Dynamic action labels for the "What ran" table (design/mockups/Results.png
// shows "Fill 'Unknown'" and "Flag negative (kept)" rather than the generic
// catalog names, reflecting the params that actually ran).

import { ACTION_LABELS } from './transformCatalog.ts'
import { stringParam } from './transformParams.ts'
import type { ChangeLogEntry } from '../types/contracts.ts'

export function changeLogActionLabel(entry: ChangeLogEntry): string {
  if (entry.action === 'impute_constant') {
    return `Fill '${stringParam(entry.params, 'value')}'`
  }
  if (entry.action === 'fix_negative') {
    const strategy = stringParam(entry.params, 'strategy', 'flag')
    if (strategy === 'abs') {
      return 'Make positive (absolute value)'
    }
    if (strategy === 'drop') {
      return 'Drop negative rows'
    }
    return 'Flag negative (kept)'
  }
  return ACTION_LABELS[entry.action]
}

export function changeLogAffected(entry: ChangeLogEntry): string {
  if (entry.rows_affected > 0) {
    return `${entry.rows_affected.toLocaleString()} row${entry.rows_affected === 1 ? '' : 's'}`
  }
  if (entry.cells_affected > 0) {
    return `${entry.cells_affected.toLocaleString()} cell${entry.cells_affected === 1 ? '' : 's'}`
  }
  return '0'
}
