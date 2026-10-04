// "Why it happened" - report.json's layer 2 as stage 5 words it (stages/report/html_causes.py), with the
// design gap decisions (Thach, 2026-10-03): the engine's own headline, never an AI narrative; the full
// hypothesis table - every verdict, the ruled-out ones included - in place of the two-column card; what
// the data cannot test; the classes nobody confirmed. No signals table: it reads as an alert and stays in
// the downloadable report (ADR-0007).

import type { DiagnosisView } from '../domain/diagnosisView.ts'
import { verdictOf } from '../domain/diagnosisView.ts'
import { evidenceValue } from '../domain/evidence.ts'
import { money, share } from '../domain/reportFormat.ts'
import type { Causes, HypothesisView, Numbers } from '../types/report.ts'
import { NoteBody } from './NoteBody.tsx'
import { Notice } from './Notice.tsx'

interface CausesSectionProps {
  causes: Causes
  numbers: Numbers
  view: DiagnosisView
}

function HypothesisTable({ hypotheses, causes, numbers, view }: { hypotheses: HypothesisView[] } & CausesSectionProps) {
  return (
    <div className="table-scroll">
      <table className="hypotheses">
        <caption>Every hypothesis tested, the ruled-out ones included</caption>
        <thead>
          <tr>
            <th scope="col">Hypothesis</th>
            <th scope="col">Verdict</th>
            <th scope="col" className="hypotheses__figure">Contribution</th>
            <th scope="col" className="hypotheses__figure">Share</th>
            <th scope="col">Rule and evidence</th>
          </tr>
        </thead>
        <tbody>
          {hypotheses.map((hypothesis) => {
            const verdict = verdictOf(hypothesis, view, numbers)
            return (
              <tr key={hypothesis.id}>
                {/* The row's header, its id and statement apart for a screen reader (the 6E2 review #12). */}
                <th scope="row">
                  <span className="hypotheses__id">{hypothesis.id}</span> {hypothesis.statement}
                </th>
                <td>
                  <span className={verdict.against ? 'verdict verdict--against' : `verdict verdict--${hypothesis.verdict}`}>
                    {verdict.label}
                  </span>
                </td>
                <td className="hypotheses__figure">{hypothesis.contribution === null ? '' : money(hypothesis.contribution)}</td>
                <td className="hypotheses__figure">{hypothesis.share === null ? '' : share(hypothesis.share)}</td>
                <td>
                  <details>
                    <summary aria-label={`Rule and evidence for ${hypothesis.id}`}>Details</summary>
                    <p>{hypothesis.rule}</p>
                    {Object.keys(hypothesis.evidence).length > 0 && (
                      <ul className="hypotheses__evidence">
                        {Object.entries(hypothesis.evidence).map(([key, value]) => (
                          <li key={key}>{`${key}: ${evidenceValue(value, causes.suggested_classes)}`}</li>
                        ))}
                      </ul>
                    )}
                  </details>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function CausesSection({ causes, numbers, view }: CausesSectionProps) {
  const period = numbers.period
  const narration = causes.narration
  const suggested = Object.entries(causes.suggested_classes)

  // Rule 1 (the design gap review): the trust gate blocked the run, so the causes are replaced by the
  // reason. The data checks it did run (D1-D3) are the trust badge's own lines above.
  if (causes.headline.rule === 1) {
    return (
      <section className="card insights-card">
        <h2 className="insights-card__title">Why it happened</h2>
        <p className="insights-headline">{causes.headline.message}</p>
        <p>No cause was tested: the data trust check blocked this run. The data checks are in the badge above.</p>
      </section>
    )
  }

  return (
    <section className="card insights-card">
      <h2 className="insights-card__title">Why it happened</h2>
      <p className="insights-headline">{causes.headline.message}</p>
      {narration === null ? (
        <Notice tone="info" title="The AI narration is unavailable for this report" />
      ) : (
        <div className="insights-narration">
          <h3 className="insights-card__subtitle">The AI&apos;s reading</h3>
          <p>{narration.summary}</p>
          <p>{narration.headline_explanation}</p>
          <ul>
            {narration.hypothesis_notes.map((note) => (
              <li key={note.id}>{`${note.id}: ${note.text}`}</li>
            ))}
          </ul>
          <p>{narration.not_tested_note}</p>
        </div>
      )}
      {causes.hypotheses_note && (
        // Above the table it qualifies (decision 4): the verdicts describe a change too small, or a
        // history too short, to single one out.
        <Notice tone="info" title="About these verdicts">
          {causes.hypotheses_note}
        </Notice>
      )}
      <HypothesisTable hypotheses={causes.hypotheses} causes={causes} numbers={numbers} view={view} />
      {numbers.unconfirmed_placeholders_reason && (
        // The customer causes read the same customers (2E-u3).
        <p className="insights-reason">{numbers.unconfirmed_placeholders_reason}</p>
      )}
      {causes.not_testable.length > 0 && (
        <>
          <h3 className="insights-card__subtitle">What this data cannot test</h3>
          <ul>
            {causes.not_testable.map((item) => (
              <li key={item.id}>{`${item.statement}: ${item.reason}`}</li>
            ))}
          </ul>
        </>
      )}
      {causes.notes.length > 0 && (
        // As text where the diagnosis is: a pointer by note code matched no visible label (the 6E2
        // review #13); the KPI cards keep theirs behind their markers.
        <>
          <h3 className="insights-card__subtitle">Notes on the diagnosis</h3>
          {causes.notes.map((note) => (
            <NoteBody key={note.code} note={note} period={period} />
          ))}
        </>
      )}
      {suggested.length > 0 && (
        <div className="table-scroll">
          <table className="hypotheses">
            <caption>Classes suggested for these products that nobody confirmed in Review</caption>
            <thead>
              <tr>
                <th scope="col">Product</th>
                <th scope="col">Suggested class</th>
              </tr>
            </thead>
            <tbody>
              {suggested.map(([product, lineClass]) => (
                <tr key={product}>
                  <td>{product}</td>
                  <td>{lineClass}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
