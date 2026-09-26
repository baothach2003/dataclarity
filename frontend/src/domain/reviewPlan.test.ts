import { describe, expect, it } from 'vitest'
import type { ProfileContract } from '../types/contracts.ts'
import { buildManualPlan } from './reviewPlan.ts'

// 2E-e doubt-review F1: the hand-built plan (the no-AI path) still said '1.0'
// after plan contracts went to 2.0 with order_id, and the backend refused
// every manual plan - a run without the AI could not be cleaned at all.
describe('buildManualPlan', () => {
  it('writes the plan contract major version the backend reads', () => {
    // Only `columns[].name` is read here; the rest of the profile is irrelevant.
    const profile = { columns: [{ name: 'Invoice' }] } as unknown as ProfileContract

    // 2.1 in 2E-e2, 2.2 in 2E-k (minor bumps); 3.0 since 2E-l: the line-class
    // enum gained "pooled", a major bump - a '2.x' manual plan is refused.
    expect(buildManualPlan(profile, null).schema_version).toBe('3.0')
  })

  it('starts with no answer to either Review question (2E-e2)', () => {
    const profile = { columns: [{ name: 'Invoice' }] } as unknown as ProfileContract

    expect(buildManualPlan(profile, null).confirmations).toEqual({
      order_id_is_receipt: null,
      customer_on_first_line_only: null,
    })
  })
})
