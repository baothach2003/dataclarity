// Section 2, "Where the change came from" (the report redesign's step 5; report.html's _waterfall and
// html_svg.waterfall_chart, the layout Thach approved): last month's sales at zero, each part from where the
// last ended, then the whole change - drawn from report.json's front.waterfall, whose bars are diagnosis.json's
// bridge, never a split the bridge withholds (Q17). Every printed figure is stage 5's own text; the table
// gives each bar's words, which a screen reader can read and the chart cannot give.

import { Bar, BarChart, CartesianGrid, LabelList, Rectangle, ReferenceLine, XAxis, YAxis } from 'recharts'
import type { BarShapeProps } from 'recharts'
import { useCurrencyCode } from '../domain/currencyCode.ts'
import { waterfallRows } from '../domain/frontView.ts'
import type { WaterfallRow } from '../domain/frontView.ts'
import { count } from '../domain/reportFormat.ts'
import { useNarrow } from '../domain/useNarrow.ts'
import type { Waterfall } from '../types/reportFront.ts'

const TITLE = 'Where the change came from'

function fill(row: WaterfallRow | undefined): string {
  if (row === undefined || row.factor === null) {
    return 'var(--text-secondary)'
  }
  return row.shown >= 0 ? 'var(--accent)' : 'var(--severity-high)'
}

/** An axis tick: geometry, signed and whole, the currency's code on it as report.html's axis has. */
function tick(value: number, code: string | null): string {
  if (value === 0) {
    return '0'
  }
  const text = `${value > 0 ? '+' : '-'}${count(Math.abs(value))}`
  return code ? `${code} ${text}` : text
}

export function FrontWaterfall({ waterfall }: { waterfall: Waterfall }) {
  const code = useCurrencyCode()
  const narrow = useNarrow()
  const rows = waterfallRows(waterfall)
  const previous = waterfall.previous_label.split(' ').slice(0, -2).join(' ')
  const current = waterfall.current_label.split(' ').slice(0, -2).join(' ')

  return (
    <>
      <p className="front__small">{waterfall.caption}</p>
      <p className="front__small">{`0 = ${waterfall.previous_label} (${waterfall.previous_text})`}</p>
      <div className="chart-frame" role="img" aria-label={`${TITLE}, drawn as bars: the table below gives every figure`}>
        {/* A phone draws the same bars across, each label on its own line: five labelled columns do not fit
            at 390 px (the app check, 2026-10-06). */}
        <BarChart
          responsive
          accessibilityLayer={false}
          data={rows}
          layout={narrow ? 'vertical' : 'horizontal'}
          style={{ width: '100%', height: narrow ? 64 + rows.length * 44 : 280 }}
          margin={narrow ? { top: 8, right: 72, bottom: 0, left: 0 } : { top: 24, right: 8, bottom: 0, left: 8 }}
        >
          <CartesianGrid stroke="var(--divider)" vertical={narrow} horizontal={!narrow} />
          {narrow ? (
            <>
              <XAxis type="number" tickFormatter={(value: number) => tick(value, code)} tick={{ fontSize: 10 }} tickCount={3} />
              <YAxis type="category" dataKey="label" interval={0} tick={{ fontSize: 11 }} width={112} />
              <ReferenceLine x={0} stroke="var(--text-secondary)" />
            </>
          ) : (
            <>
              <XAxis dataKey="label" interval={0} tick={{ fontSize: 11 }} height={44} />
              <YAxis tickFormatter={(value: number) => tick(value, code)} tick={{ fontSize: 11 }} width={88} />
              <ReferenceLine y={0} stroke="var(--text-secondary)" />
            </>
          )}
          {/* Each bar coloured by its own direction, the whole change apart (report.html's up / down / tot). */}
          <Bar
            dataKey="range"
            isAnimationActive={false}
            radius={3}
            shape={(props: BarShapeProps) => <Rectangle {...props} fill={fill(rows[props.index])} />}
          >
            <LabelList
              dataKey="worth"
              position={narrow ? 'right' : 'top'}
              style={{ fontSize: narrow ? 11 : 12, fontWeight: 600, fill: 'var(--text-primary)' }}
            />
          </Bar>
        </BarChart>
      </div>
      <div className="table-scroll">
        <table className="hypotheses">
          <caption>{TITLE}</caption>
          <thead>
            <tr>
              <th scope="col">Part</th>
              <th scope="col">{`${previous} → ${current}`}</th>
              <th scope="col" className="hypotheses__figure">
                Worth
              </th>
            </tr>
          </thead>
          <tbody>
            {waterfall.bars.map((bar) => (
              <tr key={bar.factor}>
                <th scope="row">{bar.label}</th>
                <td>{`${bar.was} → ${bar.now}`}</td>
                <td className="hypotheses__figure">{bar.worth}</td>
              </tr>
            ))}
            <tr>
              <th scope="row">
                <strong>Total change</strong>
              </th>
              <td />
              <td className="hypotheses__figure">
                <strong>{waterfall.change_text}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {waterfall.note && <p className="front__small">{waterfall.note}</p>}
    </>
  )
}
