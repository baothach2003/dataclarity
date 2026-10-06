// Section 1's chart, "Sales by month (before any costs)" (the report redesign's step 5; design D7; report.html's
// html_svg.sales_chart): report.json's revenue_trend as stage 5 draws it - a month not drawn is a gap, never a
// zero and never joined across (CONTRACTS 11) - under the front block's own title, with its part-month
// sentences. The months table stays in "Technical details".

import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from 'recharts'
import { revenueRows } from '../domain/chartData.ts'
import { useCurrencyCode } from '../domain/currencyCode.ts'
import { axisAmount, money } from '../domain/reportFormat.ts'
import type { Chart } from '../types/report.ts'

interface FrontSalesChartProps {
  chart: Chart | undefined
  title: string
  notes: string[]
}

export function FrontSalesChart({ chart, title, notes }: FrontSalesChartProps) {
  const code = useCurrencyCode()
  const rows = chart ? revenueRows(chart) : []
  if (rows.length === 0) {
    return null
  }
  return (
    <>
      <h3 className="front__chart-title">{title}</h3>
      <div className="chart-frame" role="img" aria-label={`${title}, drawn as a line: the technical details give every month's figure`}>
        <LineChart
          responsive
          accessibilityLayer={false}
          data={rows}
          style={{ width: '100%', height: 240 }}
          margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
        >
          <CartesianGrid stroke="var(--divider)" vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 11 }} minTickGap={16} />
          <YAxis
            tickFormatter={(value: number) => axisAmount(value, code)}
            allowDecimals={false}
            tick={{ fontSize: 11 }}
            width={88}
          />
          <Tooltip formatter={(value) => (typeof value === 'number' ? money(value, code) : String(value))} />
          <Line type="linear" dataKey="revenue" name="Sales" stroke="var(--accent)" strokeWidth={2} connectNulls={false} isAnimationActive={false} />
        </LineChart>
      </div>
      {notes.map((line) => (
        <p className="front__small" key={line}>
          {line}
        </p>
      ))}
    </>
  )
}
