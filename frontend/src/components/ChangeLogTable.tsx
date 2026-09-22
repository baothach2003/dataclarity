// "What ran" table (docs/SPECS.md section 4.3: "Expandable per-action
// detail"). Expanding shows the action's params, the only extra detail
// `cleaning_report.json` actually carries per entry — the mockup's per-row
// reasons and row indices are not in the contract (see ReviewPage's
// PreviewPane note on the same gap) and are not fabricated here.

import { Fragment, useState } from 'react'
import { changeLogActionLabel, changeLogAffected } from '../domain/changeLogLabels.ts'
import { ChevronDownIcon } from './Icon.tsx'
import type { ChangeLogEntry } from '../types/contracts.ts'

interface ChangeLogTableProps {
  changes: ChangeLogEntry[]
}

export function ChangeLogTable({ changes }: ChangeLogTableProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null)

  return (
    <table className="change-log-table">
      <thead>
        <tr>
          <th>Action</th>
          <th>Column</th>
          <th>Affected</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {changes.map((entry, index) => {
          const params = Object.entries(entry.params)
          const expandable = params.length > 0
          const expanded = expandedIndex === index
          return (
            <Fragment key={index}>
              <tr
                className={expandable ? 'change-log-row' : undefined}
                onClick={
                  expandable
                    ? () => {
                        setExpandedIndex((current) => (current === index ? null : index))
                      }
                    : undefined
                }
              >
                <td>
                  {expandable && (
                    <ChevronDownIcon
                      className={expanded ? undefined : 'icon-collapsed'}
                    />
                  )}{' '}
                  {changeLogActionLabel(entry)}
                </td>
                <td>{entry.column ?? 'all columns'}</td>
                <td>{changeLogAffected(entry)}</td>
                <td className="change-log-detail">{entry.detail}</td>
              </tr>
              {expanded && (
                <tr className="change-log-expand">
                  <td colSpan={4}>
                    <div className="change-log-expand__content">
                      {params.map(([key, value]) => (
                        <span key={key}>
                          {key}: {JSON.stringify(value)}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          )
        })}
      </tbody>
    </table>
  )
}
