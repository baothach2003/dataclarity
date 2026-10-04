// How the Insights page prints report.json's figures: stage 5's own rules (stages/report/html_parts.py),
// so the page and the downloadable report print every figure alike. Formatting only - rounding for
// display, never a computed figure (CLAUDE.md 3.2). No currency symbol: the file never says which.

import type { KpiUnit } from '../types/report.ts'

// Python's format rounds the double's EXACT value, a tie to even: 40.125 (exact in binary) -> 40.12,
// 0.0125 (0.012500000000000000069... in binary) -> 0.013. Intl rounds the shortest decimal instead
// (0.0125 -> 0.012) and toFixed rounds a tie up (40.125 -> 40.13): neither matches the report, so the
// exact digits are rounded here.

/** The double's exact decimal expansion, any magnitude (the 6E1 review #1: toPrecision switches to an
 * exponent from 1e21 or 1e100 up). A double is mantissa x 2^exponent; a negative exponent is
 * mantissa x 5^-exponent / 10^-exponent. */
function exactDigits(abs: number): { whole: string; fraction: string } {
  const view = new DataView(new ArrayBuffer(8))
  view.setFloat64(0, abs)
  const high = view.getUint32(0)
  const low = view.getUint32(4)
  const biased = (high >>> 20) & 0x7ff
  let mantissa = (BigInt(high & 0xfffff) << 32n) | BigInt(low)
  let exponent = -1074
  if (biased !== 0) {
    mantissa |= 1n << 52n
    exponent = biased - 1075
  }
  if (exponent >= 0) {
    return { whole: (mantissa << BigInt(exponent)).toString(), fraction: '' }
  }
  const places = -exponent
  const digits = (mantissa * 5n ** BigInt(places)).toString().padStart(places + 1, '0')
  return { whole: digits.slice(0, -places), fraction: digits.slice(-places) }
}

function roundedDigits(value: number, decimals: number): { negative: boolean; whole: string; fraction: string } {
  const negative = value < 0 || Object.is(value, -0)
  const { whole, fraction: exactFraction } = exactDigits(Math.abs(value))
  const fraction = exactFraction.padEnd(decimals, '0')
  const kept = (whole + fraction.slice(0, decimals)).split('').map(Number)
  const rest = fraction.slice(decimals)
  const first = rest.charAt(0)
  const beyond = /[1-9]/.test(rest.slice(1))
  const last = kept[kept.length - 1] ?? 0
  const up = first > '5' || (first === '5' && (beyond || last % 2 === 1))
  if (up) {
    let i = kept.length - 1
    while (i >= 0 && kept[i] === 9) {
      kept[i] = 0
      i -= 1
    }
    if (i < 0) {
      kept.unshift(1)
    } else {
      kept[i] = (kept[i] ?? 0) + 1
    }
  }
  const digits = kept.join('')
  const rounded = digits.slice(0, digits.length - decimals).replace(/^0+(?=\d)/, '')
  return { negative, whole: rounded === '' ? '0' : rounded, fraction: digits.slice(digits.length - decimals) }
}

function fixed(value: number, decimals: number, grouping: boolean): string {
  if (!Number.isFinite(value)) {
    // The contract refuses a figure that is not finite; shown as written if one ever came.
    return String(value)
  }
  const { negative, whole, fraction } = roundedDigits(value, decimals)
  const grouped = grouping ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : whole
  return `${negative ? '-' : ''}${grouped}${decimals > 0 ? `.${fraction}` : ''}`
}

// A value that shows as zero shows no sign: -0.0 in a file, or a small negative rounded away
// (CONTRACTS 11; html_parts._signless).
function signless(text: string): string {
  return /^-[0.,]+%?$/.test(text) ? text.slice(1) : text
}

export function money(value: number): string {
  return signless(fixed(value, 2, true))
}

export function count(value: number): string {
  return signless(fixed(value, 0, true))
}

export function ratio(value: number): string {
  return signless(fixed(value, 3, false))
}

/** Revenue's change, the one change report.json carries: "+11.9%", "-7.7%", and "0.0%" unsigned. */
export function change(value: number): string {
  const text = fixed(value, 1, true)
  if (/^-?[0.,]+$/.test(text)) {
    return `${text.replace(/^-/, '')}%`
  }
  return `${value > 0 ? '+' : ''}${text}%`
}

/** A share as a whole percent. Python's "%" format multiplies the double by 100 first (0.005 -> 0.5 ->
 * "0%"), so this does too. */
export function share(value: number): string {
  // Never grouped: Python's "%" format has no thousands mark (the 6E1 review #2).
  return signless(`${fixed(value * 100, 0, false)}%`)
}

export const FORMATS: Record<KpiUnit, (value: number) => string> = { money, count, ratio }

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

/** "2026-05" -> "May 2026"; a value of another shape is shown as written. */
export function monthLabel(period: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(period)
  const name = match ? MONTHS[Number(match[2]) - 1] : undefined
  return match && name ? `${name} ${match[1]}` : period
}
