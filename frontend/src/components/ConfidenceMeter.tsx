// Confidence meter (docs/FIGMA_DESIGN_NOTES.md section 5, node `1:334`): a bar
// plus the numeric value. Below 0.70 is the SPECS 4.2 "needs attention"
// threshold, shown in the medium-severity color; color is never the only
// signal, so the number is always printed too (SPECS section 11).

export const LOW_CONFIDENCE_BELOW = 0.7

interface ConfidenceMeterProps {
  value: number
  label?: string
}

export function ConfidenceMeter({ value, label }: ConfidenceMeterProps) {
  const low = value < LOW_CONFIDENCE_BELOW
  return (
    <span className="confidence" aria-label={`${label ?? 'Confidence'}: ${value.toFixed(2)}`}>
      <span className="confidence__track">
        <span
          className={'confidence__fill' + (low ? ' confidence__fill--low' : '')}
          style={{ width: `${String(Math.max(0, Math.min(1, value)) * 100)}%` }}
        />
      </span>
      <span className="confidence__value">{value.toFixed(2)}</span>
    </span>
  )
}
