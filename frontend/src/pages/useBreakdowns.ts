// Review's sales breakdowns (the dashboard, Thach's D4; docs/DASHBOARD_DESIGN.md 5.4). Stage 1 says which columns
// can split sales for the plan as it stands - read on the plan's lines (Thach's Q3-Q5), so asked again whenever a
// step or an answer of the plan changes - and the AI's suggestion (asked once per run, by the server). The user is
// the final authority (CLAUDE.md 3.3): the suggestion is pre-selected, the user removes or adds columns, at most
// two; what is selected goes with the plan. Thach's Q7 (2026-10-16): a column written on each order's first line only
// is offered once the user answers that it applies to the whole order - the answers go with the plan, so stage 1
// is asked again with them.

import { useEffect, useState } from 'react'
import { breakdownQuestion } from '../api/runs.ts'
import type { BreakdownQuestion } from '../types/breakdowns.ts'
import { MAX_BREAKDOWNS } from '../types/breakdowns.ts'
import type { CleaningPlan } from '../types/contracts.ts'

export interface BreakdownState {
  question: BreakdownQuestion | null
  loading: boolean
  // The question shown is the last answer, for an earlier plan: stage 1 is measuring the plan as it stands now.
  stale: boolean
  error: unknown
  // The columns that will split sales: the user's choice, else the suggestion - always eligible ones.
  selected: string[]
  // The user's answers to the Q7 questions, by column.
  wholeOrder: Record<string, boolean>
  answer: (column: string, value: boolean | null) => void
  remove: (column: string) => void
  add: (column: string) => void
  retry: () => void
}

interface Asked {
  key: string
  question: BreakdownQuestion | null
  error: unknown
}

/** What eligibility reads of the plan: all of it but the user's own choice of columns (the server's key too). */
function planKey(plan: CleaningPlan): string {
  return JSON.stringify({ ...plan, breakdowns: undefined, generated_at: undefined })
}

const ASK_AFTER_MS = 400

export function useBreakdowns(baseUrl: string, runId: string, edited: CleaningPlan, enabled: boolean): BreakdownState {
  const [wholeOrder, setWholeOrder] = useState<Record<string, boolean>>({})
  const plan = withWholeOrder(edited, wholeOrder)
  const key = planKey(plan)
  const [asked, setAsked] = useState<Asked | null>(null)
  // The user's own selection, once they changed it; null while they have not.
  const [choice, setChoice] = useState<string[] | null>(null)
  const [attempt, setAttempt] = useState(0)
  // The last answer received, whatever plan it was for.
  const [answered, setAnswered] = useState<Asked | null>(null)
  const [planAtKey, setPlanAtKey] = useState({ key, plan })
  if (planAtKey.key !== key) {
    setPlanAtKey({ key, plan })
  }

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    // 400 ms after the last edit, as the preview (the doubt review's R2: each edit is a whole-file measure on the
    // server, in its one heavy slot).
    const timer = setTimeout(() => {
      breakdownQuestion(baseUrl, runId, planAtKey.plan, controller.signal)
        .then((response) => {
          setAsked({ key: planAtKey.key, question: response.question, error: null })
          setAnswered({ key: planAtKey.key, question: response.question, error: null })
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setAsked({ key: planAtKey.key, question: null, error })
          }
        })
    }, ASK_AFTER_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [baseUrl, runId, planAtKey, enabled, attempt])

  const current = asked !== null && asked.key === key ? asked : null
  // While the plan as it stands is measured, the last answer stays: the columns selected are not dropped unseen
  // (the doubt review's R1) - execute checks them again on the final plan, and refuses one that no longer splits.
  const shown = current ?? answered
  const question = shown?.question ?? null
  const eligible = new Set(question?.eligible.map((c) => c.column) ?? [])
  // A column no longer eligible is never sent: not in the answer, nor - while the answer is the last one, for an
  // earlier plan - dropped or mapped to a field by the plan as it stands (the scoped review's #2).
  const unused = new Set(
    plan.column_actions.filter((c) => c.canonical_field === 'ignore' && c.action !== 'drop_column').map((c) => c.source_name),
  )
  const selected = (choice ?? question?.suggested ?? [])
    .filter((c) => eligible.has(c) && unused.has(c))
    .slice(0, MAX_BREAKDOWNS)
  return {
    question,
    loading: enabled && current === null,
    stale: current === null && answered !== null,
    error: current?.error ?? null,
    selected,
    wholeOrder,
    answer: (column, value) => {
      const next = { ...wholeOrder }
      if (value === null) {
        // eslint-disable-next-line @typescript-eslint/no-dynamic-delete -- a column's answer withdrawn
        delete next[column]
      } else {
        next[column] = value
      }
      setWholeOrder(next)
    },
    remove: (column) => {
      setChoice(selected.filter((c) => c !== column))
    },
    add: (column) => {
      if (eligible.has(column) && !selected.includes(column) && selected.length < MAX_BREAKDOWNS) {
        setChoice([...selected, column])
      }
    },
    retry: () => {
      setAsked(null)
      setAttempt((n) => n + 1)
    },
  }
}

/** `plan` with the answers to the Q7 questions (plan `breakdown_whole_order`), when there are any. */
function withWholeOrder(plan: CleaningPlan, answers: Record<string, boolean>): CleaningPlan {
  return Object.keys(answers).length === 0 ? plan : { ...plan, breakdown_whole_order: answers }
}

/** `plan` with the columns that split sales (plan `breakdowns`) and the Q7 answers, when there are any. */
export function withBreakdowns(plan: CleaningPlan, selected: string[], wholeOrder: Record<string, boolean> = {}): CleaningPlan {
  const answered = withWholeOrder(plan, wholeOrder)
  return selected.length === 0 ? answered : { ...answered, breakdowns: selected }
}
