// The Review screen's answers about orders, customers and lines that are not
// products (sessions 2E-e2, 2E-k, 2E-d2), kept apart from the plan so an
// answer neither re-runs the preview nor is lost when the plan is reset to the
// AI's. Each answer remembers the columns it was given for
// (domain/orderChecks.ts, domain/customerChecks.ts, domain/lineClasses.ts).

import { useState } from 'react'
import { confirmedPlaceholders, customerColumn, customerIdentity, placeholderCandidates } from '../domain/customerChecks.ts'
import type { PlaceholderCandidate, StoredPlaceholders } from '../domain/customerChecks.ts'
import { answeredLineClasses, candidateColumn, nonProductCandidates } from '../domain/lineClasses.ts'
import type { LineCandidate, StoredLineClasses } from '../domain/lineClasses.ts'
import { NO_ANSWERS, answerKey, applicableAnswers, withApplicableConfirmations } from '../domain/orderChecks.ts'
import type { Question, StoredAnswers } from '../domain/orderChecks.ts'
import type {
  CleaningPlan,
  LineClass,
  OrderConfirmations,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'

export interface OrderAnswers {
  answers: OrderConfirmations
  placeholders: string[]
  candidates: PlaceholderCandidate[]
  placeholderAnswers: ReadonlyMap<string, boolean>
  lineCandidates: LineCandidate[]
  lineAnswers: ReadonlyMap<string, LineClass | 'product'>
  answer: (question: Question, value: boolean | null) => void
  answerPlaceholder: (value: string, placeholder: boolean | null) => void
  answerLine: (candidate: LineCandidate, choice: LineClass | 'product' | null) => void
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
  const [storedLines, setStoredLines] = useState<StoredLineClasses>({})
  const placeholders = confirmedPlaceholders(plan, profile, schema, storedPlaceholders)
  const column = customerColumn(plan)
  const placeholderAnswers = new Map(
    Object.entries(storedPlaceholders).flatMap(([identity, answer]) =>
      answer !== undefined && answer.column === column ? [[identity, answer.value] as const] : [],
    ),
  )
  const lineCandidates = nonProductCandidates(plan, profile, schema)
  const lineAnswers = new Map(
    lineCandidates.flatMap((candidate) => {
      const answer = storedLines[candidate.key]
      return answer !== undefined && answer.column === candidateColumn(plan, candidate)
        ? [[candidate.key, answer.value] as const]
        : []
    }),
  )
  return {
    answers: applicableAnswers(plan, schema, profile, stored, placeholders),
    placeholders,
    candidates: placeholderCandidates(plan, profile, schema),
    placeholderAnswers,
    lineCandidates,
    lineAnswers,
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
    answerLine: (candidate, choice) => {
      const lineColumn = candidateColumn(plan, candidate)
      setStoredLines((current) => {
        const next = { ...current }
        if (choice === null || lineColumn === null) {
          // eslint-disable-next-line @typescript-eslint/no-dynamic-delete -- a keyed answer map
          delete next[candidate.key]
        } else {
          next[candidate.key] = { value: choice, column: lineColumn }
        }
        return next
      })
    },
    confirmed: (submitted) => {
      const withAnswers = withApplicableConfirmations(
        submitted,
        schema,
        profile,
        stored,
        confirmedPlaceholders(submitted, profile, schema, storedPlaceholders),
      )
      // The classes go only when there are some (2E-d2), as placeholders do.
      const lineClasses = answeredLineClasses(submitted, profile, schema, storedLines)
      if (lineClasses.length === 0) {
        return withAnswers
      }
      const confirmations: OrderConfirmations = {
        order_id_is_receipt: null,
        customer_on_first_line_only: null,
        ...withAnswers.confirmations,
        line_classes: lineClasses,
      }
      return { ...withAnswers, confirmations }
    },
  }
}
