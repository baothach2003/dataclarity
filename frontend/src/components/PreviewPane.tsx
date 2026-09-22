// The before/after preview pane (docs/SPECS.md section 4.2 C;
// design/mockups/Review.png). Diff coloring follows
// docs/FIGMA_DESIGN_NOTES.md section 4: changed = yellow, filled in = green,
// dropped = red + strikethrough; the "Before" side is always plain (matches
// the mockup: only the "After" side is colored).
//
// The preview API reports a dropped row as `after: null` with no reason
// (stages/ingest/preview.py: `changed` is forced empty for a dropped row), so
// this pane shows "Row dropped" rather than inventing why (CLAUDE.md 3.2)
// — the mockup's per-row reasons ("No qty", "Dup. row") are illustrative and
// are not data the API actually returns; flagged for Thach.

import type { ReactNode } from 'react'
import { LoaderIcon } from './Icon.tsx'
import type { PreviewResult } from '../types/contracts.ts'

interface PreviewPaneProps {
  preview: PreviewResult | null
  loading: boolean
}

export function PreviewPane({ preview, loading }: PreviewPaneProps) {
  return (
    <section className="card">
      <div className="columns-card__head">
        <h2 className="columns-card__title">Preview</h2>
        <span className="columns-card__count">
          {preview ? `${String(preview.rows.length)} sample rows` : 'No preview yet'} · scroll
          horizontally for more columns
        </span>
        {loading && (
          <span className="preview-updating">
            <LoaderIcon /> Updating preview…
          </span>
        )}
      </div>

      <div className="preview-legend">
        <span>
          <span className="preview-legend__swatch" style={{ background: 'var(--diff-changed)' }} />
          Changed
        </span>
        <span>
          <span className="preview-legend__swatch" style={{ background: 'var(--diff-added)' }} />
          Filled in
        </span>
        <span>
          <span className="preview-legend__swatch" style={{ background: 'var(--diff-removed)' }} />
          Will be dropped
        </span>
      </div>

      {preview && (
        <>
          <div className="preview-deltas">
            <span className="preview-delta-chip">
              Rows {preview.rows_in_file.toLocaleString()} → {preview.rows_after.toLocaleString()}
            </span>
            {preview.deltas.flatMap((delta) => {
              const chips: ReactNode[] = []
              if (
                delta.null_pct_before !== null &&
                delta.null_pct_after !== null &&
                Math.round(delta.null_pct_before * 10) !== Math.round(delta.null_pct_after * 10)
              ) {
                chips.push(
                  <span className="preview-delta-chip" key={`${delta.column}-missing`}>
                    {delta.column} missing {delta.null_pct_before.toFixed(1)}% →{' '}
                    {delta.null_pct_after.toFixed(1)}%
                  </span>,
                )
              } else if (
                delta.unique_before !== null &&
                delta.unique_after !== null &&
                delta.unique_before !== delta.unique_after
              ) {
                chips.push(
                  <span className="preview-delta-chip" key={`${delta.column}-unique`}>
                    {delta.column} unique {delta.unique_before} → {delta.unique_after}
                  </span>,
                )
              }
              return chips
            })}
          </div>

          <div className="preview-columns">
            <div>
              <p className="preview-columns__label">Before</p>
              <BeforeTable preview={preview} />
            </div>
            <div>
              <p className="preview-columns__label">After</p>
              <AfterTable preview={preview} />
            </div>
          </div>
        </>
      )}
    </section>
  )
}

function beforeColumns(preview: PreviewResult): string[] {
  return preview.rows.length > 0 ? Object.keys(preview.rows[0].before) : []
}

function BeforeTable({ preview }: { preview: PreviewResult }) {
  const columns = beforeColumns(preview)
  return (
    <div className="preview-table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row) => (
            <tr key={row.row}>
              {columns.map((c) => (
                <td key={c}>{row.before[c] ?? '(blank)'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AfterTable({ preview }: { preview: PreviewResult }) {
  return (
    <div className="preview-table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            {preview.columns_after.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row) => {
            if (row.after === null) {
              return (
                <tr key={row.row} className="preview-row--dropped">
                  {preview.columns_after.map((c) => (
                    <td key={c} className="preview-cell--removed">
                      {c in row.before ? (row.before[c] ?? '(blank)') : 'Row dropped'}
                    </td>
                  ))}
                </tr>
              )
            }
            const after = row.after
            return (
              <tr key={row.row}>
                {preview.columns_after.map((c) => {
                  const changed = row.changed.includes(c)
                  const hadValue = c in row.before && row.before[c] !== null
                  const cellClass = changed
                    ? hadValue
                      ? 'preview-cell--changed'
                      : 'preview-cell--added'
                    : undefined
                  return (
                    <td key={c} className={cellClass}>
                      {after[c] ?? '(blank)'}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
