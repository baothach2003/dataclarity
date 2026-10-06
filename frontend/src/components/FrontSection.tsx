// The front section of Insights (the report redesign's step 5; docs/REPORT_REDESIGN.md sections 1 and 8):
// report.json's `front` block printed as it stands, in report.html's order and layout (html_front.py, the
// mock Thach reviewed) - the summary and the sales chart, where the change came from, what was checked, what
// to do next, next month, what this report cannot know. One copy of the wording: every sentence is stage
// 5's (or stage 4's, in the actions), every figure in it formatted there; the page words none.

import { useId } from 'react'
import type { ReactNode } from 'react'
import type { Chart, NoteCode } from '../types/report.ts'
import type { ChecklistGroup, Front } from '../types/reportFront.ts'
import { FrontReadWith } from './FrontReadWith.tsx'
import { FrontSalesChart } from './FrontSalesChart.tsx'
import { FrontWaterfall } from './FrontWaterfall.tsx'

interface FrontSectionProps {
  front: Front
  // report.json's charts.revenue_trend, drawn under the front's own title.
  salesChart: Chart | undefined
  onOpenNote: (code: NoteCode) => void
}

function Card({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  const id = useId()
  return (
    <section className={`card front-card ${className}`} aria-labelledby={id}>
      <h2 className="front-card__title" id={id}>
        {title}
      </h2>
      {children}
    </section>
  )
}

// The marks report.html puts before each line of a group (html_front._MARKS).
const MARKS: Record<ChecklistGroup['kind'], string> = {
  matches: 'yes',
  moved: 'yes',
  against: 'against',
  not_reason: 'no',
  cannot_show: 'cant',
}

function Group({ group }: { group: ChecklistGroup }) {
  return (
    <>
      <h3 className="front__group-title">{group.title}</h3>
      {group.note && <p className="front__small">{group.note}</p>}
      <ul className={`front-check front-check--${MARKS[group.kind]}`}>
        {group.lines.map((line, index) => (
          // Two lines may read alike; their place is their identity.
          <li key={index}>{line}</li>
        ))}
      </ul>
      {group.after && <p className="front__small">{group.after}</p>}
    </>
  )
}

export function FrontSection({ front, salesChart, onOpenNote }: FrontSectionProps) {
  const compared = front.state === 'compared'
  const steps = front.next_steps
  return (
    <>
      <Card title="In 30 seconds" className="front-card--summary">
        {front.caution.map((line) => (
          <p className="front__caution" key={line}>
            {line}
          </p>
        ))}
        {front.summary.map((line) => (
          <p className="front__lead" key={line}>
            {line}
          </p>
        ))}
        {/* Shown once: a caution's lines open the section; otherwise the data checks line stands in "What
            was checked", or here when there is none (html_front._summary). */}
        {front.state === 'not_compared' &&
          front.caution.length === 0 &&
          front.data_checks.map((line) => (
            <p className="front__small" key={line}>
              {line}
            </p>
          ))}
        <p className="front__small">{front.sales_note}</p>
        <FrontReadWith codes={front.notes.summary} onOpen={onOpenNote} />
        {front.state !== 'blocked' && <FrontSalesChart chart={salesChart} title={front.chart_title} notes={front.chart_note} />}
      </Card>

      {compared && (
        <Card title="Where the change came from">
          {front.waterfall !== null ? <FrontWaterfall waterfall={front.waterfall} /> : <p>{front.waterfall_note}</p>}
          <FrontReadWith codes={front.notes.change} onOpen={onOpenNote} />
        </Card>
      )}

      {compared && (
        <Card title="What was checked">
          {front.caution.length === 0 &&
            front.data_checks.map((line) => (
              <p key={line}>{line}</p>
            ))}
          {front.checklist.map((group) => (
            <Group key={group.kind} group={group} />
          ))}
          <FrontReadWith codes={front.notes.checked} onOpen={onOpenNote} />
        </Card>
      )}

      {compared && steps !== null && (
        <Card title="What to do next">
          {steps.sentence && <p>{steps.sentence}</p>}
          {steps.items.map((item) => (
            <div className="front-action" key={item.action}>
              <p className="front__small">{`Rests on: ${item.rests_on}`}</p>
              <p>
                <strong>Action:</strong> <span>{item.action}</span>
              </p>
              <p>
                <strong>Why:</strong> <span>{item.why}</span>
              </p>
              <p className="front__small">{item.watch}</p>
            </div>
          ))}
          <FrontReadWith codes={front.notes.next_steps} onOpen={onOpenNote} />
        </Card>
      )}

      <Card title="Next month">
        {front.next_month.map((line) => (
          <p key={line}>{line}</p>
        ))}
        <FrontReadWith codes={front.notes.next_month} onOpen={onOpenNote} />
      </Card>

      <Card title="What this report cannot know">
        <ul className="front-list">
          {front.cannot_know.map((item) => (
            <li key={item.title}>
              <strong>{`${item.title}.`}</strong> {item.text}
            </li>
          ))}
        </ul>
      </Card>
    </>
  )
}
