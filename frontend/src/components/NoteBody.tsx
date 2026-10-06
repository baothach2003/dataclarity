// One note as report.json words it (by its code, from NOTE_TEXTS - CONTRACTS 11) with its measures:
// a previous month's measure only when that month is compared, a current or whole-file one always - its
// lines are real (CONTRACTS 9; stage 5's html_parts.scope_shown).

import { useCurrencyCode } from '../domain/currencyCode.ts'
import { count, money } from '../domain/reportFormat.ts'
import { scopeLabel } from '../domain/reportText.ts'
import type { NoteMeasure, NoteView, ReportPeriod } from '../types/report.ts'

function plural(n: number, one: string, many: string): string {
  return `${count(n)} ${n === 1 ? one : many}`
}

/** Every count stage 5's measures table prints - lines, amount, orders, keys (html_parts.measures; the
 * 6E1 review #4: a note's sentence can speak of the orders it counts). */
function measureText(measure: NoteMeasure, period: ReportPeriod, code: string | null): string {
  const parts = [plural(measure.lines, 'line', 'lines')]
  if (measure.amount !== null) {
    parts.push(money(measure.amount, code))
  }
  if (measure.orders !== null && measure.orders !== undefined) {
    parts.push(plural(measure.orders, 'order', 'orders'))
  }
  if (measure.keys !== null && measure.keys !== undefined) {
    parts.push(plural(measure.keys, 'key', 'keys'))
  }
  return `${measure.name}, ${scopeLabel(measure.scope, period)}: ${parts.join(', ')}`
}

// `anchor`: the one place a note is linked to from the front section's "Read these figures with"
// (report.html's #note-<code>), so each id stands once on the page.
export function NoteBody({ note, period, anchor = false }: { note: NoteView; period: ReportPeriod; anchor?: boolean }) {
  const code = useCurrencyCode()
  const shown = note.measures.filter((measure) => measure.scope !== 'previous' || period.previous_complete)
  return (
    <div className="note-body" id={anchor ? `note-${note.code}` : undefined}>
      <p>{note.text}</p>
      {shown.length > 0 && (
        <ul className="note-body__measures">
          {shown.map((measure) => (
            <li key={`${measure.name}-${measure.scope}`}>{measureText(measure, period, code)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
