// The notes the report names beside a figure (by code), shown beside it - folded, so the figure leads
// (CONTRACTS 11; CLAUDE.md 3.3a: a note wherever the affected figure is shown).

import type { NoteCode, NoteView, ReportPeriod } from '../types/report.ts'
import { NoteBody } from './NoteBody.tsx'

interface NotesBesideProps {
  // The codes the figure names, or the notes themselves.
  codes?: NoteCode[]
  notes: NoteView[]
  period: ReportPeriod
}

export function NotesBeside({ codes, notes, period }: NotesBesideProps) {
  const shown = codes === undefined ? notes : notes.filter((note) => codes.includes(note.code))
  if (shown.length === 0) {
    return null
  }
  return (
    <details className="notes-beside">
      <summary>{`Notes on these figures (${String(shown.length)})`}</summary>
      {shown.map((note) => (
        <NoteBody key={note.code} note={note} period={period} />
      ))}
    </details>
  )
}
