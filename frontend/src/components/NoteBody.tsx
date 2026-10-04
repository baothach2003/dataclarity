// One note as report.json words it (by its code, from NOTE_TEXTS - CONTRACTS 11) with its measures:
// a previous month's measure only when that month is compared, a current or whole-file one always - its
// lines are real (CONTRACTS 9; stage 5's html_parts.scope_shown).

import { count, money, monthLabel } from '../domain/reportFormat.ts'
import type { NoteMeasure, NoteView, ReportPeriod, Scope } from '../types/report.ts'

function scopeLabel(scope: Scope, period: ReportPeriod): string {
  return scope === 'file' ? 'whole file' : monthLabel(scope === 'current' ? period.current : period.previous)
}

function plural(n: number, one: string, many: string): string {
  return `${count(n)} ${n === 1 ? one : many}`
}

/** Every count stage 5's measures table prints - lines, amount, orders, keys (html_parts.measures; the
 * 6E1 review #4: a note's sentence can speak of the orders it counts). */
function measureText(measure: NoteMeasure, period: ReportPeriod): string {
  const parts = [plural(measure.lines, 'line', 'lines')]
  if (measure.amount !== null) {
    parts.push(money(measure.amount))
  }
  if (measure.orders !== null && measure.orders !== undefined) {
    parts.push(plural(measure.orders, 'order', 'orders'))
  }
  if (measure.keys !== null && measure.keys !== undefined) {
    parts.push(plural(measure.keys, 'key', 'keys'))
  }
  return `${measure.name}, ${scopeLabel(measure.scope, period)}: ${parts.join(', ')}`
}

export function NoteBody({ note, period }: { note: NoteView; period: ReportPeriod }) {
  const shown = note.measures.filter((measure) => measure.scope !== 'previous' || period.previous_complete)
  return (
    <div className="note-body">
      <p>{note.text}</p>
      {shown.length > 0 && (
        <ul className="note-body__measures">
          {shown.map((measure) => (
            <li key={`${measure.name}-${measure.scope}`}>{measureText(measure, period)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
