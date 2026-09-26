// Building and adjusting the working plan on the Review screen. The backend
// only ever proposes a plan when the AI answered (stage 1 step C); when it did
// not (AI_UNAVAILABLE), the user builds one by hand from the transform catalog
// (docs/AI_PIPELINE.md section 9) — `buildManualPlan` seeds that starting
// point with the safest legal action per column (`flag_only`, always legal:
// docs/AI_PIPELINE.md section 6), changing nothing until the user says so.

import { legalColumnActions } from './transformCatalog.ts'
import { defaultParams } from './transformParams.ts'
import type {
  CanonicalField,
  CleaningPlan,
  ColumnAction,
  ColumnInference,
  ProfileContract,
  SchemaInferenceContract,
  SemanticType,
} from '../types/contracts.ts'

const FALLBACK_SEMANTIC_TYPE: SemanticType = 'text'
const FALLBACK_CANONICAL_FIELD: CanonicalField = 'ignore'

function inferenceByName(schema: SchemaInferenceContract): Map<string, ColumnInference> {
  return new Map(schema.columns.map((column) => [column.source_name, column]))
}

/** A plan the user builds from scratch: every column defaults to `flag_only`
 * (changes nothing, always legal), using the AI's semantic type and mapping
 * where it analyzed the column (`schema`, capped at 25 columns) and a neutral
 * fallback beyond that. */
export function buildManualPlan(profile: ProfileContract, schema: SchemaInferenceContract | null): CleaningPlan {
  const inferred = schema ? inferenceByName(schema) : new Map<string, ColumnInference>()
  const columnActions: ColumnAction[] = profile.columns.map((column) => {
    const inference = inferred.get(column.name)
    const semanticType = inference?.semantic_type ?? FALLBACK_SEMANTIC_TYPE
    const canonicalField = inference?.canonical_field ?? FALLBACK_CANONICAL_FIELD
    return {
      source_name: column.name,
      semantic_type: semanticType,
      canonical_field: canonicalField,
      action: 'flag_only',
      params: defaultParams('flag_only'),
      rationale: '',
      alternatives: [],
      edited_by_user: false,
    }
  })
  return {
    // The plan contract's major (2.0 since 2E-e: order_id widened the canonical
    // enum; 2.1 in 2E-e2, 2.2 since 2E-k: confirmations). A '1.0' manual plan
    // was refused, so the no-AI path could not clean.
    schema_version: '2.2',
    generated_at: new Date().toISOString(),
    source: 'manual',
    dataset_actions: [],
    column_actions: columnActions,
    confirmations: { order_id_is_receipt: null, customer_on_first_line_only: null },
  }
}

/** `plan` with every column-action's mapping cleared: the Review - Not
 * Inventory state (design/mockups/Review - Not Inventory.png) disables mapping
 * entirely, and the backend's generic-cleaning path for a NOT_INVENTORY run
 * expects nothing mapped (`execute_run(require_required_fields=False)`,
 * PROJECT_PLAN.md Phase 1 1G notes). */
export function withMappingDisabled(plan: CleaningPlan): CleaningPlan {
  return {
    ...plan,
    column_actions: plan.column_actions.map((column) => ({ ...column, canonical_field: 'ignore' })),
  }
}

/** After `semanticType` or `canonicalField` changes, the column's action may no
 * longer be legal (SPECS 4.2: "changing semantic type re-filters the legal
 * action list"). Keeps the current action when it is still legal, otherwise
 * falls back to the first legal action's default params. */
export function reconcileAction(
  column: ColumnAction,
  semanticType: SemanticType,
  canonicalField: CanonicalField,
): Pick<ColumnAction, 'action' | 'params'> {
  const legal = legalColumnActions(semanticType, canonicalField)
  if (legal.includes(column.action)) {
    return { action: column.action, params: column.params }
  }
  const fallback = legal.includes('flag_only') ? 'flag_only' : (legal[0] ?? 'flag_only')
  return { action: fallback, params: defaultParams(fallback) }
}
