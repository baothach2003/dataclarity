// The lines no figure counts and where the money of the classes you gave went (the design gap review's
// ADD 9; CONTRACTS 6: never dropped silently), told as stage 5 tells them (html_report._other_lines): a
// previous month's rows only when that month is compared; a withheld month's 0 said to be withheld, a
// real amount standing. The lines dated after the upload are counted here too; why is said beside the
// dates covered, at the top (the 6E3 review #5).

import { count, money, monthLabel } from '../domain/reportFormat.ts'
import { NOT_COMPARED_ABOVE, scopeLabel } from '../domain/reportText.ts'
import type { Numbers } from '../types/report.ts'

// `prose`: the columns holding a sentence - each keeps a readable measure at phone width (the table
// scrolls sideways) instead of a column one word wide.
function Table({ caption, headers, rows, prose }: { caption: string; headers: string[]; rows: string[][]; prose: number[] }) {
  return (
    <div className="table-scroll">
      <table className="hypotheses">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {headers.map((header) => (
              <th scope="col" key={header}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            // Rows may read alike (one class in two scopes); their place is their identity.
            <tr key={index}>
              {row.map((cell, column) => (
                <td key={column} className={prose.includes(column) ? 'cell-prose' : undefined}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function LinesInNoFigureCard({ numbers }: { numbers: Numbers }) {
  const { period } = numbers
  const compared = period.previous_complete
  const shownScope = (scope: Numbers['unmeasurable'][number]['scope']) => scope !== 'previous' || compared
  const future = numbers.future_lines ?? 0
  const withheld = numbers.kpis[0]?.current === null
  const unmeasurable = numbers.unmeasurable.filter((row) => shownScope(row.scope))
  const outside = numbers.outside_revenue.filter((row) => shownScope(row.scope))
  if (!numbers.undated_lines_reason && future === 0 && unmeasurable.length === 0 && numbers.non_product.length === 0 && outside.length === 0) {
    return null
  }
  return (
    <section className="card insights-card">
      <h2 className="insights-card__title">Lines in no figure, and where their money went</h2>
      {numbers.undated_lines_reason && <p>{numbers.undated_lines_reason}</p>}
      {future > 0 && (
        <p>{`${count(future)} ${future === 1 ? 'line is' : 'lines are'} dated after the upload, so no figure counts ${future === 1 ? 'it' : 'them'}; why is said beside the dates the file covers, at the top.`}</p>
      )}
      {unmeasurable.length > 0 && (
        <Table
          caption="Lines that cannot be measured"
          headers={['Scope', 'Why', 'Lines']}
          prose={[1]}
          rows={unmeasurable.map((row) => [scopeLabel(row.scope, period), row.reason, count(row.lines)])}
        />
      )}
      {numbers.non_product.length > 0 && (
        <Table
          caption="Lines of the classes you gave"
          headers={['Class', 'Lines', 'Amount', monthLabel(numbers.period.current), monthLabel(numbers.period.previous), 'Where it went']}
          prose={[5]}
          rows={numbers.non_product.map((row) => [
            row.line_class,
            count(row.lines),
            money(row.amount),
            // Only a withheld month's 0; a real amount stands (5B review 2 #8).
            withheld && row.amount_current === 0 ? "withheld, with the current month's figures" : money(row.amount_current),
            compared ? money(row.amount_previous) : NOT_COMPARED_ABOVE,
            row.reason,
          ])}
        />
      )}
      {outside.length > 0 && (
        <Table
          caption="Lines outside revenue"
          headers={['Class', 'Scope', 'Sign', 'Lines', 'Amount', 'Lines without an amount', 'Why']}
          prose={[6]}
          rows={outside.map((row) => [
            row.line_class,
            scopeLabel(row.scope, period),
            row.sign ?? '',
            count(row.lines),
            money(row.amount),
            count(row.lines_without_amount),
            // Worded by its class code (Thach, 2026-10-04, (ix)).
            row.reason,
          ])}
        />
      )}
    </section>
  )
}
