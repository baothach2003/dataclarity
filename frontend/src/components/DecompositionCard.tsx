// "Where the revenue change came from" (frame `Insights` 4:1489; the design gap review: it matches, with a
// file without order numbers named in lines, a tree that can be null, and a second level). Stage 3's
// lever tree from diagnosis.json (CONTRACTS 11's FE rows): each factor's two months and its contribution,
// drawn to scale. The page computes no figure: revenue's months and change are the KPI's own. Not shown
// beside a previous month that is not compared, nor a withheld current one (CONTRACTS 11).

import type { OrdersBasis } from '../api/analysis.ts'
import type { Decomposition, DiagnosisView, FactorName } from '../domain/diagnosisView.ts'
import { signedMoney } from '../domain/diagnosisView.ts'
import { change, count, money } from '../domain/reportFormat.ts'
import type { NoteFigure, NoteView, Numbers } from '../types/report.ts'
import { NotesBeside } from './NotesBeside.tsx'

// Stage 3's customers are BUYERS - customers with a sale row (lever.period_totals) - not the KPI's active
// customers, which count a customer who only returned goods (the 6E2 review #1); a file without trusted
// order numbers counts lines (metrics.json core.orders_basis; CONTRACTS 6).
function factorLabel(name: FactorName, basis: 'order_id' | 'lines'): string {
  const lines = basis === 'lines'
  switch (name) {
    case 'customers':
      return 'Customers who bought'
    case 'frequency':
      return lines ? 'Lines per customer who bought' : 'Orders per customer who bought'
    case 'orders':
      return lines ? 'Lines' : 'Orders'
    case 'aov':
      return lines ? 'Average line value' : 'Average order value'
    case 'units_per_order':
      return lines ? 'Units per line' : 'Units per order'
    case 'price_per_unit':
      return 'Price per unit'
  }
}

// Counts whole; a rate or a value to two decimals (the frame: "2.10 -> 2.14", "40.00 -> 40.40").
function factorValue(name: FactorName, value: number): string {
  return name === 'customers' || name === 'orders' ? count(value) : money(value)
}

const CALENDAR_WORDS = { weekday_weights: 'which weekdays each month had', day_count: 'how many days each month had' }

// The figures the lever splits: a note naming one stands beside it (CLAUDE.md 3.3a).
const LEVER_FIGURES = new Set<NoteFigure>(['revenue', 'customers', 'orders', 'aov'])

interface DecompositionCardProps {
  view: DiagnosisView
  numbers: Numbers
  ordersBasis: OrdersBasis
  // The notes the report shows beside figures (layers 1 and 2).
  notes: NoteView[]
}

function Factors({
  level,
  basis,
  largest,
  walkIns,
}: {
  level: Decomposition
  basis: 'order_id' | 'lines'
  largest: number
  walkIns: boolean
}) {
  return (
    <>
      {level.factors.map((factor) => {
        const amount = signedMoney(factor.contribution)
        // The direction is the printed figure's: one that prints as zero has none (no colour, no bar).
        const direction = amount.startsWith('+') ? 'up' : amount.startsWith('-') ? 'down' : 'flat'
        // The bar's length is the contribution's size against the largest - a drawing, as a chart is.
        const width = largest > 0 ? `${((Math.abs(factor.contribution) / largest) * 100).toFixed(1).replace(/\.0$/, '')}%` : '0%'
        return (
          <div className="decomposition__row" data-testid="factor" key={factor.name}>
            <div>
              <p className="decomposition__label" data-cell>
                {factorLabel(factor.name, basis)}
              </p>
              <p className="decomposition__values" data-cell>
                {`${factorValue(factor.name, factor.valuePrev)} → ${factorValue(factor.name, factor.valueCur)}`}
              </p>
              {walkIns && (factor.name === 'customers' || factor.name === 'frequency') && (
                // Unconfirmed walk-in candidates count as customers here too (2E-u3; the 6E2 review #5).
                <p className="kpi-card__mark">includes possible walk-ins not confirmed (see above)</p>
              )}
            </div>
            {/* A diverging bar: a fall grows left of the centre line, a rise right of it. */}
            <div className="decomposition__track" aria-hidden="true">
              {direction !== 'flat' && (
                <div className={`decomposition__half decomposition__half--${direction}`}>
                  <span className={`decomposition__bar decomposition__bar--${direction}`} style={{ width }} />
                </div>
              )}
            </div>
            <p className={`decomposition__amount decomposition__amount--${direction}`} data-cell>
              {amount}
            </p>
          </div>
        )
      })}
    </>
  )
}

export function DecompositionCard({ view, numbers, ordersBasis, notes }: DecompositionCardProps) {
  const revenue = numbers.kpis.find((kpi) => kpi.id === 'revenue')
  const level1 = view.level1
  // Unread basis: no factor is named by a guess (the 6E2 review #16).
  if (
    !level1 ||
    ordersBasis === null ||
    !numbers.period.previous_complete ||
    !revenue ||
    revenue.current === null ||
    revenue.previous === null
  ) {
    return null
  }
  const level2 = view.level2
  const pair = view.maskedShiftPair
  const largest = Math.max(
    ...[...level1.factors, ...(level2?.factors ?? []), ...(pair?.factors ?? [])].map((factor) => Math.abs(factor.contribution)),
  )
  const walkIns = Boolean(numbers.unconfirmed_placeholders_reason)
  const besideLever = notes.filter((note) => note.figures.some((figure) => LEVER_FIGURES.has(figure)))
  const calendar = view.calendar

  return (
    <section className="card insights-card decomposition">
      <h2 className="insights-card__title">Where the revenue change came from</h2>
      <Factors level={level1} basis={ordersBasis} largest={largest} walkIns={walkIns} />
      {level2 && (
        <>
          <p className="decomposition__group">{`${factorLabel('aov', ordersBasis)}, split`}</p>
          <Factors level={level2} basis={ordersBasis} largest={largest} walkIns={false} />
        </>
      )}
      {pair && (
        // Rule 4's headline cites this pair's two contributions (headline.py; the 6E2 review #15).
        <>
          <p className="decomposition__group">
            {`The same change as ${factorLabel('orders', ordersBasis).toLowerCase()} × ${factorLabel('aov', ordersBasis).toLowerCase()}`}
          </p>
          <Factors level={pair} basis={ordersBasis} largest={largest} walkIns={false} />
        </>
      )}
      <div className="decomposition__row decomposition__total" data-testid="decomposition-total">
        <div>
          <p className="decomposition__label">Revenue</p>
          <p className="decomposition__values">{`${money(revenue.previous)} → ${money(revenue.current)}`}</p>
        </div>
        <span aria-hidden="true" />
        {revenue.change_pct !== null ? (
          <p className="decomposition__amount">{change(revenue.change_pct)}</p>
        ) : (
          revenue.change_reason && <p className="decomposition__reason">{revenue.change_reason}</p>
        )}
      </div>
      {calendar && (
        // The design gap review's ADD 12. calendar_effect is the change the calendar alone predicts and
        // calendar_adjusted_change the change less it (stages/diagnose/calendar_effect.py): an estimate,
        // signed, never "accounts for" - T1 may rule the calendar out (the 6E2 review #4).
        <p className="insights-reason">
          {`By the calendar alone (${CALENDAR_WORDS[calendar.method]}), revenue would be expected to change by ${signedMoney(calendar.calendarEffect)}; net of that, the change is ${signedMoney(calendar.calendarAdjustedChange)}.`}
        </p>
      )}
      <NotesBeside notes={besideLever} period={numbers.period} />
    </section>
  )
}
