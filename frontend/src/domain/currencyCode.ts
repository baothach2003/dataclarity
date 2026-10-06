// The currency the report's amounts are in (report.json `currency`; the report redesign's Q8): its ISO code
// on every amount the Insights page formats, as report.html's appendix prints them - never on a count.
// Null: not stated, amounts without a code ("Amounts are in your file's currency.").

import { createContext, useContext } from 'react'

export const CurrencyCode = createContext<string | null>(null)

export function useCurrencyCode(): string | null {
  return useContext(CurrencyCode)
}
