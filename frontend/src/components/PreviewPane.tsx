// The preview pane (docs/FIGMA_DESIGN_NOTES.md section 7, revised
// 2026-09-22): one table, a pinned Row column, only changed columns shown by
// default, dotted-underline + fill for a changed/filled cell, strikethrough
// for a dropped row, the original value on hover and on keyboard focus.

import { useId, useMemo, useState } from 'react'
import { LoaderIcon } from './Icon.tsx'
import {
  columnMeta,
  dropReason,
  formatCellValue,
  isNumeric,
  splitColumns,
} from '../domain/previewDisplay.ts'
import type { CleaningPlan, PreviewResult, PreviewRow } from '../types/contracts.ts'

interface PreviewPaneProps {
  preview: PreviewResult | null
  loading: boolean
  plan: CleaningPlan
}

export function PreviewPane({ preview, loading, plan }: PreviewPaneProps) {
  const [showUnchanged, setShowUnchanged] = useState(false)
  const { semanticType, actionLabel } = useMemo(() => columnMeta(plan), [plan])
  const { shown, hidden } = useMemo(
    () => (preview ? splitColumns(preview) : { shown: [], hidden: [] }),
    [preview],
  )
  const columns = showUnchanged ? [...shown, ...hidden] : shown

  return (
    <section className="card">
      <div className="columns-card__head">
        <h2 className="columns-card__title">Preview</h2>
        <span className="columns-card__count">
          {preview
            ? `${String(preview.rows.length)} of ${String(preview.sample_rows)} sampled rows · ` +
              `${String(shown.length)} of ${String(shown.length + hidden.length)} columns changed`
            : 'No preview yet'}
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
        <span>· Dotted underline = value changed, hover or focus to see the original</span>
      </div>

      {preview && (
        <>
          <div className="preview-deltas">
            <span className="preview-delta-chip">
              Rows {preview.rows_in_file.toLocaleString()} → {preview.rows_after.toLocaleString()}{' '}
              (full file, projected)
            </span>
            {preview.deltas.map((delta) => {
              if (
                delta.null_pct_before !== null &&
                delta.null_pct_after !== null &&
                Math.round(delta.null_pct_before * 10) !== Math.round(delta.null_pct_after * 10)
              ) {
                return (
                  <span className="preview-delta-chip" key={`${delta.column}-missing`}>
                    {delta.column} missing {delta.null_pct_before.toFixed(1)}% →{' '}
                    {delta.null_pct_after.toFixed(1)}%
                  </span>
                )
              }
              if (
                delta.unique_before !== null &&
                delta.unique_after !== null &&
                delta.unique_before !== delta.unique_after
              ) {
                return (
                  <span className="preview-delta-chip" key={`${delta.column}-unique`}>
                    {delta.column} unique {delta.unique_before} → {delta.unique_after}
                  </span>
                )
              }
              return null
            })}
          </div>

          {hidden.length > 0 && (
            <div className="preview-hidden-columns">
              <span>Hidden: {hidden.join(', ')} (no changes in sample)</span>
              <button
                type="button"
                className="button button--secondary"
                onClick={() => {
                  setShowUnchanged((current) => !current)
                }}
              >
                {showUnchanged ? 'Hide unchanged columns' : `Show unchanged columns (${String(hidden.length)})`}
              </button>
            </div>
          )}

          <PreviewTable
            preview={preview}
            columns={columns}
            semanticType={semanticType}
            actionLabel={actionLabel}
            plan={plan}
          />
        </>
      )}
    </section>
  )
}

function PreviewTable({
  preview,
  columns,
  semanticType,
  actionLabel,
  plan,
}: {
  preview: PreviewResult
  columns: string[]
  semanticType: ReturnType<typeof columnMeta>['semanticType']
  actionLabel: ReturnType<typeof columnMeta>['actionLabel']
  plan: CleaningPlan
}) {
  return (
    <div className="preview-table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            <th className="preview-table__row-col">Row</th>
            {columns.map((c) => (
              <th key={c} className={isNumeric(semanticType.get(c)) ? 'preview-table--numeric' : undefined}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row) =>
            row.after === null ? (
              <DroppedRow key={row.row} row={row} columns={columns} plan={plan} allRows={preview.rows} />
            ) : (
              <ChangedRow
                key={row.row}
                row={row}
                after={row.after}
                columns={columns}
                semanticType={semanticType}
                actionLabel={actionLabel}
              />
            ),
          )}
        </tbody>
      </table>
    </div>
  )
}

function DroppedRow({
  row,
  columns,
  plan,
  allRows,
}: {
  row: PreviewRow
  columns: string[]
  plan: CleaningPlan
  allRows: PreviewRow[]
}) {
  return (
    <tr className="preview-row--dropped">
      <td className="preview-table__row-col">
        {row.row} <span className="preview-drop-reason">{dropReason(row, plan, allRows)}</span>
      </td>
      {columns.map((c) => (
        <td key={c} className="preview-cell--removed">
          {c in row.before ? (row.before[c] ?? '(blank)') : 'Row dropped'}
        </td>
      ))}
    </tr>
  )
}

function ChangedRow({
  row,
  after,
  columns,
  semanticType,
  actionLabel,
}: {
  row: PreviewRow
  after: Record<string, string | null>
  columns: string[]
  semanticType: ReturnType<typeof columnMeta>['semanticType']
  actionLabel: ReturnType<typeof columnMeta>['actionLabel']
}) {
  return (
    <tr>
      <td className="preview-table__row-col">{row.row}</td>
      {columns.map((c) => {
        const changed = row.changed.includes(c)
        const hadValue = c in row.before && row.before[c] !== null
        const numeric = isNumeric(semanticType.get(c))
        const rawValue = after[c] ?? '(blank)'
        const displayValue = after[c] !== null ? formatCellValue(after[c], numeric) : rawValue
        const className = [
          numeric ? 'preview-table--numeric' : undefined,
          changed ? (hadValue ? 'preview-cell--changed' : 'preview-cell--added') : undefined,
        ]
          .filter(Boolean)
          .join(' ') || undefined

        return (
          <td key={c} className={className}>
            {changed ? (
              <PreviewCellTooltip
                displayValue={displayValue}
                beforeValue={c in row.before ? (row.before[c] ?? '(blank)') : '(none)'}
                action={actionLabel.get(c)}
              />
            ) : (
              displayValue
            )}
          </td>
        )
      })}
    </tr>
  )
}

function PreviewCellTooltip({
  displayValue,
  beforeValue,
  action,
}: {
  displayValue: string
  beforeValue: string
  action: string | undefined
}) {
  const tooltipId = useId()
  return (
    <span className="preview-cell-tip-wrap" tabIndex={0} aria-describedby={tooltipId}>
      <span className="preview-value--dotted">{displayValue}</span>
      <span className="preview-cell-tip" role="tooltip" id={tooltipId}>
        Before: {beforeValue}
        {action && (
          <>
            <br />
            {action}
          </>
        )}
      </span>
    </span>
  )
}
