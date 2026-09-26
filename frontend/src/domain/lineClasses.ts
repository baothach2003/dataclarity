// Lines that may not be products (session 2E-d2, Thach): postage, fees,
// discounts and accounting adjustments booked as product lines. Stage 1
// measures the candidates on the raw file for the product columns it mapped
// (stages/ingest/non_product_lines.py); after a remap they are read here from
// profile.json's top values - the same words and the same first-or-last-word
// rule, money not measured - so the question is not lost. The user classes
// each; unanswered, or "a product", its lines stay products.

import type {
  CleaningPlan,
  LineClass,
  LineClassAnswer,
  ProfileContract,
  SchemaInferenceContract,
} from '../types/contracts.ts'

type ProductField = 'sku' | 'product_name'

// Mirrors stage 1's CLASS_WORDS, in its order: the first class whose word
// begins or ends the text wins. null: asked with no suggestion ("SAMPLES").
const CLASS_WORDS: [LineClass | null, string[]][] = [
  ['adjustment', ['adjust', 'adjustment', 'bad debt', 'manual', String.raw`write[\s-]?off`, 'written off', 'điều chỉnh', 'dieu chinh']],
  ['discount', ['discount', 'coupon', 'giảm giá', 'giam gia', 'chiết khấu', 'chiet khau']],
  ['charge', ['postage', 'shipping', 'delivery', 'carriage', 'freight', String.raw`p\s?&\s?p`, 'phí vận chuyển', 'phi van chuyen', 'phí ship', 'phi ship']],
  // Not "hoa hồng": commission, but also roses (2E-d2 doubt-review F7).
  ['cost', ['fee', 'bank charge', 'commission']],
  [null, ['sample']],
]
// Only a letter makes a word part of another ("COFFEE", "ADJUSTABLE").
const AT_AN_END = CLASS_WORDS.map(([lineClass, words]) => ({
  lineClass,
  first: new RegExp(String.raw`^(?:${words.join('|')})s?(?!\p{L})`, 'u'),
  last: new RegExp(String.raw`(?<!\p{L})(?:${words.join('|')})s?$`, 'u'),
}))
// shared/text.py's invisible characters, as code-point ranges: no reader
// sees them in a name. Numbers, not a regex class: a class of them is
// unreadable in source and some are combining marks.
const INVISIBLE: [number, number][] = [
  [0xad, 0xad], [0x34f, 0x34f], [0x61c, 0x61c], [0x115f, 0x1160], [0x17b4, 0x17b5], [0x180b, 0x180f],
  [0x200b, 0x200b], [0x200e, 0x200f], [0x202a, 0x202e], [0x2060, 0x206f], [0x2800, 0x2800],
  [0x3164, 0x3164], [0xfe00, 0xfe0f], [0xfeff, 0xfeff], [0xffa0, 0xffa0], [0xfff9, 0xfffb],
  [0x1d173, 0x1d17a], [0xe0000, 0xe007f],
]

export interface LineCandidate {
  // `${field}:${identity}`: how an answer is stored.
  key: string
  value: string
  field: ProductField
  name: string | null
  lines: number
  // null after a remap: the profile holds no money.
  positive: number | null
  negative: number | null
  suggested: LineClass | null
}

/** An answer, and the product column it was given for: after a remap it no
 * longer applies. Keyed by the candidate's key. */
export type StoredLineClasses = Partial<Record<string, { value: LineClass | 'product'; column: string }>>

/** A product value as stage 1 keys it: composed, invisible characters
 * removed, whitespace runs as one, trimmed, case folded. */
export function productIdentity(value: string): string {
  const visible = Array.from(value.normalize('NFC')).filter((character) => {
    const point = character.codePointAt(0) ?? 0
    return !INVISIBLE.some(([low, high]) => point >= low && point <= high)
  })
  return visible.join('').replace(/\s+/gu, ' ').trim().toLowerCase()
}

function classWord(identity: string): { lineClass: LineClass | null } | null {
  const found = AT_AN_END.find(({ first, last }) => first.test(identity) || last.test(identity))
  return found === undefined ? null : { lineClass: found.lineClass }
}

function mappedColumn(plan: CleaningPlan, field: ProductField): string | null {
  return (
    plan.column_actions.find((c) => c.canonical_field === field && c.action !== 'drop_column')?.source_name ?? null
  )
}

/** The product column an answer is tied to: the SKU when it is mapped, else the name. */
function productColumn(plan: CleaningPlan): { column: string; field: ProductField } | null {
  const sku = mappedColumn(plan, 'sku')
  if (sku !== null) {
    return { column: sku, field: 'sku' }
  }
  const name = mappedColumn(plan, 'product_name')
  return name === null ? null : { column: name, field: 'product_name' }
}

export function nonProductCandidates(
  plan: CleaningPlan,
  profile: ProfileContract,
  schema: SchemaInferenceContract | null,
): LineCandidate[] {
  const product = productColumn(plan)
  if (product === null) {
    return []
  }
  const measured = (field: ProductField) =>
    schema?.columns.find((c) => c.canonical_field === field)?.source_name ?? null
  const sameSku = measured('sku') === mappedColumn(plan, 'sku')
  const sameBoth = sameSku && measured('product_name') === mappedColumn(plan, 'product_name')
  // A SKU candidate stands while the SKU column does, whatever the name column
  // (review F4); a name candidate - lines without a SKU - needs both. null:
  // stage 1 could not measure - the profile decides.
  if (
    schema !== null &&
    schema.non_product_candidates != null &&
    sameSku &&
    (sameBoth || product.field === 'sku')
  ) {
    return schema.non_product_candidates.filter((c) => sameBoth || c.field === 'sku').map((c) => ({
      key: `${c.field}:${productIdentity(c.value)}`,
      value: c.value,
      field: c.field,
      name: c.name,
      lines: c.lines,
      positive: c.positive,
      negative: c.negative,
      suggested: c.suggested,
    }))
  }
  const top = profile.columns.find((c) => c.name === product.column)?.top_values ?? []
  // Values that read the same are one key: asked once, their lines together
  // (review F12: "POSTAGE" and "Postage " were two questions, one answer).
  const byKey = new Map<string, LineCandidate>()
  for (const t of top) {
    const identity = productIdentity(t.value)
    const found = classWord(identity)
    const key = `${product.field}:${identity}`
    const seen = byKey.get(key)
    if (found === null) {
      continue
    }
    if (seen === undefined) {
      byKey.set(key, {
        key,
        value: t.value,
        field: product.field,
        name: null,
        lines: t.count,
        positive: null,
        negative: null,
        suggested: found.lineClass,
      })
    } else {
      seen.lines += t.count
    }
  }
  return [...byKey.values()]
}

/** The classes answered for the current product columns, as the plan's
 * `confirmations.line_classes` carries them: "a product" is no answer. */
export function answeredLineClasses(
  plan: CleaningPlan,
  profile: ProfileContract,
  schema: SchemaInferenceContract | null,
  stored: StoredLineClasses,
): LineClassAnswer[] {
  return nonProductCandidates(plan, profile, schema).flatMap((c) => {
    const answer = stored[c.key]
    return answer === undefined || answer.value === 'product' || answer.column !== mappedColumn(plan, c.field)
      ? []
      : [{ value: c.value, field: c.field, line_class: answer.value }]
  })
}

/** The column a candidate's answer is tied to. */
export function candidateColumn(plan: CleaningPlan, candidate: LineCandidate): string | null {
  return mappedColumn(plan, candidate.field)
}
