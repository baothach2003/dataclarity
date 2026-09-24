// One row of the Review columns table (docs/SPECS.md section 4.2 B;
// design/mockups/Review.png).

import { ActionCell } from './ActionCell.tsx'
import { ConfidenceMeter } from './ConfidenceMeter.tsx'
import { AlertTriangleIcon, InfoIcon } from './Icon.tsx'
import { IssueBadges } from './IssueBadges.tsx'
import type { ColumnViewModel } from '../domain/columnView.ts'
import { CANONICAL_FIELD_LABELS, SEMANTIC_TYPE_LABELS } from '../domain/labels.ts'
import type { CanonicalField, Params, SemanticType, TransformAction } from '../types/contracts.ts'

const SEMANTIC_TYPES: SemanticType[] = [
  'numeric_continuous',
  'numeric_discrete',
  'categorical_nominal',
  'categorical_ordinal',
  'datetime',
  'identifier',
  'boolean',
  'text',
]

const CANONICAL_FIELDS: CanonicalField[] = [
  'product_name',
  'sku',
  'category',
  'transaction_date',
  'quantity',
  'unit_price',
  'transaction_type',
  'supplier',
  'customer',
  'note',
  'order_id',
  'ignore',
]

interface ColumnRowProps {
  view: ColumnViewModel
  isNotInventory: boolean
  mappingConflict?: string
  rationaleOpen: boolean
  onToggleRationale: () => void
  onSemanticTypeChange: (name: string, type: SemanticType) => void
  onCanonicalFieldChange: (name: string, field: CanonicalField) => void
  onActionChange: (name: string, action: TransformAction, params: Params) => void
}

export function ColumnRow({
  view,
  isNotInventory,
  mappingConflict,
  rationaleOpen,
  onToggleRationale,
  onSemanticTypeChange,
  onCanonicalFieldChange,
  onActionChange,
}: ColumnRowProps) {
  const { action } = view
  const rowClasses = [
    view.needsAttention ? 'tr--needs-attention' : '',
    action.canonical_field === 'ignore' ? 'tr--ignored' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <>
      <tr className={rowClasses || undefined}>
        <td>
          <span className="column-name">
            {view.needsAttention && <AlertTriangleIcon className="column-name__warning" />}
            {view.name}
            {action.edited_by_user && <span className="column-name__edited">edited</span>}
          </span>
        </td>
        <td>{view.dtype}</td>
        <td>
          <select
            className="select"
            value={action.semantic_type}
            onChange={(event) => {
              onSemanticTypeChange(view.name, event.target.value as SemanticType)
            }}
          >
            {SEMANTIC_TYPES.map((type) => (
              <option key={type} value={type}>
                {SEMANTIC_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </td>
        <td>
          {isNotInventory ? (
            <select className="select" value="ignore" disabled>
              <option value="ignore">Not available</option>
            </select>
          ) : (
            <>
              <select
                className="select"
                value={action.canonical_field}
                onChange={(event) => {
                  onCanonicalFieldChange(view.name, event.target.value as CanonicalField)
                }}
              >
                {CANONICAL_FIELDS.map((field) => (
                  <option key={field} value={field}>
                    {CANONICAL_FIELD_LABELS[field]}
                  </option>
                ))}
              </select>
              {mappingConflict && (
                <p className="mapping-conflict">Already mapped by {mappingConflict}</p>
              )}
            </>
          )}
        </td>
        <td>
          {action.canonical_field === 'ignore' ? (
            <span className="issues-empty">None</span>
          ) : (
            <IssueBadges issues={view.issues} canonicalField={action.canonical_field} />
          )}
        </td>
        <td>
          <ActionCell
            column={action}
            semanticType={action.semantic_type}
            canonicalField={action.canonical_field}
            rationaleOpen={rationaleOpen}
            onToggleRationale={onToggleRationale}
            onChange={(nextAction, params) => {
              onActionChange(view.name, nextAction, params)
            }}
          />
        </td>
        <td>{view.confidence === null ? '—' : <ConfidenceMeter value={view.confidence} />}</td>
      </tr>
      {rationaleOpen && action.rationale && (
        <tr>
          <td colSpan={7}>
            <div className="rationale">
              <InfoIcon className="rationale__icon" />
              <div>
                <p className="rationale__title">AI rationale</p>
                <p>{action.rationale}</p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
