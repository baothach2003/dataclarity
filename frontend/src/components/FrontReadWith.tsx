// "Read these figures with: ..." (the report redesign's Q35; report.html's _read_with): the notes beside a
// section's figures, each a link to its sentence in "Technical details" - which opens there (as report.html
// opens its appendix at #note-<code>). Named by code, as report.html names them.

import type { NoteCode } from '../types/report.ts'

interface FrontReadWithProps {
  codes: NoteCode[]
  onOpen: (code: NoteCode) => void
}

export function FrontReadWith({ codes, onOpen }: FrontReadWithProps) {
  if (codes.length === 0) {
    return null
  }
  return (
    <p className="front__small">
      Read these figures with:{' '}
      {codes.map((code, index) => (
        <span key={code}>
          {index > 0 && ' '}
          <a
            href={`#note-${code}`}
            onClick={(event) => {
              event.preventDefault()
              onOpen(code)
            }}
          >
            {code.replaceAll('_', ' ')}
          </a>
        </span>
      ))}
    </p>
  )
}
