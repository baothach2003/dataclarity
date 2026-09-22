// The Action cell of one column row (docs/SPECS.md section 4.2 B): a dropdown
// of the actions legal for the column's current semantic type and mapping,
// its params, and a toggle for the AI's rationale.

import { ACTION_LABELS, legalColumnActions } from '../domain/transformCatalog.ts'
import { defaultParams, hasParams } from '../domain/transformParams.ts'
import { ActionParamsEditor } from './ActionParamsEditor.tsx'
import { InfoIcon } from './Icon.tsx'
import type { CanonicalField, ColumnAction, Params, SemanticType, TransformAction } from '../types/contracts.ts'

interface ActionCellProps {
  column: ColumnAction
  semanticType: SemanticType
  canonicalField: CanonicalField
  onChange: (action: TransformAction, params: Params) => void
  rationaleOpen: boolean
  onToggleRationale: () => void
  disabled?: boolean
}

export function ActionCell({
  column,
  semanticType,
  canonicalField,
  onChange,
  rationaleOpen,
  onToggleRationale,
  disabled,
}: ActionCellProps) {
  const legal = legalColumnActions(semanticType, canonicalField)
  // The action a stale plan carries might no longer be legal for the current
  // type/mapping (the caller reconciles this on change - domain/reviewPlan.ts
  // reconcileAction); still listing it here keeps the select from silently
  // showing the wrong value while that happens.
  const options = legal.includes(column.action) ? legal : [column.action, ...legal]

  return (
    <div className="action-cell">
      <div className="action-params__row">
        <select
          className="select"
          value={column.action}
          disabled={disabled}
          onChange={(event) => {
            const action = event.target.value as TransformAction
            onChange(action, defaultParams(action))
          }}
        >
          {options.map((action) => (
            <option key={action} value={action}>
              {ACTION_LABELS[action]}
            </option>
          ))}
        </select>
        {column.rationale && (
          <button
            type="button"
            className="link-button"
            aria-expanded={rationaleOpen}
            aria-label={rationaleOpen ? 'Hide AI rationale' : 'Show AI rationale'}
            onClick={onToggleRationale}
          >
            <InfoIcon />
          </button>
        )}
      </div>
      {!disabled && hasParams(column.action) && (
        <div className="action-params">
          <ActionParamsEditor
            action={column.action}
            params={column.params}
            onChange={(params) => {
              onChange(column.action, params)
            }}
          />
        </div>
      )}
    </div>
  )
}
