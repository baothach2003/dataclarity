// Review's sales breakdowns (the dashboard, Thach's D4; contracts/breakdowns.py BreakdownQuestion): the columns
// stage 1 found able to split sales for the plan as it stands, the AI's suggestion among them, and stage 1's
// own line saying where it came from - the page words none of it.

export interface EligibleColumn {
  column: string
  values: string[]
}

export interface BreakdownQuestion {
  eligible: EligibleColumn[]
  suggested: string[]
  status: 'chosen' | 'none_eligible' | 'ai_unavailable'
  message: string
}

export interface BreakdownResponse {
  run_id: string
  question: BreakdownQuestion
}

// At most this many columns split sales (contracts/metrics.py MAX_BREAKDOWNS).
export const MAX_BREAKDOWNS = 2
