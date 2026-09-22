// Dataset summary strip (docs/SPECS.md section 4.2 A; design/mockups/Review.png).

import { ConfidenceMeter } from './ConfidenceMeter.tsx'

interface SummaryStripProps {
  rows: number
  columns: number
  duplicateRows: number
  missingCellsPct: number
  domainConfidence: number
  isNotInventory: boolean
}

export function SummaryStrip({
  rows,
  columns,
  duplicateRows,
  missingCellsPct,
  domainConfidence,
  isNotInventory,
}: SummaryStripProps) {
  return (
    <div className="summary-strip">
      <div className="summary-tile">
        <p className="summary-tile__label">Rows</p>
        <p className="summary-tile__value">{rows.toLocaleString()}</p>
      </div>
      <div className="summary-tile">
        <p className="summary-tile__label">Columns</p>
        <p className="summary-tile__value">{columns.toLocaleString()}</p>
      </div>
      <div className="summary-tile">
        <p className="summary-tile__label">Duplicate rows</p>
        <p className="summary-tile__value">{duplicateRows.toLocaleString()}</p>
      </div>
      <div className="summary-tile">
        <p className="summary-tile__label">Missing cells</p>
        <p className="summary-tile__value">{missingCellsPct.toFixed(1)}%</p>
      </div>
      <div className="summary-tile">
        <p className="domain-confidence__label">Domain confidence</p>
        <div className="domain-confidence__meter">
          <ConfidenceMeter value={domainConfidence} label="Domain confidence" />
          <span className="domain-confidence__tag">
            {isNotInventory ? 'Not inventory' : 'Inventory / sales'}
          </span>
        </div>
      </div>
    </div>
  )
}
