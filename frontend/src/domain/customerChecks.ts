// Walk-in placeholders (session 2E-k, Thach): customer values that may stand
// for the customers a shop did not record - "Guest", "Walk-in", "0". Review
// asks about each; a Yes makes those lines unattributed in stages 2 and 3.
// Stage 1 measures the candidates on the raw file for the column it mapped
// (stages/ingest/customer_placeholders.py); after a remap they are read here
// from profile.json's top values - the same word list and the same share of
// lines, revenue not measured - so the question is not lost.

import type { CleaningPlan, ProfileContract, SchemaInferenceContract, TopValue } from '../types/contracts.ts'

// Mirrors stage 1's PLACEHOLDER_SHARE, PLACEHOLDER_RATIO, PLACEHOLDER_WORDS and
// is_placeholder_word (stages/ingest/customer_placeholders.py).
export const PLACEHOLDER_SHARE = 0.1
export const PLACEHOLDER_RATIO = 4
const WORDS = [
  'guest',
  String.raw`walk[\s_-]?in`,
  'cash',
  'anonymous',
  'unknown',
  'none',
  'null',
  'blank',
  'default',
  String.raw`one[\s_-]?time`,
  'retail customer',
  'counter',
  'no customer',
  'misc',
  String.raw`non[\s_-]?member`,
  'unregistered',
  'laufkunde',
  'barverkauf',
  'divers',
  'consumidor final',
  'cliente (?:final|contado)',
  'p[uú]blico en general',
  'pelanggan umum',
  '散客',
  'kh[aá]ch (?:h[aà]ng )?l[eẻ]',
  'kh[aá]ch v[aã]ng lai',
]
// Only a LETTER before or after makes a word part of another ("Walker",
// "Miscellaneous Ltd"), so plurals, codes and underscores still match:
// "Walk-ins", "GUEST01", "Walk_In" (2E-k doubt-review cycle 3 F3).
const PLACEHOLDER_WORDS = new RegExp(String.raw`(?<!\p{L})(?:${WORDS.join('|')})s?(?!\p{L})`, 'u')
const NOT_APPLICABLE = /^n\.?\s?a\.?$/

/** A customer identity that reads as a placeholder: a word above (2E-k
 * doubt-review F6, cycle 2 F1, F4, cycle 3 F3), "customer" alone, "n.a.", no
 * letter or digit at all, or a number at or below zero ("0", "0.0", "-1"). */
function isPlaceholderWord(identity: string): boolean {
  if (!/[\p{L}\p{N}]/u.test(identity)) {
    return true
  }
  if (identity.trim() !== '' && Number(identity) <= 0) {
    return true
  }
  return identity === 'customer' || NOT_APPLICABLE.test(identity) || PLACEHOLDER_WORDS.test(identity)
}

export interface PlaceholderCandidate {
  value: string
  linesPct: number
  revenuePct: number | null
}

/** An answer, and the customer column it was given for: after a remap it no
 * longer applies. Keyed by the value's customer identity. */
export type StoredPlaceholders = Partial<Record<string, { value: boolean; column: string }>>

/** Stage 2's customer identity: stripped and case-folded. */
export function customerIdentity(value: string): string {
  return value.trim().toLowerCase()
}

/** The column mapped to customer, or null; a dropped column is not mapped. */
export function customerColumn(plan: CleaningPlan): string | null {
  return (
    plan.column_actions.find((c) => c.canonical_field === 'customer' && c.action !== 'drop_column')?.source_name ??
    null
  )
}

export function placeholderCandidates(
  plan: CleaningPlan,
  profile: ProfileContract,
  schema: SchemaInferenceContract | null,
): PlaceholderCandidate[] {
  const column = customerColumn(plan)
  if (column === null) {
    return []
  }
  const measured = schema?.columns.find((c) => c.canonical_field === 'customer')?.source_name
  // null: stage 1 could not measure (2E-k doubt-review F4) - the profile decides.
  if (schema !== null && measured === column && schema.customer_placeholders != null) {
    return schema.customer_placeholders.map((c) => ({
      value: c.value,
      linesPct: c.lines_pct,
      revenuePct: c.revenue_pct,
    }))
  }
  const rows = profile.dataset.rows
  const top = profile.columns.find((c) => c.name === column)?.top_values ?? []
  const asked = (t: TopValue): boolean =>
    isPlaceholderWord(customerIdentity(t.value)) || (rows > 0 && t.count / rows >= PLACEHOLDER_SHARE)
  // The largest value at PLACEHOLDER_RATIO times the next one, among the
  // values not already asked about - a first placeholder shielded a second
  // (review cycle 3 F1). The profile's top values come largest first; lines
  // only, revenue is not measured here.
  const rest = top.filter((t) => !asked(t))
  const dominant =
    rest.length >= 2 && rest[1].count > 0 && rest[0].count >= PLACEHOLDER_RATIO * rest[1].count ? rest[0].value : null
  return top
    .filter((t) => asked(t) || t.value === dominant)
    .map((t) => ({ value: t.value, linesPct: rows > 0 ? (100 * t.count) / rows : 0, revenuePct: null }))
}

/** A share in percent for Review's copy, floored to one decimal so a share
 * under a threshold never reads as it (9.96 is "9.9", not "10"), and "<0.1"
 * rather than "0.0" for a tiny one (review cycle 3 F7). The epsilon keeps a
 * binary 28.999999999999996 at 29. */
export function formatShare(pct: number): string {
  if (pct > 0 && pct < 0.1) {
    return '<0.1'
  }
  return String(Math.floor(pct * 10 + 1e-9) / 10)
}

/** The candidates answered Yes for the current customer column, as written:
 * what the plan's `confirmations.customer_placeholders` carries. */
export function confirmedPlaceholders(
  plan: CleaningPlan,
  profile: ProfileContract,
  schema: SchemaInferenceContract | null,
  stored: StoredPlaceholders,
): string[] {
  const column = customerColumn(plan)
  return placeholderCandidates(plan, profile, schema)
    .filter((c) => {
      const answer = stored[customerIdentity(c.value)]
      return answer !== undefined && answer.value && answer.column === column
    })
    .map((c) => c.value)
}
