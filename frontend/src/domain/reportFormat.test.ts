import { describe, expect, it } from 'vitest'
import { change, count, money, ratio, share } from './reportFormat.ts'

// Every expected value is what stage 5's own functions print for the same
// input (stages/report/html_parts.py, run 2026-10-04), so the Insights page and
// the downloadable report print a figure alike - rounding edges included: an
// exact half rounds to even (40.125 -> 40.12), a binary value just above a
// half rounds up (0.0125 -> 0.013), and a value that shows as zero shows no
// sign (CONTRACTS 11).
describe('reportFormat', () => {
  it('prints money with two decimals and grouped thousands, no currency symbol', () => {
    expect(money(96152)).toBe('96,152.00')
    expect(money(40.125)).toBe('40.12')
    expect(money(-0.001)).toBe('0.00')
    expect(money(-1479.6472434497755)).toBe('-1,479.65')
    expect(money(1234567.891)).toBe('1,234,567.89')
  })

  it('prints counts whole', () => {
    expect(count(2380)).toBe('2,380')
    expect(count(-0.4)).toBe('0')
    expect(count(12301)).toBe('12,301')
  })

  it('prints a ratio with three decimals', () => {
    expect(ratio(0.031)).toBe('0.031')
    expect(ratio(-0)).toBe('0.000')
    expect(ratio(0.0125)).toBe('0.013')
  })

  it("prints revenue's change with its sign, and none at zero", () => {
    expect(change(-7.688172043010753)).toBe('-7.7%')
    expect(change(11.905481356137065)).toBe('+11.9%')
    expect(change(0.04)).toBe('0.0%')
    expect(change(-0.04)).toBe('0.0%')
    expect(change(1234.5)).toBe('+1,234.5%')
  })

  it('prints a share as a whole percent', () => {
    expect(share(0.9568098236064152)).toBe('96%')
    expect(share(-0.3004359885177209)).toBe('-30%')
    expect(share(-0)).toBe('0%')
    expect(share(0.125)).toBe('12%')
    expect(share(1.4791770831818256)).toBe('148%')
    expect(share(0.005)).toBe('0%')
  })
})

// The 6E1 review (#1, #2): a finite figure of any size prints as stage 5
// prints it - the double's exact digits, never a zero or a wrong size - and a
// share is never grouped (Python's "%" format has no thousands mark).
describe('reportFormat at the edges', () => {
  it('prints a very large figure whole, as stage 5 does', () => {
    expect(money(1e100)).toBe(
      '10,000,000,000,000,000,159,028,911,097,599,180,468,360,808,563,945,281,389,781,327,557,747,838,772,170,381,060,813,469,985,856,815,104.00',
    )
    expect(money(-1e100)).toBe(
      '-10,000,000,000,000,000,159,028,911,097,599,180,468,360,808,563,945,281,389,781,327,557,747,838,772,170,381,060,813,469,985,856,815,104.00',
    )
    expect(money(9.99e99)).toBe(
      '9,990,000,000,000,000,215,207,280,061,047,724,344,556,843,053,263,384,401,021,344,562,702,137,049,700,770,562,180,880,786,822,004,736.00',
    )
    expect(ratio(1e97)).toBe('10000000000000000735758738477112498397576062152177456799245857901351759143802190202050679656153088.000')
    expect(change(1e22)).toBe('+10,000,000,000,000,000,000,000.0%')
    expect(count(1.5e21)).toBe('1,500,000,000,000,000,000,000')
    expect(money(5e-324)).toBe('0.00')
  })

  it('never groups a share', () => {
    expect(share(10)).toBe('1000%')
    expect(share(25.3)).toBe('2530%')
  })
})

// Step 5's review: an axis tick is an amount too - the code on it when the report has one (report.html's
// tickprefix), never on a count.
describe('axisAmount and signedMoney', () => {
  it('prints a whole tick with the code, and none without one', async () => {
    const { axisAmount, signedMoney } = await import('./reportFormat.ts')

    expect(axisAmount(45000, 'GBP')).toBe('GBP 45,000')
    expect(axisAmount(45000, null)).toBe('45,000')
    expect(signedMoney(-1479.6472, 'GBP')).toBe('GBP -1,479.65')
    expect(signedMoney(4925, null)).toBe('+4,925.00')
    expect(signedMoney(-0.001, null)).toBe('0.00')
  })
})
