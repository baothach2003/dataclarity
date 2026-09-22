// The Review screen's action bar (docs/SPECS.md section 4.2 D;
// design/mockups/Review · Confirm disabled (spec).png).

import { joinFieldLabels } from '../domain/labels.ts'
import type { CanonicalField } from '../types/contracts.ts'

interface ActionBarProps {
  isNotInventory: boolean
  missingFields: CanonicalField[]
  editedCount: number
  attentionCount: number
  canReset: boolean
  executing: boolean
  onCancel: () => void
  onReset: () => void
  onConfirm: () => void
}

export function ActionBar({
  isNotInventory,
  missingFields,
  editedCount,
  attentionCount,
  canReset,
  executing,
  onCancel,
  onReset,
  onConfirm,
}: ActionBarProps) {
  const blocked = !isNotInventory && missingFields.length > 0
  const confirmLabel = isNotInventory ? 'Clean & download' : 'Confirm & Clean'

  return (
    <div className="action-bar">
      <span className="action-bar__status">
        {isNotInventory
          ? 'Generic cleaning: downloads only'
          : blocked
            ? `Required fields not mapped: ${joinFieldLabels(missingFields)}`
            : `${String(editedCount)} column${editedCount === 1 ? '' : 's'} edited · ${String(attentionCount)} need attention`}
      </span>
      <div className="action-bar__buttons">
        <button type="button" className="link-button" onClick={onCancel} disabled={executing}>
          Cancel
        </button>
        <button
          type="button"
          className="button button--secondary"
          onClick={onReset}
          disabled={!canReset || executing}
        >
          Reset to AI proposal
        </button>
        <span className="tooltip-wrap">
          <button
            type="button"
            className="button button--primary"
            onClick={onConfirm}
            disabled={blocked || executing}
          >
            {executing ? 'Cleaning…' : confirmLabel}
          </button>
          {blocked && (
            <span className="tooltip" role="tooltip">
              Map product name, transaction date and quantity first
            </span>
          )}
        </span>
      </div>
    </div>
  )
}
