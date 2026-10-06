// Review's currency question (the report redesign's step 5; contracts/currency.py CurrencyQuestion; design
// 6.2 and 6.3): stage 1's finding on the raw file, the codes in the order Review offers them, the answer
// pre-selected, and stage 1's own sentences - the page words no count.

export interface CurrencyPart {
  label: string
  lines: number
}

export interface CurrencyFinding {
  kind: 'found' | 'narrowed' | 'mixed' | 'none'
  code: string | null
  source: 'column' | 'symbol' | 'header' | null
  candidates: string[]
  evidence: string | null
  parts: CurrencyPart[]
  more_parts: number
  hint: string | null
  unreadable: number
}

// "not_stated", or an ISO 4217 code (plan confirmations.currency).
export const NOT_STATED = 'not_stated'

export interface CurrencyQuestion {
  finding: CurrencyFinding
  options: string[]
  // A found code, else "not_stated"; null when the file is blocked (more than one currency).
  selected: string | null
  blocked: string | null
  unreadable: string | null
  hint: string | null
}

export interface CurrencyResponse {
  run_id: string
  question: CurrencyQuestion
}
