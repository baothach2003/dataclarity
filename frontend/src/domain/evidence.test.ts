import { describe, expect, it } from 'vitest'
import { evidenceValue } from './evidence.ts'

// A hypothesis's evidence, shown key by key as it stands (CONTRACTS 11), worded
// as stage 5's html_parts.evidence_value words it - the expected values are its
// own output (2026-10-04). A product whose class was suggested and nobody
// confirmed carries its mark wherever the evidence names it (CONTRACTS 6, 7).
// One known difference: JSON cannot tell 1500.0 from 1500, so a whole-number
// float prints as an integer - "1,500" for "1,500.00", and "1" for "1.0" in a
// list or record.
describe('evidenceValue', () => {
  const marks = { Mug: 'charge' }

  it('words plain values', () => {
    expect(evidenceValue(null, marks)).toBe('none')
    expect(evidenceValue(true, marks)).toBe('yes')
    expect(evidenceValue(false, marks)).toBe('no')
    expect(evidenceValue(1234, marks)).toBe('1,234')
    expect(evidenceValue(19, marks)).toBe('19')
    expect(evidenceValue(0.958, marks)).toBe('0.958')
    expect(evidenceValue('Plate', marks)).toBe('Plate')
  })

  it('marks a product whose class nobody confirmed', () => {
    expect(evidenceValue('Mug', marks)).toBe('Mug (suggested: charge, not confirmed)')
  })

  it('writes lists and records as JSON, its figures rounded and its products marked', () => {
    expect(evidenceValue(['a', 1.23456, 2], marks)).toBe('["a", 1.235, 2]')
    expect(evidenceValue({ top_member: 'Mug', share: 0.30043 }, marks)).toBe(
      '{"top_member": "Mug (suggested: charge, not confirmed)", "share": 0.3004}',
    )
    expect(evidenceValue({ n: null, ok: true }, marks)).toBe('{"n": null, "ok": true}')
  })

  // The 6E2 review (#2): a fractional figure in a list or record is printed as
  // Python prints the float stage 5 rounds it to - "250.0", "1.234e-05".
  it("prints a list's fractional figures as Python prints floats", () => {
    expect(evidenceValue([250.004, 1.2345e-5, 2.5e-7, 0.5, 123.004, -0.0001], marks)).toBe('[250.0, 1.234e-05, 2.5e-07, 0.5, 123.0, -0.0001]')
    expect(evidenceValue({ rate: 0.99996, big: 12345678.9 }, marks)).toBe('{"rate": 1.0, "big": 12345678.9}')
  })
})
