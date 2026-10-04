// A hypothesis's evidence as it stands, readably - stage 5's html_parts.evidence_value: names as written,
// null as "none", a product whose class was suggested and nobody confirmed marked "(suggested: <class>,
// not confirmed)" wherever the evidence names it (CONTRACTS 6 and 7). Its keys are free-form per
// hypothesis and none is relied on (CONTRACTS 11). Rendered as text, so React escapes it (SEC-3).
//
// One known difference from the report: JSON cannot tell 1500.0 from 1500, so a whole-number float prints
// as an integer - "1,500" where report.html prints "1,500.00", "1" in a list where it prints "1.0".
// Showing report.html's own text would need stage 5 to write it into report.json (a question for Thach).

import { count, number } from './reportFormat.ts'

function marked(value: unknown, marks: Record<string, string>): unknown {
  if (typeof value === 'string' && Object.hasOwn(marks, value)) {
    return `${value} (suggested: ${marks[value] ?? ''}, not confirmed)`
  }
  if (Array.isArray(value)) {
    return value.map((item) => marked(item, marks))
  }
  if (typeof value === 'object' && value !== null) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, marked(item, marks)]))
  }
  return value
}

/** Python's repr of a float: the shortest digits, with ".0" when whole, and an exponent of at least two
 * digits below 1e-4 or from 1e16 up ("1.234e-05", "1.5e+17"). */
function pythonFloat(value: number): string {
  if (value === 0) {
    return '0.0'
  }
  const [mantissa = '', power = '0'] = value.toExponential().split('e')
  const exponent = Number(power)
  if (exponent < -4 || exponent >= 16) {
    return `${mantissa}e${exponent < 0 ? '-' : '+'}${String(Math.abs(exponent)).padStart(2, '0')}`
  }
  const plain = String(value)
  return plain.includes('.') ? plain : `${plain}.0`
}

/** Python's json.dumps(..., ensure_ascii=False) of html_parts._plain: ", " and ": " separators, a
 * fractional figure rounded as `number` prints it and written as Python writes that float (the 6E2
 * review #2: "250.004" is rounded to the float 250.0, printed "250.0"). */
function pythonJson(value: unknown): string {
  if (value === null || value === undefined) {
    return 'null'
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : pythonFloat(Number(number(value).replaceAll(',', '')))
  }
  if (typeof value === 'boolean' || typeof value === 'string') {
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    return `[${value.map(pythonJson).join(', ')}]`
  }
  if (typeof value === 'object') {
    return `{${Object.entries(value).map(([key, item]) => `${JSON.stringify(key)}: ${pythonJson(item)}`).join(', ')}}`
  }
  // JSON holds nothing else (a bigint, a function or a symbol cannot come from a parsed body).
  return 'null'
}

export function evidenceValue(value: unknown, marks: Record<string, string>): string {
  const shown = marked(value, marks)
  if (shown === null || shown === undefined) {
    return 'none'
  }
  if (typeof shown === 'boolean') {
    return shown ? 'yes' : 'no'
  }
  if (typeof shown === 'number') {
    return Number.isInteger(shown) ? count(shown) : number(shown)
  }
  if (typeof shown === 'string') {
    return shown
  }
  return pythonJson(shown)
}
