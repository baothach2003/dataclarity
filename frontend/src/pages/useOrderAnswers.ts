// The Review screen's answers about orders and customers (sessions 2E-e2 and
// 2E-k), kept apart from the plan so an answer neither re-runs the preview nor
// is lost when the plan is reset to the AI's. Each answer remembers the
// columns it was given for (domain/orderChecks.ts, domain/customerChecks.ts).

import { useState } from 'react'
import { confirmedPlaceholders, customerColumn, customerIdentity, placeholderCandidates } from '../domain/customerChecks.ts'
import type { PlaceholderCandidate, StoredPlaceholders } from '../domain/customerChecks.ts'
import { NO_ANSWERS, answerKey, applicableAnswers, withApplicableConfirmations } from '../domain/orderChecks.ts'
import type { Question, StoredAnswers } from '../domain/orderChecks.ts'
import type { CleaningPlan, OrderConfirmations, ProfileContract, SchemaInferenceContract } from '../types/contracts.ts'

export interface OrderAnswers {
  answers: OrderConfirmations
  placeholders: string[]
  candidates: PlaceholderCandidate[]
  placeholderAnswers: ReadonlyMap<string, boolean>
  answer: (question: Question, value: boolean | null) => void
  answerPlaceholder: (value: string, placeholder: boolean | null) => void
  /** `plan` with the answers that apply to it, as executed. */
  confirmed: (plan: CleaningPlan) => CleaningPlan
}

export function useOrderAnswers(
  plan: CleaningPlan,
  schema: SchemaInferenceContract | null,
  profile: ProfileContract,
): OrderAnswers {
  const [stored, setStored] = useState<StoredAnswers>(NO_ANSWERS)
  const [storedPlaceholders, setStoredPlaceholders] = useState<StoredPlaceholders>({})
  const placeholders = confirmedPlaceholders(plan, profile, schema, storedPlaceholders)
  const column = customerColumn(plan)
  const placeholderAnswers = new Map(
    Object.entries(storedPlaceholders).flatMap(([identity, answer]) =>
      answer !== undefined && answer.column === column ? [[identity, answer.value] as const] : [],
    ),
  )
  return {
    answers: applicableAnswers(plan, schema, profile, stored, placeholders),
    placeholders,
    candidates: placeholderCandidates(plan, profile, schema),
    placeholderAnswers,
    answer: (question, value) => {
      setStored((current) => ({
        ...current,
        [question]: value === null ? null : { value, key: answerKey(plan, question) },
      }))
    },
    answerPlaceholder: (value, placeholder) => {
      const identity = customerIdentity(value)
      setStoredPlaceholders((current) => {
        const next = { ...current }
        if (placeholder === null || column === null) {
          // eslint-disable-next-line @typescript-eslint/no-dynamic-delete -- a keyed answer map
          delete next[identity]
        } else {
          next[identity] = { value: placeholder, column }
        }
        return next
      })
    },
    confirmed: (submitted) =>
      withApplicableConfirmations(
        submitted,
        schema,
        profile,
        stored,
        confirmedPlaceholders(submitted, profile, schema, storedPlaceholders),
      ),
  }
}
