# ADR-0003: Model selection policy - reasoning model vs. bulk model, never the largest at runtime

## Status
Accepted

## Date
2026-09-19 (Phase 0/1C; formalized in this ADR 2026-09-22)

## Context
DataClarity calls the Anthropic API for two different kinds of work:

- **Reasoning-shaped steps**: inferring a schema from a messy CSV, proposing
  a cleaning plan, explaining a root cause, and turning metrics + diagnosis
  into a ranked strategy (`docs/AI_PIPELINE.md` section 2). All four of v1's
  AI calls are this kind - each one needs to weigh evidence and produce a
  structured, justified answer.
- **High-volume, low-complexity tasks**: work that would need to run many
  times per file at low cost per call - e.g. suggesting a category label
  row-group by row-group (`docs/AI_PIPELINE.md` section 2, "reserved for
  future"). None of these exist in v1, but the pipeline's cost profile
  changes sharply the moment one does: a per-row or per-group call at
  reasoning-model pricing would dominate the run's cost.

Model ids also change over time (new Claude releases, deprecations), and this
project already treats "no hardcoded model ids" as a hard rule
(`CLAUDE.md` section 6). A policy about *which kind of model* to use for
*which kind of task* needs to survive a model rename without becoming stale,
which rules out writing the policy in terms of a specific id.

Separately, using the single most capable model available for every runtime
call is the default a new project drifts into without a boundary - it always
scores best on quality per call, so nothing stops picking it again next time,
even where it is not needed and where cost scales with call volume.

## Decision
Model selection is a **policy expressed through two required settings**, not
a hardcoded choice:

- `MODEL_REASONING` (`Settings.model_reasoning`) - the model used for every
  step that has to weigh evidence and justify a structured answer. Currently
  all four of v1's AI calls (schema inference, cleaning plan, root cause,
  strategy - `backend/app/services/analysis.py` passes
  `settings.model_reasoning` into both stage-1 calls) use this setting.
- `MODEL_BULK` (`Settings.model_bulk`) - reserved for high-volume, low-
  complexity tasks. Not called anywhere in v1 (`docs/AI_PIPELINE.md` section
  2: "reserved for future cheap bulk tasks... not used in v1"), but required
  like every other setting (`Settings` has no defaults - a missing variable
  stops the app at startup, `backend/app/config.py`), so the moment a bulk
  task is added, the setting already exists and is already wired through
  `shared/ai_client.py`'s `call_structured(..., model, ...)` parameter rather
  than a literal string.

Neither setting may name the largest available model at runtime by default
(`PROJECT_PLAN.md` section 3: "Never Opus at runtime (cost)"). A larger model
is a deliberate, reasoned exception, not the default path - the same policy
document draws that line for Claude Code itself, developing the project
("Opus 5 only for hard debugging or architecture decisions",
`PROJECT_PLAN.md` section 7), separately from the runtime policy this ADR
covers.

A hard budget backs the policy at the call-site level, independent of which
model answers: at most 4 AI calls per run (one per AI step) plus one shared
retry (`PROJECT_PLAN.md` section 7; enforced by `shared/RunWork`'s per-run,
per-step attempt cap, `docs/AI_PIPELINE.md` section 2/3).

## Consequences

**Benefits**
- The policy survives a model rename or a new release: swapping
  `MODEL_REASONING`/`MODEL_BULK` in `.env` changes what every call site uses,
  with no code or prompt-template change, and no ADR revision needed for a
  routine version bump.
- Cost stays proportional to task shape: reasoning-heavy, low-volume calls
  use a capable model; if a high-volume task is ever added, it has a cheaper
  model already provisioned instead of inheriting the reasoning model by
  default.
- Explicitly ruling out the largest model as a runtime default removes a
  decision that would otherwise have to be re-litigated at every new AI call
  site ("which model should this use?") - the answer is "reasoning or bulk,
  per the settings," not "whichever is best available today."

**Trade-offs accepted**
- `MODEL_BULK` is unused in v1: it is a required setting with no consumer
  yet, which is unusual for this codebase's "no field without a default on
  purpose... a missing variable stops the app" philosophy applied to a value
  nothing reads. Accepted because the alternative - adding it only once a
  bulk task exists - would need a config *and* a code change at the same
  time under time pressure, instead of the config already being in place and
  tested (`.env.example`, `tests/conftest.py`'s `TEST_ENV`).
- The policy governs *which class* of model to use, not *how well* either
  model performs the task - a weaker reasoning model chosen under
  `MODEL_REASONING` would still pass this policy while producing worse
  answers. Model quality is evaluated separately (the 1C real-API check,
  `PROJECT_PLAN.md` section 12 Notes), not something this ADR's boundary can
  catch on its own.
- Excluding the largest model from the runtime default means a genuinely
  hard case (e.g. an unusually messy file the reasoning model mishandles)
  has no automatic escalation path - degrading gracefully
  (`docs/AI_PIPELINE.md` section 1, principle 5) is the accepted fallback
  instead of retrying on a bigger model.
