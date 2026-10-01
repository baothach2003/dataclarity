// The Review screen's answers about orders, customers, lines that are not
// products and how the dates are written (sessions 2E-e2, 2E-k, 2E-d2,
// 2E-j, 2E-u1), kept apart from the plan so an answer is not lost when the
// plan is reset to the AI's. The preview reads the plan with them (2E-u1
// review 2, N2), so an answer re-runs it on its sample. Each answer remembers the columns it was given for
// (domain/orderChecks.ts, domain/customerChecks.ts, domain/lineClasses.ts).

import { useState } from 'react'
import {
  confirmedPlaceholders,
  customerColumn,
  customerIdentity,
  placeholderCandidates,
  rejectedPlaceholders,
} from '../domain/customerChecks.ts'
import type { PlaceholderCandidate, StoredPlaceholders } from '../domain/customerChecks.ts'
import { applicableDateAnswer, dateMeasure, dateQuestion } from '../domain/dateOrder.ts'
import type { StoredDateAnswer } from '../domain/dateOrder.ts'
import { answeredLineClasses, candidateColumn, nonProductCandidates } from '../domain/lineClasses.ts'
import { applicableNumberAnswers, numberQuestions } from '../domain/numberFormat.ts'
import type { StoredNumberAnswers } from '../domain/numberFormat.ts'
import type { LineCandidate, StoredLineClasses } from '../domain/lineClasses.ts'
import { NO_ANSWERS, answerKey, applicableAnswers, withApplicableConfirmations } from '../domain/orderChecks.ts'
import type { Question, StoredAnswers } from '../domain/orderChecks.ts'
import type {
  CleaningPlan,
  LineClass,
  NumberFormat,
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
  // 2E-j: the answer to the date question while it applies, and whether it
  // is asked and unanswered (Confirm waits: stage 1 refuses to run).
  dateAnswer: boolean | null
  dateUnanswered: boolean
  answerDate: (dayFirst: boolean | null) => void
  // 2E-u1: the number answers that apply, and whether a column is asked and
  // unanswered (Confirm waits: stage 1 refuses to run).
  numberAnswers: Record<string, NumberFormat>
  numbersUnanswered: boolean
  answerNumber: (column: string, format: NumberFormat | null) => void
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
  const [storedDate, setStoredDate] = useState<StoredDateAnswer | null>(null)
  const [storedNumbers, setStoredNumbers] = useState<StoredNumberAnswers>({})
  const numberAnswers = applicableNumberAnswers(plan, profile, storedNumbers)
  const dateAnswer = applicableDateAnswer(plan, profile, storedDate)
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
    dateAnswer,
    dateUnanswered: dateQuestion(plan, profile) !== null && dateAnswer === null,
    numberAnswers,
    numbersUnanswered: numberQuestions(plan, profile).some(({ column }) => !(column in numberAnswers)),
    answerNumber: (column, format) => {
      setStoredNumbers((current) => {
        const next = { ...current }
        if (format === null) {
          // eslint-disable-next-line @typescript-eslint/no-dynamic-delete -- a keyed answer map
          delete next[column]
        } else {
          next[column] = format
        }
        return next
      })
    },
    answerDate: (dayFirst) => {
      // Asked, or a proof overridden (2E-o Q8): either way about the column measured.
      const found = dateMeasure(plan, profile)
      setStoredDate(dayFirst === null || found === null ? null : { value: dayFirst, column: found.column })
    },
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
      // The classes go only when there are some (2E-d2), as placeholders do,
      // and the date answer only when it applies (2E-j).
      const lineClasses = answeredLineClasses(submitted, profile, schema, storedLines)
      const dayFirst = applicableDateAnswer(submitted, profile, storedDate)
      // The number answers only for the columns asked (2E-u1).
      const numbers = applicableNumberAnswers(submitted, profile, storedNumbers)
      const hasNumbers = Object.keys(numbers).length > 0
      // A No about a walk-in candidate, so stage 1 can tell it from no answer (2E-u3).
      const realCustomers = rejectedPlaceholders(submitted, profile, schema, storedPlaceholders)
      if (lineClasses.length === 0 && dayFirst === null && !hasNumbers && realCustomers.length === 0) {
        return withAnswers
      }
      const confirmations: OrderConfirmations = {
        order_id_is_receipt: null,
        customer_on_first_line_only: null,
        ...withAnswers.confirmations,
        ...(lineClasses.length > 0 ? { line_classes: lineClasses } : {}),
        ...(dayFirst !== null ? { dates_day_first: dayFirst } : {}),
        ...(hasNumbers ? { number_formats: numbers } : {}),
        ...(realCustomers.length > 0 ? { customer_not_placeholders: realCustomers } : {}),
      }
      return { ...withAnswers, confirmations }
    },
  }
}
