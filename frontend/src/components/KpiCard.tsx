// The KPI card (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:570`) as the design gap decisions keep it
// (Thach, 2026-10-03): the change on revenue only - every other card shows its previous value, since no
// other change is computed (CONTRACTS 11) - a null figure shows its reason, never a zero, and the notes
// a figure names sit behind a small marker that reveals them, not inline text.

import { useId, useState } from 'react'
import { FORMATS, change, monthLabel } from '../domain/reportFormat.ts'
import type { Kpi, NoteView, ReportPeriod } from '../types/report.ts'
import { ArrowDownIcon, ArrowUpIcon, InfoIcon } from './Icon.tsx'
import { NoteBody } from './NoteBody.tsx'

// The incomplete previous month's reason is said once, under the KPI row (CONTRACTS 11; stage 5's
// "not compared - see why above").
const NOT_COMPARED = 'not compared (see below)'

interface KpiCardProps {
  kpi: Kpi
  period: ReportPeriod
  // The notes the report shows beside figures (layers 1 and 2); the card shows those it names by code.
  notes: NoteView[]
  // Walk-in candidates nobody confirmed are counted as customers: marked beside the customer figure,
  // the reason said under the KPI row (the design gap review's ADD 6).
  unconfirmedWalkIns?: boolean
}

function previousText(kpi: Kpi, period: ReportPeriod): string {
  const label = monthLabel(period.previous)
  if (!period.previous_complete) {
    return `${label}: ${NOT_COMPARED}`
  }
  return `${label}: ${kpi.previous === null ? (kpi.previous_reason ?? '') : FORMATS[kpi.unit](kpi.previous)}`
}

function Change({ kpi, period }: { kpi: Kpi; period: ReportPeriod }) {
  if (kpi.change_pct !== null) {
    const printed = change(kpi.change_pct)
    // The arrow is a sign: none on a change that prints as zero (CONTRACTS 11; the 6E1 review #3).
    const direction = printed.startsWith('+') ? 'up' : printed.startsWith('-') ? 'down' : 'flat'
    // Delta colour follows direction, as the design keeps it (FIGMA_DESIGN_NOTES open issues).
    return (
      <p className={`kpi-card__change kpi-card__change--${direction}`}>
        {direction === 'up' && <ArrowUpIcon />}
        {direction === 'down' && <ArrowDownIcon />}
        <span>{printed}</span> <span className="kpi-card__vs">vs {monthLabel(period.previous)}</span>
      </p>
    )
  }
  // Said once: under the KPI row when it is the incomplete month's reason, and not again when stage 5
  // gave the change the withheld current month's own reason (layers.py; the 6E1 review #16).
  const saidElsewhere =
    (!period.previous_complete && kpi.change_reason === period.previous_incomplete_reason) ||
    (kpi.current === null && kpi.change_reason === kpi.current_reason)
  if (kpi.change_reason && !saidElsewhere) {
    return <p className="kpi-card__reason">{kpi.change_reason}</p>
  }
  return null
}

export function KpiCard({ kpi, period, notes, unconfirmedWalkIns = false }: KpiCardProps) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const named = notes.filter((note) => kpi.notes.includes(note.code))

  return (
    <div className="kpi-card">
      <div className="kpi-card__head">
        <p className="kpi-card__label" data-testid="kpi-label">
          {kpi.label}
        </p>
        {named.length > 0 && (
          <button
            type="button"
            className="kpi-card__marker"
            aria-label={`Notes on ${kpi.label}`}
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => {
              setOpen(!open)
            }}
          >
            <InfoIcon />
          </button>
        )}
      </div>
      {kpi.current === null ? (
        <p className="kpi-card__reason kpi-card__reason--current">{kpi.current_reason}</p>
      ) : (
        <p className="kpi-card__value">{FORMATS[kpi.unit](kpi.current)}</p>
      )}
      {kpi.id === 'revenue' && <Change kpi={kpi} period={period} />}
      <p className="kpi-card__previous">{previousText(kpi, period)}</p>
      {unconfirmedWalkIns && kpi.id === 'active_customers' && (
        <p className="kpi-card__mark">includes possible walk-ins not confirmed (see below)</p>
      )}
      {named.length > 0 && (
        // Always rendered, so the marker's aria-controls names a real element (the 6E1 review #11).
        <div className="kpi-card__notes" id={panelId} hidden={!open}>
          {named.map((note) => (
            <NoteBody key={note.code} note={note} period={period} />
          ))}
        </div>
      )}
    </div>
  )
}
