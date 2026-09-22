// The Columns card (docs/SPECS.md section 4.2 B; design/mockups/Review.png and
// "Review - Flags.png" for the "Needs attention" filter).

import { useState } from 'react'
import { ColumnRow } from './ColumnRow.tsx'
import type { ColumnViewModel } from '../domain/columnView.ts'
import type { CanonicalField, Params, SemanticType, TransformAction } from '../types/contracts.ts'

interface ColumnsTableProps {
  columns: ColumnViewModel[]
  isNotInventory: boolean
  mappingConflicts: Map<string, string>
  onSemanticTypeChange: (name: string, type: SemanticType) => void
  onCanonicalFieldChange: (name: string, field: CanonicalField) => void
  onActionChange: (name: string, action: TransformAction, params: Params) => void
}

export function ColumnsTable({
  columns,
  isNotInventory,
  mappingConflicts,
  onSemanticTypeChange,
  onCanonicalFieldChange,
  onActionChange,
}: ColumnsTableProps) {
  const [showAttentionOnly, setShowAttentionOnly] = useState(false)
  const [openRationale, setOpenRationale] = useState<string | null>(null)

  const needingAttention = columns.filter((c) => c.needsAttention)
  const visible = showAttentionOnly ? needingAttention : columns

  return (
    <section className="card">
      <div className="columns-card__head">
        <h2 className="columns-card__title">Columns</h2>
        {!isNotInventory && needingAttention.length > 0 ? (
          <div className="filter-toggle" role="group" aria-label="Filter columns">
            <button
              type="button"
              className={'filter-toggle__option' + (!showAttentionOnly ? ' filter-toggle__option--active' : '')}
              onClick={() => { setShowAttentionOnly(false) }}
            >
              All columns ({columns.length})
            </button>
            <button
              type="button"
              className={'filter-toggle__option' + (showAttentionOnly ? ' filter-toggle__option--active' : '')}
              onClick={() => { setShowAttentionOnly(true) }}
            >
              Needs attention ({needingAttention.length})
            </button>
          </div>
        ) : (
          <span className="columns-card__count">{columns.length} columns</span>
        )}
        {showAttentionOnly && (
          <span className="columns-card__count">
            Confidence below 0.70. Check the semantic type and mapping before confirming.
          </span>
        )}
      </div>
      <div className="columns-table-wrap">
        <table className="columns-table">
          <thead>
            <tr>
              <th>Source column</th>
              <th>Dtype</th>
              <th>Semantic type</th>
              <th>Maps to</th>
              <th>Issues</th>
              <th>Action</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((view) => (
              <ColumnRow
                key={view.name}
                view={view}
                isNotInventory={isNotInventory}
                mappingConflict={mappingConflicts.get(view.name)}
                rationaleOpen={openRationale === view.name}
                onToggleRationale={() => {
                  setOpenRationale((current) => (current === view.name ? null : view.name))
                }}
                onSemanticTypeChange={onSemanticTypeChange}
                onCanonicalFieldChange={onCanonicalFieldChange}
                onActionChange={onActionChange}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
