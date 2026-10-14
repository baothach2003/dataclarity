// Review's sales breakdowns (the dashboard, Thach's D4; docs/DASHBOARD_DESIGN.md 5.4). Stage 1 says which columns
// can split sales for the plan as it stands - asked again only when a column's field, type or drop changes - and
// the AI's suggestion (asked once per run, by the server). The user is the final authority (CLAUDE.md 3.3): the
// suggestion is pre-selected, the user removes or adds columns, at most two; what is selected goes with the plan.

import { useEffect, useState } from 'react'
import { breakdownQuestion } from '../api/runs.ts'
import type { BreakdownQuestion } from '../types/breakdowns.ts'
import { MAX_BREAKDOWNS } from '../types/breakdowns.ts'
import type { CleaningPlan } from '../types/contracts.ts'

export interface BreakdownState {
  question: BreakdownQuestion | null
  loading: boolean
  error: unknown
  // The columns that will split sales: the user's choice, else the suggestion - always eligible ones.
  selected: string[]
  remove: (column: string) => void
  add: (column: string) => void
  retry: () => void
}

interface Asked {
  key: string
  question: BreakdownQuestion | null
  error: unknown
}

/** What eligibility reads of the plan: each column's field, type and drop (the server's own key). */
function columnsKey(plan: CleaningPlan): string {
  return JSON.stringify(
    plan.column_actions.map((c) => [c.source_name, c.canonical_field, c.semantic_type, c.action === 'drop_column']),
  )
}

export function useBreakdowns(baseUrl: string, runId: string, plan: CleaningPlan, enabled: boolean): BreakdownState {
  const key = columnsKey(plan)
  const [asked, setAsked] = useState<Asked | null>(null)
  // The user's own selection, once they changed it; null while they have not.
  const [choice, setChoice] = useState<string[] | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [planAtKey, setPlanAtKey] = useState({ key, plan })
  if (planAtKey.key !== key) {
    setPlanAtKey({ key, plan })
  }

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    breakdownQuestion(baseUrl, runId, planAtKey.plan, controller.signal)
      .then((response) => {
        setAsked({ key: planAtKey.key, question: response.question, error: null })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setAsked({ key: planAtKey.key, question: null, error })
        }
      })
    return () => {
      controller.abort()
    }
  }, [baseUrl, runId, planAtKey, enabled, attempt])

  const current = asked !== null && asked.key === key ? asked : null
  const question = current?.question ?? null
  const eligible = new Set(question?.eligible.map((c) => c.column) ?? [])
  // A column no longer eligible (mapped or dropped since) is never sent.
  const selected = (choice ?? question?.suggested ?? []).filter((c) => eligible.has(c)).slice(0, MAX_BREAKDOWNS)
  return {
    question,
    loading: enabled && current === null,
    error: current?.error ?? null,
    selected,
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

/** `plan` with the columns that split sales (plan `breakdowns`), when there are any. */
export function withBreakdowns(plan: CleaningPlan, selected: string[]): CleaningPlan {
  return selected.length === 0 ? plan : { ...plan, breakdowns: selected }
}
