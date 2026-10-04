// Orchestrates the screens (docs/SPECS.md section 3): Upload -> Analyzing ->
// Review -> Results, then the analysis (stages 2-5) -> Insights (PROJECT_PLAN
// 6E; the Dashboard, 6F, is out of v1). A screen state machine, no router.

import { useState } from 'react'
import { analyzeSchema, getProfile, proposePlan } from './api/runs.ts'
import { Notice } from './components/Notice.tsx'
import { Stepper } from './components/Stepper.tsx'
import { describeError } from './domain/errorCopy.ts'
import { AnalysisFlow } from './pages/AnalysisFlow.tsx'
import { AnalyzingPage } from './pages/AnalyzingPage.tsx'
import type { AnalyzingStep } from './pages/AnalyzingPage.tsx'
import { ResultsPage } from './pages/ResultsPage.tsx'
import type { CleanedResult } from './pages/ReviewPage.tsx'
import { ReviewPage } from './pages/ReviewPage.tsx'
import { UploadPage } from './pages/UploadPage.tsx'
import type { UploadedRun } from './pages/UploadPage.tsx'
import type {
  CleaningPlan,
  CleaningReport,
  Notice as NoticeContract,
  ProfileContract,
  SchemaInferenceContract,
} from './types/contracts.ts'

type Screen =
  | { kind: 'upload' }
  | {
      kind: 'analyzing'
      runId: string
      filename: string
      step: AnalyzingStep
      rows: number | undefined
      columns: number | undefined
    }
  | {
      kind: 'review'
      runId: string
      filename: string
      profile: ProfileContract
      schema: SchemaInferenceContract | null
      plan: CleaningPlan | null
      notices: NoticeContract[]
    }
  | { kind: 'results'; runId: string; filename: string; report: CleaningReport; notices: NoticeContract[] }
  | { kind: 'insights'; results: ResultsScreen }
  | { kind: 'error'; error: unknown }

type ResultsScreen = Extract<Screen, { kind: 'results' }>

function dedupeNotices(notices: NoticeContract[]): NoticeContract[] {
  const byCode = new Map(notices.map((n) => [n.code, n]))
  return [...byCode.values()]
}

function App() {
  const baseUrl = import.meta.env.VITE_API_BASE_URL
  const [screen, setScreen] = useState<Screen>({ kind: 'upload' })

  async function runAnalyzing(url: string, runId: string, filename: string) {
    setScreen({ kind: 'analyzing', runId, filename, step: 'profiling', rows: undefined, columns: undefined })
    try {
      const schemaResponse = await analyzeSchema(url, runId)
      const profile = await getProfile(url, runId)
      setScreen({
        kind: 'analyzing',
        runId,
        filename,
        step: 'schema',
        rows: profile.dataset.rows,
        columns: profile.dataset.columns,
      })

      let plan: CleaningPlan | null = null
      let planNotices: NoticeContract[] = []
      if (schemaResponse.schema_inference) {
        setScreen({
          kind: 'analyzing',
          runId,
          filename,
          step: 'plan',
          rows: profile.dataset.rows,
          columns: profile.dataset.columns,
        })
        const planResponse = await proposePlan(url, runId)
        plan = planResponse.plan
        planNotices = planResponse.notices
      }

      setScreen({
        kind: 'review',
        runId,
        filename,
        profile,
        schema: schemaResponse.schema_inference,
        plan,
        notices: dedupeNotices([...schemaResponse.notices, ...planNotices]),
      })
    } catch (error) {
      setScreen({ kind: 'error', error })
    }
  }

  function handleUploaded(run: UploadedRun) {
    if (!baseUrl) {
      return
    }
    void runAnalyzing(baseUrl, run.runId, run.filename)
  }

  function handleCleaned(runId: string, filename: string) {
    return (result: CleanedResult) => {
      setScreen({ kind: 'results', runId, filename, report: result.report, notices: result.notices })
    }
  }

  function backToUpload() {
    setScreen({ kind: 'upload' })
  }

  switch (screen.kind) {
    case 'upload':
      return <UploadPage baseUrl={baseUrl} onUploaded={handleUploaded} />
    case 'analyzing':
      return (
        <AnalyzingPage
          filename={screen.filename}
          rows={screen.rows}
          columns={screen.columns}
          step={screen.step}
        />
      )
    case 'review':
      return (
        baseUrl && (
          <ReviewPage
            baseUrl={baseUrl}
            runId={screen.runId}
            filename={screen.filename}
            profile={screen.profile}
            schema={screen.schema}
            initialPlan={screen.plan}
            notices={screen.notices}
            onCancel={backToUpload}
            onCleaned={handleCleaned(screen.runId, screen.filename)}
          />
        )
      )
    case 'results':
      return (
        baseUrl && (
          <ResultsPage
            baseUrl={baseUrl}
            runId={screen.runId}
            filename={screen.filename}
            report={screen.report}
            notices={screen.notices}
            onRunAnalysis={() => {
              setScreen({ kind: 'insights', results: screen })
            }}
          />
        )
      )
    case 'insights': {
      const results = screen.results
      return (
        baseUrl && (
          <AnalysisFlow
            baseUrl={baseUrl}
            runId={results.runId}
            filename={results.filename}
            rows={results.report.rows_out}
            onBack={() => {
              setScreen(results)
            }}
          />
        )
      )
    }
    case 'error': {
      const copy = describeError(screen.error)
      return (
        <div className="app-shell">
          <Stepper collectStatus="active" />
          <div className="page">
            <Notice
              tone="error"
              title={copy.title}
              actions={
                <button type="button" className="button button--secondary" onClick={backToUpload}>
                  Upload a different file
                </button>
              }
            >
              {copy.detail}
            </Notice>
          </div>
        </div>
      )
    }
  }
}

export default App
