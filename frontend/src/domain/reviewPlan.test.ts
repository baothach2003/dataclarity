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

    expect(buildManualPlan(profile, null).schema_version).toBe('2.0')
  })
})
