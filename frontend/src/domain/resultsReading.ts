// How stage 1 read the file, for the Results page (PROJECT_PLAN 6D; the design
// gap review's Results ADD): the date order applied, the numbers rewritten,
// the walk-in candidates left unconfirmed. Every count is one
// cleaning_report.json carries (CLAUDE.md 3.2); the only arithmetic here is
// how many names a list leaves unshown. Each sentence says only what stage 1
// measured on the uploaded file: the plan's own actions run after it, and
// may cast, fill or drop those cells (6A-6D review B1).

import type { CanonicalField, CleaningReport, NumberFormat } from '../types/contracts.ts'

const MARKS: Record<NumberFormat, string> = { decimal_point: 'a decimal point', decimal_comma: 'a decimal comma' }
const MAX_PLACEHOLDERS = 5
// As the backend clips a name it quotes (6A-6D review M6).
const MAX_NAME = 60

export interface ReadingContext {
  // False for a file the analysis will not read (NOT_INVENTORY).
  analysis: boolean
}

// The browser's own digits, as the summary tiles beside it print them (6A-6D
// review M2).
function count(n: number): string {
  return n.toLocaleString()
}

function quoted(name: string): string {
  return `"${name.length > MAX_NAME ? `${name.slice(0, MAX_NAME - 1)}…` : name}"`
}

function columnOf(report: CleaningReport, field: CanonicalField): string | undefined {
  return Object.keys(report.column_mapping).find((column) => report.column_mapping[column] === field)
}

function dateSentence(report: CleaningReport): string | null {
  if (!report.date_order) {
    return null
  }
  const column = columnOf(report, 'transaction_date')
  // Only the day-month-year cells follow an order; an ISO date reads one way
  // (CONTRACTS section 5; 6A-6D review M4). The example is Review's own.
  const where = column === undefined ? 'Dates' : `Dates in ${quoted(column)}`
  const order = report.date_order === 'day_first' ? 'day first' : 'month first'
  // The order is the user's answer when there is one, else what the raw file
  // proved (CONTRACTS section 5).
  const answered = report.confirmations?.dates_day_first !== null && report.confirmations?.dates_day_first !== undefined
  return `${where} written like 05/01/2026 were read ${order}, ${answered ? 'as you answered in Review' : "as the file's own dates show"}.`
}

function numberSentences(report: CleaningReport): string[] {
  const sentences: string[] = []
  for (const [column, applied] of Object.entries(report.number_formats ?? {})) {
    const parts: string[] = []
    if (applied.rewritten > 0) {
      const one = applied.rewritten === 1
      parts.push(
        `${count(applied.rewritten)} ${one ? 'number' : 'numbers'} in ${quoted(column)} ${one ? 'was' : 'were'} ` +
          `rewritten as ${one ? 'a plain number' : 'plain numbers'}.`,
      )
    }
    // The mark reads the cells that could be read two ways only; a cell that
    // proves its own mark is read by it (number_apply.py; 6A-6D review B2).
    if (applied.format !== null) {
      parts.push(
        `${applied.rewritten > 0 ? 'Those' : `Numbers in ${quoted(column)}`} that could be read two ways were read with ${MARKS[applied.format]}, ` +
          `${applied.answered ? 'as you answered in Review' : "as the file's own numbers show"}.`,
      )
    }
    if (applied.unreadable > 0) {
      const one = applied.unreadable === 1
      parts.push(
        `${count(applied.unreadable)} ${one ? 'cell' : 'cells'} in ${quoted(column)} could not be read as ` +
          `${one ? 'a number' : 'numbers'} in the uploaded file.`,
      )
    }
    if (parts.length > 0) {
      sentences.push(parts.join(' '))
    }
  }
  return sentences
}

function placeholderSentence(report: CleaningReport, context: ReadingContext): string | null {
  const values = report.unconfirmed_placeholders ?? []
  if (values.length === 0) {
    return null
  }
  const one = values.length === 1
  const column = columnOf(report, 'customer')
  const where = column === undefined ? '' : ` in ${quoted(column)}`
  const shown = values.slice(0, MAX_PLACEHOLDERS).map(quoted).join(', ')
  const more = values.length > MAX_PLACEHOLDERS ? ` and ${count(values.length - MAX_PLACEHOLDERS)} more` : ''
  // Measured again at execute on the plan's own mapping, so one may be a
  // value Review never asked about: "not confirmed", never "you did not
  // confirm" (6A-6D review S4).
  const lead = one
    ? `A possible walk-in placeholder${where} that was not confirmed: ${shown}.`
    : `Possible walk-in placeholders${where} that were not confirmed: ${shown}${more}.`
  // The standing no-guess rule (CLAUDE.md 3.3a): unconfirmed, they stay
  // customers; stages 2 and 5 mark them "suggested, not confirmed".
  const outcome = !context.analysis
    ? one
      ? 'It is kept as written.'
      : 'They are kept as written.'
    : one
      ? 'It stays a customer in every figure; the analysis marks it as suggested, not confirmed.'
      : 'They stay customers in every figure; the analysis marks them as suggested, not confirmed.'
  return `${lead} ${outcome}`
}

export function describeReading(report: CleaningReport, context: ReadingContext): string[] {
  return [dateSentence(report), ...numberSentences(report), placeholderSentence(report, context)].filter(
    (sentence): sentence is string => sentence !== null,
  )
}
