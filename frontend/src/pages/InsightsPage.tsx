// The Insights page (docs/SPECS.md section 4.4; docs/FIGMA_DESIGN_NOTES.md frame `Insights`, node
// 4:1489) with the design gap decisions (Thach, 2026-10-03; PROJECT_PLAN 6E). It renders report.json as
// stage 5's report.html does - the same rules, the same words where it can - and computes nothing:
// every figure is the file's, a null shown with its reason (CLAUDE.md 3.2; CONTRACTS 9 and 11).

import { useState } from 'react'
import { downloadReportHtml } from '../api/analysis.ts'
import type { OrdersBasis } from '../api/analysis.ts'
import { CausesSection } from '../components/CausesSection.tsx'
import { DecompositionCard } from '../components/DecompositionCard.tsx'
import { ForecastCard } from '../components/ForecastCard.tsx'
import { KpiCard } from '../components/KpiCard.tsx'
import { LinesInNoFigureCard } from '../components/LinesInNoFigureCard.tsx'
import { NoteBody } from '../components/NoteBody.tsx'
import { Notice } from '../components/Notice.tsx'
import type { NoticeTone } from '../components/Notice.tsx'
import { RecommendationsSection } from '../components/RecommendationsSection.tsx'
import { RevenueChartCard } from '../components/RevenueChartCard.tsx'
import { Stepper } from '../components/Stepper.tsx'
import { triggerBlobDownload } from '../domain/browserDownload.ts'
import { readDiagnosis } from '../domain/diagnosisView.ts'
import { describeError } from '../domain/errorCopy.ts'
import { count, monthLabel } from '../domain/reportFormat.ts'
import type { Numbers, ReportContract, TrustBadge, TrustVerdict } from '../types/report.ts'

// stage 5's words for the badge (stages/report/html_report.py _VERDICTS).
const VERDICTS: Record<TrustVerdict, string> = {
  trusted: 'trusted',
  caution: 'caution',
  blocked: 'blocked - the figures below are not a base for conclusions',
}
const TONES: Record<TrustVerdict, NoticeTone> = { trusted: 'success', caution: 'warning', blocked: 'error' }

interface InsightsPageProps {
  baseUrl: string
  runId: string
  report: ReportContract
  // diagnosis.json from the diagnose answer (only CONTRACTS 11's FE fields are read) and metrics.json's
  // order basis: the decomposition card and the table's verdict labels.
  diagnosis: unknown
  ordersBasis: OrdersBasis
}

function periodHead(numbers: Numbers): string {
  const { period } = numbers
  const current = monthLabel(period.current)
  const previous = monthLabel(period.previous)
  const withheld = numbers.kpis[0]?.current === null
  if (!period.previous_complete) {
    return `${current}; ${previous} is not compared${withheld ? "; the current month's figures are withheld (see below)" : ''}`
  }
  if (withheld) {
    return `${current} against ${previous}: the current month's figures are withheld (see below)`
  }
  return `${current} compared with ${previous}`
}

/** What qualifies the KPIs, said once under them (the design gap review's ADD 10): why the previous
 * month is not compared, a month the file starts inside, walk-in candidates nobody confirmed. */
function aboutLines(numbers: Numbers): string[] {
  return [numbers.period.previous_incomplete_reason, numbers.current_note, numbers.unconfirmed_placeholders_reason].filter(
    (line): line is string => typeof line === 'string' && line !== '',
  )
}

function TrustNotice({ trust }: { trust: TrustBadge }) {
  const lines = [
    ...trust.checks.map((check) => `${check.id} (${check.status.replace('_', ' ')}): ${check.message}`),
    ...trust.limitations,
  ]
  return (
    <Notice tone={TONES[trust.verdict]} title={`Data trust: ${VERDICTS[trust.verdict]}`}>
      {lines.length > 0
        ? lines.map((line, index) => (
            // Two lines may read alike; their place is their identity.
            <span className="notice__line" key={index}>
              {line}
            </span>
          ))
        : undefined}
    </Notice>
  )
}

function reportFilename(sourceFile: string): string {
  return `report_${sourceFile.replace(/\.csv$/i, '')}.html`
}

export function InsightsPage({ baseUrl, runId, report, diagnosis, ordersBasis }: InsightsPageProps) {
  const [downloadError, setDownloadError] = useState<unknown>(null)
  const numbers = report.layer_1_numbers
  const view = readDiagnosis(diagnosis)
  const revenueChart = report.charts.find((chart) => chart.id === 'revenue_trend')
  const forecastChart = report.charts.find((chart) => chart.id === 'forecast')
  const { period } = numbers
  const about = aboutLines(numbers)
  const quality = report.data_quality
  const provenance = report.provenance
  const models = provenance.models_used.length > 0 ? ` (${provenance.models_used.join(', ')})` : ''
  // The notes the report shows beside figures: layer 1's, and the causes' a KPI may name (contracts/
  // report.py allows a KPI to name either; the 6E1 review #12).
  const shownCodes = new Set(numbers.notes.map((note) => note.code))
  const besideFigures = [...numbers.notes, ...report.layer_2_causes.notes.filter((note) => !shownCodes.has(note.code))]
  const unconfirmedWalkIns = Boolean(numbers.unconfirmed_placeholders_reason)

  const handleDownload = async () => {
    setDownloadError(null)
    try {
      triggerBlobDownload(await downloadReportHtml(baseUrl, runId), reportFilename(report.source_file))
    } catch (error) {
      setDownloadError(error)
    }
  }

  return (
    <div className="app-shell">
      {/* Every stage done, nothing running (the 6E1 review #6). */}
      <Stepper progress={{ done: 5, active: null }} />
      <div className="page">
        <div>
          <h1 className="page__title">Insights</h1>
          <p className="page__subtitle">
            {`${report.source_file} · ${periodHead(numbers)} · the file covers ${period.data_start} to ${period.data_end}`}
          </p>
          {numbers.future_lines_reason && (
            // Why the dates covered end before the file's last line - beside those dates, as report.html
            // puts it (2E-u6; the 6E1 review #20).
            <p className="insights-reason">{numbers.future_lines_reason}</p>
          )}
        </div>

        <TrustNotice trust={numbers.trust} />

        <div className="kpi-row">
          {numbers.kpis.map((kpi) => (
            <KpiCard key={kpi.id} kpi={kpi} period={period} notes={besideFigures} unconfirmedWalkIns={unconfirmedWalkIns} />
          ))}
        </div>

        {about.length > 0 && (
          <Notice tone="info" title="About these figures">
            {about.map((line) => (
              <span className="notice__line" key={line}>
                {line}
              </span>
            ))}
          </Notice>
        )}

        {/* Number -> cause (FIGMA_DESIGN_NOTES 9): the change split, then why. */}
        <DecompositionCard view={view} numbers={numbers} ordersBasis={ordersBasis} notes={besideFigures} />
        <CausesSection causes={report.layer_2_causes} numbers={numbers} />

        {/* Cause -> what next: the months, the forecast, the recommendations' place (off in v1). */}
        {(revenueChart || numbers.revenue_by_month.length > 0) && (
          <RevenueChartCard chart={revenueChart} numbers={numbers} notes={besideFigures} />
        )}
        <ForecastCard forecast={report.layer_3_actions.forecast} chart={forecastChart} notes={besideFigures} period={period} />
        <RecommendationsSection actions={report.layer_3_actions} notes={besideFigures} period={period} />

        {/* The data-quality section: what no figure counts, the file, how to read the figures. */}
        <LinesInNoFigureCard numbers={numbers} />

        <section className="card insights-card">
          <h2 className="insights-card__title">The file and where these figures come from</h2>
          <p>
            {`Rows in: ${count(quality.rows_in)}. Rows out: ${count(quality.rows_out)}. Changes that did something: ${count(quality.issues_fixed)}. Warnings: ${count(quality.warnings)}.`}
          </p>
          <p>
            {/* An AI answer can be a column mapping or a cleaning plan, not only words - but never a figure
                (CLAUDE.md 3.2; the 6E1 review #9; stage 5 says the same). */}
            {`Stages run: ${provenance.stages_run.join(', ')}. AI answers used: ${count(provenance.ai_calls)}${models}. Every figure is computed by code from the earlier stages' files; the AI computes none.`}
          </p>
        </section>

        {numbers.how_to_read.length > 0 && (
          <section className="card insights-card">
            <h2 className="insights-card__title">How to read these figures</h2>
            {numbers.how_to_read.map((note) => (
              <NoteBody key={note.code} note={note} period={period} />
            ))}
          </section>
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

        <div className="action-bar insights-footer">
          <p className="insights-footer__caption">The figures, causes and forecast in one file you can share</p>
          <button
            type="button"
            className="button button--primary"
            onClick={() => {
              void handleDownload()
            }}
          >
            Download HTML report
          </button>
        </div>
      </div>
    </div>
  )
}
