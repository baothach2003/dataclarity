// The revenue forecast (report.json's layer_3_actions.forecast and charts.forecast) with the design gap
// decisions: MONTHLY points, 3 months ahead, with their 80% band - never "weekly" - its method, its
// season_years and its notes; too short a history counted in complete MONTHS (frame 4:1814's CHANGE).
// Told as stage 5 tells it (html_report._actions): the method and the months learned from, the
// forecast's own notes once, a month the file already holds never compared with the point, the chart
// drawn from its own series, the cautions and the notes naming revenue.

import { Area, CartesianGrid, ComposedChart, Legend, Line, Tooltip, XAxis, YAxis } from 'recharts'
import { cautionsToSay, forecastRows } from '../domain/chartData.ts'
import { useCurrencyCode } from '../domain/currencyCode.ts'
import { MIN_HISTORY_MONTHS } from '../domain/forecastRules.ts'
import { axisAmount, count, money, monthLabel, share } from '../domain/reportFormat.ts'
import type { Chart, ForecastView, NoteView, ReportPeriod } from '../types/report.ts'
import { Notice } from './Notice.tsx'
import { NotesBeside } from './NotesBeside.tsx'

interface ForecastCardProps {
  forecast: ForecastView
  // charts.forecast: absent when there is no forecast.
  chart: Chart | undefined
  // The notes the report shows beside figures; the forecast names its own by code.
  notes: NoteView[]
  // The months the notes' measures are scoped to.
  period: ReportPeriod
}

function months(n: number): string {
  return `${count(n)} complete ${n === 1 ? 'month' : 'months'}`
}

function tooltipValue(value: unknown, code: string | null): string {
  if (typeof value === 'number') {
    return money(value, code)
  }
  return Array.isArray(value) ? value.map((v) => money(Number(v), code)).join(' to ') : String(value)
}

export function ForecastCard({ forecast, chart, notes, period }: ForecastCardProps) {
  const code = useCurrencyCode()
  const title = chart?.title ?? 'Revenue forecast'
  // A blank note is no note (contracts/forecast.py) - the 6E3 review #13.
  const ownNotes = [forecast.history_note, forecast.season_note].filter((note): note is string => Boolean(note?.trim()))
  const first = forecast.points.at(0)

  if (forecast.insufficient_history || first === undefined) {
    return (
      <section className="card insights-card">
        <h2 className="insights-card__title">{title}</h2>
        <Notice tone="info" title="Not enough history to forecast yet">
          <span className="notice__line">{`There is too little history for a forecast: ${months(forecast.months_used)}, and ${String(MIN_HISTORY_MONTHS)} are needed.`}</span>
          {ownNotes.map((note, index) => (
            <span className="notice__line" key={index}>
              {note}
            </span>
          ))}
        </Notice>
      </section>
    )
  }

  const rows = chart ? forecastRows(chart) : []
  const band = `${share(first.confidence)} band`

  return (
    <section className="card insights-card">
      <h2 className="insights-card__title">{title}</h2>
      <p>{`Method: ${forecast.method}. Learned from ${months(forecast.months_used)}.`}</p>
      {forecast.season_years !== null && (
        // What a reader decides on, never the note's sentence (CONTRACTS 9; the 6E3 review #2).
        <p>{`The season is read from ${count(forecast.season_years)} ${forecast.season_years === 1 ? 'year' : 'years'} of history.`}</p>
      )}
      {ownNotes.map((note, index) => (
        <p className="insights-reason" key={index}>
          {note}
        </p>
      ))}
      {forecast.partial_first_month_until !== null ? (
        // "The dates the file covers": a line dated after the upload is in no figure, so "the file ends"
        // could be false (the 6E3 review #10).
        <p className="insights-reason">{`The dates the file covers end on ${forecast.partial_first_month_until}, part-way through ${monthLabel(first.period)}: that month's revenue so far is not compared with the forecast.`}</p>
      ) : (
        forecast.first_month_in_file && (
          <p className="insights-reason">{`The file already holds a line for ${monthLabel(first.period)}: its revenue so far is not compared with the forecast.`}</p>
        )
      )}
      {rows.length > 0 && (
        <div className="chart-frame" role="img" aria-label={`${title}, drawn with its ${band}: the table gives every figure`}>
          {/* No accessibility layer: the frame is one image and the table carries the figures (6E3 review #1). */}
          <ComposedChart
            responsive
            accessibilityLayer={false}
            data={rows}
            style={{ width: '100%', height: 240 }}
            margin={{ top: 8, right: 16, bottom: 0, left: 8 }}
          >
            <CartesianGrid stroke="var(--divider)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(value: number) => axisAmount(value, code)} allowDecimals={false} tick={{ fontSize: 12 }} width={88} />
            <Tooltip formatter={(value) => tooltipValue(value, code)} />
            <Legend />
            {/* The band, low to high, as one range area. */}
            <Area dataKey="band" name={band} stroke="none" fill="var(--accent)" fillOpacity={0.15} isAnimationActive={false} />
            <Line type="linear" dataKey="point" name="Forecast" stroke="var(--accent)" strokeWidth={2} strokeDasharray="6 4" isAnimationActive={false} />
          </ComposedChart>
        </div>
      )}
      {chart &&
        cautionsToSay(chart).map((caution) => (
          <p className="insights-caution" key={caution}>{`Caution: ${caution}`}</p>
        ))}
      <div className="table-scroll">
        <table className="hypotheses">
          <caption>{`Low and high: the ${band}, from the method's own past errors`}</caption>
          <thead>
            <tr>
              <th scope="col">Month</th>
              <th scope="col" className="hypotheses__figure">
                Forecast
              </th>
              <th scope="col" className="hypotheses__figure">
                Low
              </th>
              <th scope="col" className="hypotheses__figure">
                High
              </th>
            </tr>
          </thead>
          <tbody>
            {forecast.points.map((point) => (
              <tr key={point.period}>
                <th scope="row">{monthLabel(point.period)}</th>
                <td className="hypotheses__figure">{money(point.point, code)}</td>
                <td className="hypotheses__figure">{money(point.low, code)}</td>
                <td className="hypotheses__figure">{money(point.high, code)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* The chart's notes when it is drawn, else the forecast's own (stage 5: once, never twice). */}
      <NotesBeside codes={chart ? chart.notes : forecast.notes} notes={notes} period={period} />
    </section>
  )
}
