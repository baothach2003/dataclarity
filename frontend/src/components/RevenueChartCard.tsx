// Revenue by month (the design gap review's ADD 8; report.json's charts.revenue_trend): the months drawn
// whole only when complete, a gap drawn as a gap with its reason - never a zero, never joined across
// (CONTRACTS 9 and 11). Told as stage 5 tells it (html_report._chart): the gap's note, each trust caution
// once, the notes naming revenue; with no month to draw, the sentence alone. The figures also stand in a
// table - which a screen reader can read and the chart cannot give, and which stays when the report draws
// no chart (as report.html keeps its month table).

import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts'
import { cautionsToSay, revenueRows } from '../domain/chartData.ts'
import { useCurrencyCode } from '../domain/currencyCode.ts'
import { axisAmount, money, monthLabel } from '../domain/reportFormat.ts'
import { NOT_COMPARED_ABOVE } from '../domain/reportText.ts'
import type { Chart, NoteView, Numbers } from '../types/report.ts'
import { NotesBeside } from './NotesBeside.tsx'

interface RevenueChartCardProps {
  // charts.revenue_trend; absent when the report draws none.
  chart: Chart | undefined
  numbers: Numbers
  // The notes the report shows beside figures; the chart names its own by code.
  notes: NoteView[]
}

export function RevenueChartCard({ chart, numbers, notes }: RevenueChartCardProps) {
  const code = useCurrencyCode()
  const rows = chart ? revenueRows(chart) : []
  const { period } = numbers
  const title = chart?.title ?? 'Revenue by month'

  return (
    <section className="card insights-card">
      <h2 className="insights-card__title">{title}</h2>
      {rows.length > 0 && (
        <div className="chart-frame" role="img" aria-label={`${title}, drawn as a line: the table below gives every figure`}>
          {/* No accessibility layer: the frame is one image, and the table carries the figures (the 6E3
              review #1: a focusable application nested in an image named nothing). */}
          <LineChart
            responsive
            accessibilityLayer={false}
            data={rows}
            style={{ width: '100%', height: 260 }}
            margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
          >
            <CartesianGrid stroke="var(--divider)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(value: number) => axisAmount(value, code)} allowDecimals={false} tick={{ fontSize: 12 }} width={88} />
            <Tooltip formatter={(value) => (typeof value === 'number' ? money(value, code) : String(value))} />
            {/* A null month is a gap: never joined across (CONTRACTS 11). */}
            <Line type="linear" dataKey="revenue" stroke="var(--accent)" strokeWidth={2} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </div>
      )}
      {chart?.note && <p className="insights-reason">{chart.note}</p>}
      {chart &&
        cautionsToSay(chart).map((caution) => (
          <p className="insights-caution" key={caution}>{`Caution: ${caution}`}</p>
        ))}
      {chart && <NotesBeside codes={chart.notes} notes={notes} period={period} />}
      {numbers.revenue_by_month.length > 0 && (
        <details className="chart-table" open={rows.length === 0}>
          <summary>The figures as a table</summary>
          <div className="table-scroll">
            <table className="hypotheses">
              <caption>Revenue by month</caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col" className="hypotheses__figure">
                    Revenue
                  </th>
                  <th scope="col">Whole month</th>
                </tr>
              </thead>
              <tbody>
                {numbers.revenue_by_month.map((month) => (
                  <tr key={month.period}>
                    <th scope="row">{monthLabel(month.period)}</th>
                    <td className="hypotheses__figure">
                      {month.revenue === null
                        ? (month.revenue_reason ?? '')
                        : month.period === period.previous && !period.previous_complete
                          ? // Never a previous value beside a current one: its reason is said once, above.
                            NOT_COMPARED_ABOVE
                          : money(month.revenue, code)}
                    </td>
                    <td>{month.complete ? 'yes' : 'no'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  )
}
