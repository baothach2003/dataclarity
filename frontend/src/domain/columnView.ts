// One row of the Review columns table: profile.json (dtype), schema_inference
// (confidence, issues — absent for a column past the AI's 25-column cap,
// docs/CONTRACTS.md section 4) and the working plan's column action zipped
// together by source column name.

import { LOW_CONFIDENCE_BELOW } from '../components/ConfidenceMeter.tsx'
import type {
  ColumnAction,
  ColumnInference,
  ColumnIssue,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'

export interface ColumnViewModel {
  name: string
  dtype: string
  confidence: number | null
  issues: ColumnIssue[]
  action: ColumnAction
  needsAttention: boolean
}

interface CleaningPlanLike {
  column_actions: ColumnAction[]
}

export function buildColumnViewModels(
  profile: ProfileContract,
  schema: SchemaInferenceContract | null,
  plan: CleaningPlanLike,
): ColumnViewModel[] {
  const inferred = new Map<string, ColumnInference>(
    schema?.columns.map((c) => [c.source_name, c] as const) ?? [],
  )
  const dtypeByName = new Map(profile.columns.map((c) => [c.name, c.dtype] as const))

  return plan.column_actions.map((action) => {
    const inference = inferred.get(action.source_name)
    const confidence = inference?.confidence ?? null
    return {
      name: action.source_name,
      dtype: dtypeByName.get(action.source_name) ?? '',
      confidence,
      issues: inference?.issues ?? [],
      action,
      needsAttention: confidence !== null && confidence < LOW_CONFIDENCE_BELOW,
    }
  })
}
