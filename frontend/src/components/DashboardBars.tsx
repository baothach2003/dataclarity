// The dashboard's bar charts on the page (docs/DASHBOARD_DESIGN.md section 3; Thach's D6), drawn as report.html
// draws them (stages/report/html_bars.py): one row per bar, its label and printed value as text - readable on a
// phone and read by a screen reader - and the bar under them on one scale holding zero, a negative value left of
// the zero line, last month's value a thin marker. Parts of a whole: one bar per month cut into its parts, the
// legend printing each part's figure. The widths are layout; every figure printed is report.json's text.

import type { CSSProperties } from 'react'
import type { Bar } from '../types/reportDashboard.ts'

function scale(bars: Bar[]): { low: number; span: number } {
  const values = [0, ...bars.map((b) => b.now), ...bars.flatMap((b) => (b.was === null ? [] : [b.was]))]
  const low = Math.min(...values)
  const high = Math.max(...values)
  return { low, span: high - low || 1 }
}

function barStyle(value: number, low: number, span: number): CSSProperties {
  const start = Math.min(0, value)
  const end = Math.max(0, value)
  return { left: `${String(((start - low) / span) * 100)}%`, width: `${String(Math.max(((end - start) / span) * 100, 0.4))}%` }
}

export function DashboardBars({ bars, title, diverging }: { bars: Bar[]; title: string; diverging: boolean }) {
  const { low, span } = scale(bars)
  const zero = { left: `${String(((0 - low) / span) * 100)}%` }
  return (
    <ul className="hbars" aria-label={title}>
      {bars.map((bar, index) => {
        const kind = diverging ? (bar.now > 0 ? 'up' : bar.now < 0 ? 'down' : 'flat') : bar.now < 0 ? 'down' : 'now'
        return (
          // Two bars may share a label (none does in report.json); their place is their identity.
          <li className="hb-row" key={index}>
            <span className="hb-label">{bar.label}</span>
            <span className="hb-val">
              {bar.now_text}
              {bar.was_text !== null && <span className="hb-was">{` was ${bar.was_text}`}</span>}
            </span>
            <span className="hb-track" aria-hidden="true">
              <span className={`hb-bar hb-bar--${kind}`} style={barStyle(bar.now, low, span)} />
              {bar.was !== null && <span className="hb-bar hb-bar--was hb-marker" style={barStyle(bar.was, low, span)} />}
              <span className="hb-zero" style={zero} />
            </span>
          </li>
        )
      })}
    </ul>
  )
}

export function DashboardParts({ bars, title }: { bars: Bar[]; title: string }) {
  const months: [string, number[]][] = [['This month', bars.map((b) => b.now)]]
  if (bars.every((b) => b.was !== null)) {
    months.push(['Last month', bars.map((b) => b.was ?? 0)])
  }
  return (
    <>
      <ul className="hparts" aria-label={title}>
        {months.map(([name, values]) => {
          const total = values.reduce((sum, value) => sum + value, 0) || 1
          return (
            <li className="hp-row" key={name}>
              <span className="hb-label">{name}</span>
              <span className="hp-track" aria-hidden="true">
                {values.map((value, index) => (
                  <span key={index} className={`hp-part hp-part--${String(index)}`} style={{ width: `${String((value / total) * 100)}%` }} />
                ))}
              </span>
            </li>
          )
        })}
      </ul>
      {/* Each part's own figures: a legend, not a paragraph (Thach's layout, 2026-10-15). */}
      <ul className="hp-legend">
        {bars.map((bar, index) => (
          <li className="front__small" key={index}>
            <span className={`hp-swatch hp-part--${String(index)}`} aria-hidden="true" />
            {`${bar.label}: ${bar.now_text}${bar.was_text !== null ? ` (was ${bar.was_text})` : ''}`}
          </li>
        ))}
      </ul>
    </>
  )
}
