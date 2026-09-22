// Results page (docs/SPECS.md section 4.3; design/mockups/Results.png).

import { useState } from 'react'
import { downloadCleanedCsv } from '../api/runs.ts'
import { ChangeLogTable } from '../components/ChangeLogTable.tsx'
import { CheckCircleIcon } from '../components/Icon.tsx'
import { Notice } from '../components/Notice.tsx'
import { Stepper } from '../components/Stepper.tsx'
import { downloadJson, triggerBlobDownload } from '../domain/browserDownload.ts'
import { describeError } from '../domain/errorCopy.ts'
import { buildSummaryTiles, changesWithEffect } from '../domain/resultsSummary.ts'
import type { CleaningReport, Notice as NoticeContract } from '../types/contracts.ts'

interface ResultsPageProps {
  baseUrl: string
  runId: string
  filename: string
  report: CleaningReport
  notices: NoticeContract[]
}

export function ResultsPage({ baseUrl, runId, filename, report, notices }: ResultsPageProps) {
  const [downloadError, setDownloadError] = useState<unknown>(null)
  const tiles = buildSummaryTiles(report)
  const effectiveChanges = changesWithEffect(report)
  const isNotInventory = notices.some((n) => n.code === 'NOT_INVENTORY')

  const handleDownloadCsv = async () => {
    setDownloadError(null)
    try {
      const blob = await downloadCleanedCsv(baseUrl, runId)
      triggerBlobDownload(blob, `cleaned_${filename}`)
    } catch (error) {
      setDownloadError(error)
    }
  }

  return (
    <div className="app-shell">
      <Stepper collectStatus="done" />
      <div className="page">
        <div>
          <h1 className="page__title">
            <CheckCircleIcon /> Cleaning complete
          </h1>
          <p className="page__subtitle">
            {filename} · {effectiveChanges.length} action{effectiveChanges.length === 1 ? '' : 's'} ran
            exactly as you confirmed them
          </p>
        </div>

        {isNotInventory && (
          <Notice tone="warning" title="Generic cleaning only">
            This file did not look like inventory or sales data, so import and the analysis stages
            stay unavailable for it.
          </Notice>
        )}

        <div className="summary-strip">
          {tiles.map((tile) => (
            <div className="summary-tile" key={tile.label}>
              <p className="summary-tile__label">{tile.label}</p>
              <p className="summary-tile__value">{tile.value.toLocaleString()}</p>
              {tile.caption && <p className="summary-tile__caption">{tile.caption}</p>}
            </div>
          ))}
        </div>

        <section className="card">
          <h2 className="columns-card__title">What ran</h2>
          <ChangeLogTable changes={effectiveChanges} />
        </section>

        {report.warnings.length > 0 && (
          <Notice tone="info" title="Warnings">
            {report.warnings.map((w) => w.detail).join(' ')}
          </Notice>
        )}

        {downloadError !== null &&
          (() => {
            const copy = describeError(downloadError)
            return (
              <Notice tone="error" title={copy.title}>
                {copy.detail}
              </Notice>
            )
          })()}

        <div className="action-bar results-footer">
          <div className="results-downloads">
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                void handleDownloadCsv()
              }}
            >
              Download cleaned_{filename}
            </button>
            <button
              type="button"
              className="button button--secondary"
              onClick={() => {
                downloadJson(report, 'cleaning_report.json')
              }}
            >
              Download cleaning_report.json
            </button>
          </div>
          <div className="results-actions">
            <span className="tooltip-wrap">
              <button type="button" className="button button--secondary" disabled>
                Import to dashboard
              </button>
              <span className="tooltip" role="tooltip">
                Not available yet: Phase 7 (import) is not built
              </span>
            </span>
            <span className="tooltip-wrap">
              <button type="button" className="button button--primary" disabled>
                Run full analysis
              </button>
              <span className="tooltip" role="tooltip">
                Not available yet: Phases 2-5 are not built
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
