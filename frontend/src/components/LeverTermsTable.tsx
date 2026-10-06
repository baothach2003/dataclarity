// "The split of the change, exact" (design 1.7; report.html's appendix, html_causes.py): every term of stage 3's
// split as report.json lists it - level 1, level 2 and the orders x average order value pair - so an analyst
// sees, as numbers, even the split the front's waterfall withholds (Q17: never drawn). Formatted as report.html
// formats them; the page adds nothing up.

import { useCurrencyCode } from '../domain/currencyCode.ts'
import { count, money, plainNumber } from '../domain/reportFormat.ts'
import type { Factor, LeverLevelView } from '../types/reportFront.ts'

function factorValue(name: Factor, value: number, code: string | null): string {
  if (name === 'aov' || name === 'price_per_unit') {
    return money(value, code)
  }
  return name === 'customers' || name === 'orders' ? count(value) : plainNumber(value)
}

export function LeverTermsTable({ levels }: { levels: LeverLevelView[] }) {
  const code = useCurrencyCode()
  if (levels.length === 0) {
    return null
  }
  return (
    <div className="table-scroll">
      <table className="hypotheses">
        <caption>The split of the change, exact</caption>
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col">Formula</th>
            <th scope="col">Factor</th>
            <th scope="col" className="hypotheses__figure">Before</th>
            <th scope="col" className="hypotheses__figure">After</th>
            <th scope="col" className="hypotheses__figure">Contribution</th>
          </tr>
        </thead>
        <tbody>
          {levels.flatMap((level) =>
            level.factors.map((term) => (
              <tr key={`${level.level}-${term.name}`}>
                <td>{level.level}</td>
                <td>{level.formula}</td>
                <td>{term.name}</td>
                <td className="hypotheses__figure">{factorValue(term.name, term.value_prev, code)}</td>
                <td className="hypotheses__figure">{factorValue(term.name, term.value_cur, code)}</td>
                <td className="hypotheses__figure">{money(term.contribution, code)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  )
}
