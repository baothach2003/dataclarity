# ADR-0002: pandas computes, AI only interprets

## Status
Accepted

## Date
2026-09-18 (Phase 0, formalized alongside the AI pipeline design in
`docs/AI_PIPELINE.md`; this ADR written 2026-09-22)

## Context
DataClarity reports numbers a user will act on - revenue, growth, churn risk,
stockout dates, forecast recommendations. The Anthropic API is used four
times per run at most (`docs/AI_PIPELINE.md` section 2: schema inference,
cleaning plan, root cause, strategy), and every one of those calls sees only
a bounded slice of the data: a truncated profile, up to 30 stratified sample
rows, or a previously computed JSON contract - never the full file
(`docs/AI_PIPELINE.md` section 1, principle 1).

A system built this way faces one central design question: which parts of
the pipeline are allowed to *produce a number that ends up in the report*,
and which parts are only allowed to *talk about* numbers someone else already
produced? Blurring that line - letting the model estimate a total, average an
already-summarized figure, or "helpfully" fill in a gap - would put an
unverifiable, non-reproducible number in a report whose whole purpose is to
be decision-ready.

## Decision
**pandas computes. The AI only interprets.**

- Every number that appears in `metrics.json`, `diagnosis.json`,
  `forecast.json` and `report.json` comes from a tested pandas function -
  `stages/analyze/metrics_*.py`, `stages/diagnose/decomposition.py`,
  `stages/predict/forecast.py`. The AI is never the source of a KPI, a
  percentage, a count, or a projected date.
- The AI's role is strictly interpretive: given already-computed numbers
  (metrics, decomposition, forecast), it explains *why* they moved and what
  to do about it (`prompts/root_cause.md`, `prompts/strategy.md`). Every
  prompt template embeds an explicit prohibition: no invented numbers, every
  claim must cite a figure present in the input (`docs/AI_PIPELINE.md`
  section 4).
- Stage 1 is the one place the AI's output *shapes* what pandas will later
  compute (the semantic types and the cleaning plan), but even there the AI
  chooses only from a fixed, whitelisted transform catalog
  (`docs/AI_PIPELINE.md` section 6) - it names an action and its parameters,
  it never performs the transform or computes the affected-row count itself;
  `stages/ingest/transforms.py` does, and the user approves the plan before
  anything runs (`CLAUDE.md` section 3.3).
- AI output is treated as **untrusted input at every step**: validated
  against a Pydantic response model, checked against a hand-written legality
  and coverage check (every profiled column named exactly once, every action
  in the catalog, figures cross-checked against pandas' own counts where one
  exists), retried once on failure, and degraded gracefully - never trusted
  by default (`CLAUDE.md` section 3.2; `shared/ai_client.py`,
  `docs/AI_PIPELINE.md` section 3).

## Consequences

**Benefits**
- Every number in the final report is independently reproducible: re-run the
  same clean data through the same pandas function and it does not change,
  regardless of what the model says on a given day. This is a hard
  requirement for a report meant to support a business decision.
- The system degrades gracefully when the AI is unavailable
  (`docs/AI_PIPELINE.md` section 1, principle 5): profiling, manual plan
  building, and all of stages 2-5's computed numbers still work with the AI
  entirely offline - only narrative text (schema suggestions, root-cause
  prose, strategy recommendations) is lost, never a number.
- Bounding what the AI ever sees (max 30 sample rows, 25-60 columns, a JSON
  contract instead of raw data for stages 3-4) is only possible because the
  AI was never going to need the full data to *compute* anything - it only
  needs enough to talk about what pandas already computed.

**Trade-offs accepted**
- The AI cannot notice a real pattern that the fixed set of pandas metrics
  does not already surface - if a KPI worth reporting is not in
  `metrics_core.py`/`metrics_customers.py`/`metrics_products.py`, the AI has
  no way to compute it on the fly to fill the gap. Extending what's reported
  means writing and testing a new pandas function, not asking the model to
  try harder.
- Validation, the retry-once policy, and the catalog whitelist are all extra
  code and tests that a "just trust the model's JSON" design would not need.
  Accepted because the alternative fails silently exactly where it matters
  most: a hallucinated number is far more costly, and far harder to catch,
  than an extra validation pass.
- The cleaning plan is limited to the transform catalog (section 6) even when
  a smarter one-off fix might exist for a specific messy file - a transform
  the AI cannot name, pandas cannot yet run, and the plan cannot include it.
