// Review's currency question (the report redesign's step 5; design 6.2 and 6.3). Stage 1 reads the raw
// file on the plan's money column, so the question is asked again only when that column changes - never on
// every edit (the line summary's lesson: whole-file reads pile up). The answer is the user's alone: it is
// sent only when the user picked one, so an unanswered question runs as stage 1 decides (a found code, else
// "not stated" - never assumed).

import { useEffect, useState } from 'react'
import { currencyQuestion } from '../api/runs.ts'
import type { CleaningPlan } from '../types/contracts.ts'
import type { CurrencyQuestion } from '../types/currency.ts'

export interface CurrencyState {
  question: CurrencyQuestion | null
  // Stage 1 is reading the file: the question is on its way (shown as such, never absent).
  loading: boolean
  error: unknown
  // What the picker shows: the user's answer, else stage 1's pre-selection.
  selected: string | null
  // The user's own answer, or null while unanswered.
  answer: string | null
  // More than one currency: the plan cannot run (Thach, Q7 = A).
  blocked: boolean
  choose: (value: string) => void
  retry: () => void
}

interface Asked {
  key: string
  question: CurrencyQuestion | null
  error: unknown
}

/** The columns the plan maps to the unit price: what the finding depends on. */
function moneyKey(plan: CleaningPlan): string {
  return JSON.stringify(plan.column_actions.filter((c) => c.canonical_field === 'unit_price').map((c) => c.source_name))
}

export function useCurrencyQuestion(baseUrl: string, runId: string, plan: CleaningPlan, enabled: boolean): CurrencyState {
  const key = moneyKey(plan)
  const [asked, setAsked] = useState<Asked | null>(null)
  const [answer, setAnswer] = useState<{ key: string; value: string } | null>(null)
  const [attempt, setAttempt] = useState(0)
  // The plan as it stands when the money column changes; later edits do not ask again.
  const [planAtKey, setPlanAtKey] = useState({ key, plan })
  if (planAtKey.key !== key) {
    setPlanAtKey({ key, plan })
  }

  useEffect(() => {
    if (!enabled) {
      return
    }
    const controller = new AbortController()
    currencyQuestion(baseUrl, runId, planAtKey.plan, controller.signal)
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
  const blocked = question?.finding.kind === 'mixed'
  // An answer about another money column, or to a blocked file, is no answer.
  const own = answer !== null && answer.key === key && !blocked ? answer.value : null
  return {
    question,
    loading: enabled && current === null,
    error: current?.error ?? null,
    selected: own ?? question?.selected ?? null,
    answer: own,
    blocked,
    choose: (value) => {
      setAnswer({ key, value })
    },
    retry: () => {
      // The failed answer goes, so the question reads as on its way again (step 5's scoped review).
      setAsked(null)
      setAttempt((n) => n + 1)
    },
  }
}

/** `plan` with the user's currency answer, when there is one (plan confirmations.currency). */
export function withCurrency(plan: CleaningPlan, answer: string | null): CleaningPlan {
  if (answer === null) {
    return plan
  }
  return {
    ...plan,
    confirmations: {
      order_id_is_receipt: null,
      customer_on_first_line_only: null,
      ...plan.confirmations,
      currency: answer,
    },
  }
}
