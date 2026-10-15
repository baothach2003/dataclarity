// A note where its figure is (CLAUDE.md 3.3a as Thach amended it, 2026-10-15; docs/DASHBOARD_DESIGN.md section
// 10): a small "i" button beside the figure or chart - reachable by keyboard, named for a screen reader - that
// opens its sentences on tap or click: the element's own lines (`asides`), then each note's sentence by its
// code (the report's own NOTE_TEXTS wording, as report.html's marker prints it). The page words none.

import { useId, useState } from 'react'
import type { NoteCode } from '../types/report.ts'

interface NoteMarkerProps {
  // What the figure is: the button is named "About <about>".
  about: string
  codes: NoteCode[]
  asides: string[]
  texts: ReadonlyMap<NoteCode, string>
}

export function NoteMarker({ about, codes, asides, texts }: NoteMarkerProps) {
  const [open, setOpen] = useState(false)
  const panel = useId()
  if (codes.length === 0 && asides.length === 0) {
    return null
  }
  return (
    <div className="marker-wrap">
      <button
        type="button"
        className="marker"
        data-notes={codes.join(' ')}
        aria-label={`About ${about}`}
        aria-expanded={open}
        aria-controls={panel}
        onClick={() => {
          setOpen((shown) => !shown)
        }}
      >
        i
      </button>
      {/* The panel the button controls always exists (aria-controls), hidden and empty until opened. */}
      <div className="marker__panel" id={panel} hidden={!open}>
        {open &&
          asides.map((line, index) => (
            // Two lines may read alike; their place is their identity.
            <p key={index}>{line}</p>
          ))}
        {open &&
          codes.map((code) => (
            <p key={code}>
              <strong>{`${code.replaceAll('_', ' ')}.`}</strong> {texts.get(code)}
            </p>
          ))}
      </div>
    </div>
  )
}
