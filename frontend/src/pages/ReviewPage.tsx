// Review screen (docs/SPECS.md section 4.2; design/mockups/Review.png and its
// variants). The core screen: the user edits the plan, the preview refreshes
// 400ms after every edit, and Confirm & Clean executes exactly the plan shown
// (docs/SPECS.md section 5, the Confirmation Contract).

import { useEffect, useMemo, useState } from 'react'
import { executePlan, previewPlan, proposePlan } from '../api/runs.ts'
import { ActionBar } from '../components/ActionBar.tsx'
import { ColumnsTable } from '../components/ColumnsTable.tsx'
import { Notice } from '../components/Notice.tsx'
import { NonProductNotice } from '../components/NonProductNotice.tsx'
import { OrderNotices } from '../components/OrderNotices.tsx'
import { PlaceholderNotices } from '../components/PlaceholderNotices.tsx'
import { PreviewPane } from '../components/PreviewPane.tsx'
import { Stepper } from '../components/Stepper.tsx'
import { SummaryStrip } from '../components/SummaryStrip.tsx'
import { buildColumnViewModels } from '../domain/columnView.ts'
import { describeError } from '../domain/errorCopy.ts'
import { mappingConflict, missingRequiredFields } from '../domain/planRules.ts'
import { buildManualPlan, reconcileAction, withMappingDisabled } from '../domain/reviewPlan.ts'
import { defaultParams } from '../domain/transformParams.ts'
import { useOrderAnswers } from './useOrderAnswers.ts'
import type {
  CanonicalField,
  CleaningPlan,
  CleaningReport,
  Notice as NoticeContract,
  Params,
  PreviewResult,
  ProfileContract,
  SchemaInferenceContract,
  SemanticType,
  TransformAction,
} from '../types/contracts.ts'

const PREVIEW_DEBOUNCE_MS = 400

export interface CleanedResult {
  report: CleaningReport
  notices: NoticeContract[]
}

interface ReviewPageProps {
  baseUrl: string
  runId: string
  filename: string
  profile: ProfileContract
  schema: SchemaInferenceContract | null
  initialPlan: CleaningPlan | null
  notices: NoticeContract[]
  onCancel: () => void
  onCleaned: (result: CleanedResult) => void
}

export function ReviewPage({
  baseUrl,
  runId,
  filename,
  profile,
  schema,
  initialPlan,
  notices,
  onCancel,
  onCleaned,
}: ReviewPageProps) {
  const [aiProposal, setAiProposal] = useState(initialPlan)
  const [plan, setPlan] = useState<CleaningPlan>(() => initialPlan ?? buildManualPlan(profile, schema))
  const orderAnswers = useOrderAnswers(plan, schema, profile)
  const [activeNotices, setActiveNotices] = useState(notices)
  const [mappingConflicts, setMappingConflicts] = useState<Map<string, string>>(new Map())
  const [notInventoryAcknowledged, setNotInventoryAcknowledged] = useState(false)
  const [retryingAi, setRetryingAi] = useState(false)

  const [preview, setPreview] = useState<PreviewResult | null>(null)
  // The plan `preview` reflects; differs from `planToSubmit` while a debounced
  // preview request is pending or in flight (react-hooks/set-state-in-effect
  // forbids setting a loading flag synchronously at the top of the effect).
  const [previewedPlan, setPreviewedPlan] = useState<CleaningPlan | null>(null)
  const [previewError, setPreviewError] = useState<unknown>(null)

  const [executing, setExecuting] = useState(false)
  const [executeError, setExecuteError] = useState<unknown>(null)

  const notInventoryNotice = activeNotices.find((n) => n.code === 'NOT_INVENTORY')
  const aiUnavailableNotice = activeNotices.find((n) => n.code === 'AI_UNAVAILABLE')
  const isNotInventory = notInventoryNotice !== undefined

  const planToSubmit = useMemo(
    () => (isNotInventory ? withMappingDisabled(plan) : plan),
    [isNotInventory, plan],
  )

  const previewLoading = previewedPlan !== planToSubmit

  // Preview refreshes 400ms after the last edit (SPECS 4.2 C), cancelling a
  // request superseded by a newer edit before it answers.
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => {
      previewPlan(baseUrl, runId, planToSubmit, controller.signal)
        .then((response) => {
          setPreview(response.preview)
          setPreviewError(null)
          setPreviewedPlan(planToSubmit)
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setPreviewError(error)
            setPreviewedPlan(planToSubmit)
          }
        })
    }, PREVIEW_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [baseUrl, runId, planToSubmit])

  const columns = useMemo(() => buildColumnViewModels(profile, schema, plan), [profile, schema, plan])
  const missingFields = isNotInventory ? [] : missingRequiredFields(plan)
  const editedCount = plan.column_actions.filter((c) => c.edited_by_user).length
  const attentionCount = columns.filter((c) => c.needsAttention).length

  function patchColumn(name: string, patch: Partial<CleaningPlan['column_actions'][number]>) {
    setPlan((current) => ({
      ...current,
      column_actions: current.column_actions.map((column) =>
        column.source_name === name ? { ...column, ...patch, edited_by_user: true } : column,
      ),
    }))
  }

  function handleSemanticTypeChange(name: string, type: SemanticType) {
    const column = plan.column_actions.find((c) => c.source_name === name)
    if (!column) {
      return
    }
    const reconciled = reconcileAction(column, type, column.canonical_field)
    patchColumn(name, { semantic_type: type, ...reconciled })
  }

  function handleCanonicalFieldChange(name: string, field: CanonicalField) {
    const conflictWith = mappingConflict(plan, name, field)
    setMappingConflicts((current) => {
      const next = new Map(current)
      if (conflictWith) {
        next.set(name, conflictWith)
      } else {
        next.delete(name)
      }
      return next
    })
    if (conflictWith) {
      return
    }
    const column = plan.column_actions.find((c) => c.source_name === name)
    if (!column) {
      return
    }
    const reconciled = reconcileAction(column, column.semantic_type, field)
    patchColumn(name, { canonical_field: field, ...reconciled })
  }

  function handleActionChange(name: string, action: TransformAction, params: Params) {
    patchColumn(name, { action, params })
  }

  function handleReset() {
    if (aiProposal) {
      setPlan(aiProposal)
      setMappingConflicts(new Map())
    }
  }

  const handleConfirm = async () => {
    setExecuting(true)
    setExecuteError(null)
    try {
      const result = await executePlan(baseUrl, runId, orderAnswers.confirmed(planToSubmit))
      onCleaned({ report: result.report, notices: result.notices })
    } catch (error) {
      setExecuteError(error)
    } finally {
      setExecuting(false)
    }
  }

  const handleRetryAi = async () => {
    setRetryingAi(true)
    try {
      const response = await proposePlan(baseUrl, runId)
      setActiveNotices(response.notices)
      if (response.plan) {
        setAiProposal(response.plan)
        setPlan(response.plan)
      }
    } catch (error) {
      setExecuteError(error)
    } finally {
      setRetryingAi(false)
    }
  }

  return (
    <div className="app-shell">
      <Stepper collectStatus="active" />
      <div className="page">
        <div>
          <h1 className="page__title">Review cleaning plan</h1>
          <p className="page__subtitle">
            {filename} · {aiProposal ? 'AI proposal ready' : 'Manual plan'}
            {attentionCount > 0 && !isNotInventory && `, ${String(attentionCount)} columns need attention`}
          </p>
        </div>

        <SummaryStrip
          rows={profile.dataset.rows}
          columns={profile.dataset.columns}
          duplicateRows={profile.dataset.duplicate_rows}
          missingCellsPct={profile.dataset.missing_cells_pct}
          domainConfidence={schema?.domain_confidence ?? 1}
          isNotInventory={isNotInventory}
        />

        {notInventoryNotice && !notInventoryAcknowledged && (
          <Notice
            tone="warning"
            title={notInventoryNotice.message}
            actions={
              <>
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={() => {
                    setNotInventoryAcknowledged(true)
                  }}
                >
                  Continue with generic cleaning
                </button>
                <button type="button" className="link-button" onClick={onCancel}>
                  Upload a different file
                </button>
              </>
            }
          >
            You can still clean it and download the result. Column mapping, import to the
            dashboard and the analysis stages are turned off for this file.
          </Notice>
        )}

        {aiUnavailableNotice && (
          <Notice
            tone="warning"
            title="AI suggestions are unavailable right now"
            actions={
              <>
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={() => {
                    setActiveNotices((current) => current.filter((n) => n.code !== 'AI_UNAVAILABLE'))
                  }}
                >
                  Build plan manually
                </button>
                <button
                  type="button"
                  className="link-button"
                  disabled={retryingAi}
                  onClick={() => {
                    void handleRetryAi()
                  }}
                >
                  {retryingAi ? 'Trying again…' : 'Try AI again'}
                </button>
              </>
            }
          >
            Profiling is done. You can build the cleaning plan by hand, and preview and cleaning
            work as normal.
          </Notice>
        )}

        {!isNotInventory && (
          <>
            <PlaceholderNotices
              candidates={orderAnswers.candidates}
              answers={orderAnswers.placeholderAnswers}
              onAnswer={orderAnswers.answerPlaceholder}
            />
            <NonProductNotice
              candidates={orderAnswers.lineCandidates}
              answers={orderAnswers.lineAnswers}
              onAnswer={orderAnswers.answerLine}
            />
            <OrderNotices
              plan={plan}
              answers={orderAnswers.answers}
              placeholders={orderAnswers.placeholders}
              profile={profile}
              schema={schema}
              onAnswer={orderAnswers.answer}
              onDropBlankIds={(name) => { handleActionChange(name, 'drop_rows_missing', defaultParams('drop_rows_missing')) }}
              onUploadFixed={onCancel}
            />
          </>
        )}

        <ColumnsTable
          columns={columns}
          isNotInventory={isNotInventory}
          mappingConflicts={mappingConflicts}
          onSemanticTypeChange={handleSemanticTypeChange}
          onCanonicalFieldChange={handleCanonicalFieldChange}
          onActionChange={handleActionChange}
        />

        <PreviewPane preview={preview} loading={previewLoading} plan={previewedPlan ?? plan} />

        {previewError !== null &&
          (() => {
            const copy = describeError(previewError)
            return (
              <Notice tone="error" title={copy.title}>
                {copy.detail}
              </Notice>
            )
          })()}

        {executeError !== null &&
          (() => {
            const copy = describeError(executeError)
            return (
              <Notice
                tone="error"
                title={copy.title}
                actions={
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={() => {
                      setExecuteError(null)
                    }}
                  >
                    Back to review
                  </button>
                }
              >
                {copy.detail}
              </Notice>
            )
          })()}

        <ActionBar
          isNotInventory={isNotInventory}
          missingFields={missingFields}
          editedCount={editedCount}
          attentionCount={attentionCount}
          canReset={aiProposal !== null}
          executing={executing}
          onCancel={onCancel}
          onReset={handleReset}
          onConfirm={() => {
            void handleConfirm()
          }}
        />
      </div>
    </div>
  )
}
