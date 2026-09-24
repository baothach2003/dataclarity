# DataClarity - Project Plan (v2)

> Official roadmap. Used by both Thach and Claude Code. At the start of EVERY new
> session, re-read section 12 "Current Status" before doing anything. Functional
> detail lives in `docs/SPECS.md`, stage contracts in `docs/CONTRACTS.md`, AI
> internals in `docs/AI_PIPELINE.md`. This plan indexes phases and tasks only.

## 1. What this project is

**DataClarity** is a web application that turns a messy inventory/sales CSV into a
decision-ready report, through a 5-stage pipeline:

| Stage | Name | Question it answers | Package |
|---|---|---|---|
| 1 | Collect | What data do we actually have, and is it trustworthy? | `stages/ingest/` |
| 2 | Analyze | What is happening in this business? | `stages/analyze/` |
| 3 | Diagnose | Why is it happening? | `stages/diagnose/` |
| 4 | Predict | What happens next, and what should we do? | `stages/predict/` |
| 5 | Report | How do we present this so a human can decide? | `stages/report/` |

Stage 1 is the interactive part: the user uploads a CSV, AI infers the schema and
proposes a cleaning plan, the user reviews and edits it in the UI with before/after
preview, then approves. Stages 2-5 then run on the approved clean data.

**Secondary goal (equally important):** portfolio/CV project supporting an ICT
Business Analyst profile for a 190 visa application. Requires clean code, tests,
a professional README, a deployed demo link, and AI integration defensible in an
interview (not a thin wrapper).

**What to cut first if time runs short:** dashboard polish and stage 4 forecasting
sophistication. Never cut: the review-and-approve flow (stage 1) or the root-cause
logic (stage 3). Those are the differentiators.

## 2. Architecture decision: one repo, five independent packages

Each stage is a **self-contained Python package** that:
- reads its input only from the previous stage's **contract file** (JSON on disk,
  schema in `docs/CONTRACTS.md`, validated by Pydantic models in `contracts/`)
- writes its output as the next contract file
- can be run standalone from the CLI: `python -m stages.diagnose --run <run_id>`
- **must never import from another stage package**

This boundary is enforced by an automated test (`tests/test_architecture.py`)
that parses imports with `ast` and fails the build on any cross-stage import.
Full rationale, the alternative considered (five separate repos) and the
trade-offs accepted: `docs/adr/0001-stage-isolation-single-repo.md`.

```
[React frontend] --HTTP--> [FastAPI backend] --calls--> [stages/*]
                                  |                          |
                                  v                          v
                            [PostgreSQL]          [runs/<run_id>/*.json contracts]
```

## 3. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend API | Python 3.11+, FastAPI | One language for API and analysis |
| Data processing | pandas | 50MB / few hundred thousand rows ceiling; no Spark needed |
| Forecasting | statsmodels (or pure pandas rolling stats) | Interpretable; no heavy ML dependency |
| AI runtime | Anthropic API: `claude-sonnet-5` (inference, diagnosis, strategy), `claude-haiku-4-5` (cheap bulk tasks) | Sonnet where reasoning matters, Haiku where volume matters. Never Opus at runtime (cost) |
| Database | PostgreSQL + SQLAlchemy + Alembic | Migrations from day one (lesson learned) |
| Frontend | React + Vite + TypeScript | TS required, no plain JS |
| Charts | Recharts | Same as previous project |
| Design | Figma Pro (Thach) | Node ids recorded in `docs/FIGMA_DESIGN_NOTES.md` |
| Deploy | Render (API + DB), Vercel (frontend) | Free tier sufficient |
| Tests | pytest, Vitest | AI always mocked in tests |

## 4. Folder Structure (target)

```
dataclarity/
├── CLAUDE.md  PROJECT_PLAN.md  CONSTRAINTS.md  KICKOFF_PROMPT.md  README.md
├── docs/           SPECS.md  CONTRACTS.md  AI_PIPELINE.md  FIGMA_DESIGN_NOTES.md
├── prompts/        schema_inference.md  cleaning_plan.md  root_cause.md  strategy.md
├── contracts/      # Pydantic models shared by all stages - the ONLY shared import
│   ├── profile.py  cleaning.py  metrics.py  diagnosis.py  forecast.py  report.py
├── stages/
│   ├── ingest/     # stage 1: profiling, AI schema inference, cleaning engine
│   ├── analyze/    # stage 2: KPI + RFM + Pareto computation
│   ├── diagnose/   # stage 3: decomposition + AI root cause
│   ├── predict/    # stage 4: forecast + AI strategy
│   └── report/     # stage 5: HTML report assembly
├── backend/app/    # FastAPI: routers/, services/ (orchestration only), models/
├── frontend/src/   # api/  pages/  components/  types/
├── runs/           # per-run contract files + outputs (gitignored)
└── tests/          # unit tests per stage + test_architecture.py + e2e
```

## 5. Phases (small on purpose - one sub-phase = one Claude Code session)

> Hard rule: one sub-phase per session. Finishing early is fine; starting the next
> one is not, unless Thach explicitly says so.

### Phase 0 - Foundations
- [x] 0A Repo init, folder skeleton, backend FastAPI app factory, `/health`,
      config via pydantic-settings + `.env.example`, pytest wired, 1 passing test
- [x] 0B `contracts/` package: Pydantic models for all 6 contract modules per
      `docs/CONTRACTS.md` (8 models for the 9 JSON files), with validation
      tests
- [x] 0C `tests/test_architecture.py`: AST-based test failing on cross-stage
      imports, and on any import of `app` or `backend` from `stages/` or
      `shared/` (backs SPECS SEC-4); also stages -> web/DB frameworks,
      shared -> stages, and contracts -> anything internal or a framework
- [x] 0C2 Run registry helper (`shared/run_registry.py`: `runs/<run_id>/`
      creation, path resolution); `Settings.runs_dir` anchored to the repo
      root
- [x] 0D Frontend skeleton: Vite + React + TS, `/health` call, CORS via env var
- **DoD:** both apps run; architecture test passes; contracts importable
  (met 2026-09-19: "Backend: ok" confirmed by Thach in the browser)

### Phase 1 - Stage 1 Collect (backend)
- [x] 1A Upload endpoint `POST /api/runs` (multipart, `MAX_UPLOAD_MB` cap and
      type validation per SPECS section 11 SEC-1, including the 50MB ceiling
      check at startup), file stored under `runs/<run_id>/raw.csv`. A binary
      file renamed to `.csv` is rejected by a NUL-byte check on the first
      8 KB (PARSE_FAILED); 0-byte and whitespace-only files are EMPTY_FILE.
      The `runs` DB row moved to 1A2 (Thach's decision)
- [x] 1A2 Database setup and the `runs` row: SQLAlchemy engine/session,
      Alembic init, the `runs` migration per SPECS section 9 (pulled forward
      from 7A), `POST /api/runs` writes the row (`status=uploaded`,
      `expires_at` from `RETENTION_HOURS`), and a DB/filesystem consistency
      test. Tests use SQLite (Thach's decision; the migration also runs
      against SQLite in a test); PostgreSQL only for dev/deploy, verified by
      hand. Needs PostgreSQL installed locally. Decide the write order, so a
      failed DB insert cannot leave an orphan `raw.csv` (or the reverse)
- [x] 1B `stages/ingest/profiling.py`: pure pandas per-column + dataset stats ->
      `profile.json` contract. Unit tests with fixture CSVs. Rejects a
      header-only file with EMPTY_FILE (SPECS section 10; 1A only rejects
      0-byte and whitespace-only files, without parsing). No stage CLI was
      added in 1B; the runs-root question moved to 5D
- [x] 1C `shared/ai_client.py` (`docs/AI_PIPELINE.md` section 3) with the
      real-API guard fixture that activates CONSTRAINTS F4, then
      `stages/ingest/ai_input.py` + `ai_schema.py`: AI stage A (schema
      inference) via the AI client, validated, retry-once, degraded mode.
      Checks that every profiled column appears exactly once (CONTRACTS
      section 3). `AIUnavailable` carries a reason code and the client logs
      it; the reason is not written to a contract file (Thach's decision:
      stage 1 degraded writes no file at all)
- [x] 1D `stages/ingest/transforms.py`: the full transform catalog
      (`docs/AI_PIPELINE.md` section 6) as pure functions + change log. One test
      per transform including edge cases. Also count, in pandas, the issue
      codes the profile holds no figure for (negative_values, zero_values,
      trailing_whitespace, invalid_dates, outliers_iqr, ...), so
      `ai_schema.py` can replace the AI's estimate with the computed count
      (1C checks only missing_values, duplicate_rows and all_null_column), and
      consider sample-row kinds 1C does not pick yet (text in a mostly numeric
      column, whitespace, bad dates)
- [x] 1E `stages/ingest/ai_plan.py`: AI stage B (cleaning plan) + catalog/legality
      validation. Tests with mocked AI. Also wired the pandas issue counts into
      `ai_schema.py` (`issue_recount.py`) and defined the business key, as the
      1D handover asked. The checks are in `plan_checks.py` and the param rules
      in `transform_params.py` (docs/AI_PIPELINE.md section 11)
- [x] 1F `stages/ingest/cleaning.py`: preview (sample) and execute (full) engines
      -> `cleaned.csv` + `cleaning_report.json` (+ `plan_final.json`, which nothing
      owned). Delivered: `cleaning.py` (`apply_plan`, the one place a plan runs, and
      `execute_run`), `preview.py` (`preview_run` / `preview_frame`, the sample and the
      20 rows shown), `plan_validation.py` (the plan the user submits, checked again),
      `transform_types.py` (the `transforms.py` split, 322 -> 281 lines),
      `problem_rows.py`, `contract_files.write_files_atomically` (with rollback), the
      `encoding_fallback` warning. Resolved from 1E: mixed UTC offsets keep the date as
      written; `drop_rows_missing` runs before the imputations; execute rejects a plan
      that drops a required field. Still open, in AI_PIPELINE section 12 "Known limits":
      one action per column (kept by decision until the review screen, 6B, shows what
      is needed), a plan cannot require `transaction_date` to be parsed
- [x] 1G Endpoints wiring: `/analyze-schema`, `/plan`, `/preview`, `/execute` per
      `docs/SPECS.md` section 8 (now updated with the built response shapes and the
      state table). Delivered: `app/schemas.py` (response models, `Notice`), `app/errors.py`
      (the envelope now also covers FastAPI's own 422/404/405 and an unexpected exception,
      via `RequestValidationError`/`StarletteHTTPException` handlers and an in-CORS
      middleware for `Exception`, so a 500 still carries CORS headers),
      `app/services/run_state.py` (the state machine: `load_run`/`load_live_run`,
      `require_status`, `advance`/`fail`, `claim_for_cleaning` with a compare-and-swap
      retry loop, `release`, `recover_claim`), `app/services/run_memory.py` (`FrameCache`
      bounded by measured bytes and idle time, one read lock per run so a slow parse of
      one run never blocks another; `RetryBudgets`, one `RetryBudget` per run shared by
      the schema and plan steps; `RunWork`, one piece of work at a time per run and a
      3-attempt cap per AI step, RATE_LIMITED past that), `app/services/analysis.py`
      (`analyze_schema`, `propose_plan`), `app/services/plan_execution.py`
      (`preview_plan`, `execute_plan`), `app/services/stage_errors.py` (every stage
      exception -> its SPECS section 10 code). A new `cleaning` run status (Alembic
      migration `5c1e7b3d9a42`) is the claim `execute` holds; a run left in it by a dead
      process or a lost status write is freed by the next call that reaches it
      (`load_live_run`), `cleaned` if its report exists, else `planned` - never a
      background sweep, since v1 runs one process. `execute_run` gained
      `require_required_fields=False` for a NOT_INVENTORY run (generic cleaning has
      nothing to map). Doubt-driven review (one cycle, fresh reviewer, cross-model
      declined by Thach) found 5 high-severity issues before anything was reviewed a
      second time: a missing prompt file leaking a server path as a false INVALID_STATE;
      a run strandable in `cleaning` forever; the AI callable an unbounded number of
      times per run (and a race where a slow request's answer could overwrite a
      concurrent one's, or claim a status the run no longer has); and one slow preview
      able to block every other request behind a single global parse lock. All fixed,
      each with a reproducing test, then verified by mutation testing (every mutant of
      the fix killed). `test_config.py`/`.env.example` gain `PREVIEW_CACHE_MAX_MB` and
      `PREVIEW_CACHE_TTL_SECONDS`, both required like every other setting: an existing
      `.env` needs the two lines added or the backend will not start
- **DoD:** full stage 1 works end-to-end via API only (no UI), verified on a
  deliberately messy fixture CSV (met 2026-09-22: upload -> analyze-schema -> plan ->
  preview -> execute driven through the API with the AI mocked, state transitions and
  409s on out-of-order calls asserted; concurrent-execute and concurrent-AI-step races
  driven with real threads and a real SQLite file so the claim is proven, not assumed)

### Phase 2 - Stage 2 Analyze
- [x] Install skills Wave 2 (see docs/SKILLS.md)
- [x] Create `docs/adr/` (own docs session, after the Wave 2 install, using
      documentation-and-adrs) with: ADR-0001 one repo with five independent
      stage packages; ADR-0002 pandas computes, AI only interprets; ADR-0003
      model choice per task (reasoning model vs bulk model via `MODEL_REASONING`
      / `MODEL_BULK`, never the largest model at runtime; no model ids in the
      ADR). ADRs hold the "why"; existing docs keep the rule and link to the ADR
- [x] 2A `metrics_core.py`: revenue by period, MoM growth, orders, active
      customers, AOV, return rate. Tests with hand-calculated expected values.
      Zero denominators (`revenue_change_pct` with no previous revenue, `aov`
      and return rate with no orders) need a contract decision first: the 1.0
      contract requires a number there
- [x] 2B `metrics_customers.py`: RFM scoring + segment assignment (Champions,
      Loyal, At-risk, Hibernating, New). Tests
- [x] 2C `metrics_products.py`: Pareto concentration, top/bottom movers,
      velocity + stockout projection. Tests. `days_to_stockout` at zero
      velocity needs a contract decision first (same reason as 2A)
- [x] 2D Assemble `metrics.json` contract + `POST /api/runs/{id}/analyze`. Tests
- **DoD:** numbers in `metrics.json` verified by hand against the fixture data
  (met 2026-09-22: `by_dimension.category`'s contribution_pct formula reproduces
  both worked-example figures in docs/CONTRACTS.md section 6 exactly, UK 57.1%
  and Home Decor 41.4%, computed from core's own revenue_current/previous)

### Phase 3 - Stage 3 Diagnose

> Seven sessions, not three. The original 3A-3C plan (sequential substitution,
> the AI choosing which hypotheses to rule out) was replaced by the diagnostic
> engine in `docs/DIAGNOSE_DESIGN.md` - approved by Thach as the full engine,
> not the reduced MVP. 3A-3G below are sessions 1-7 of that file's section 11.
> Facts now live in `docs/CONTRACTS.md` section 7 and `docs/AI_PIPELINE.md`
> section 7; DIAGNOSE_DESIGN.md remains the record of *why*. Only 3F spends
> API credit.
>
> **Session order from here** (Thach, triaged after 3D5b; amended in 3E1):
> 3D4, 3D5, 3D5b (all committed together), then **3D6**, then **3D6b**, then
> **3E1**, then **2E**, then **3E1b**, then **3E2**, then **3D7**, then 3F,
> 3G (Thach, after 3E1). **2E first** because it corrects the orders
> definition B1 and B2 rest on (stage 2 counts return lines as orders -
> confirmed in `metrics_core._bucket`, so 2E keeps its full scope) and stage
> 2's partial previous month; calibrating 3E1b on the old definition and
> then changing it would mean calibrating twice. **3E1b before 3E2** because
> it carries FABRICATEs (asymmetry rule), and 3E2 measures a settled engine.
> 3E1b merges what 3E1 recorded as 3E1b and 3E1c: both change how D1 learns
> from history months with missing days, in the same function. **3D8 moves after 3E, low priority**
> (Thach, 3D6b): since ADR-0007 losing year-over-year mode loses only a
> descriptive row, so its effect is display only.
> **3D9 left the critical path** (Thach, after 3D6): instead of a further
> session tuning step 4, ADR-0007 made every step-4 row descriptive in v1 and
> moved the masked-shift alert onto the tree (session 3D6b). 3D9 is now part
> of the Backlog's "unusualness verdicts". The paragraph below is the record
> of how 3D9 had been triaged.
> **3D9 moved ahead of 3E by execution, not by reading** (Thach, 3D6): every
> known limit of 3D6's guard was run through the real pipeline to the
> headline and classified FABRICATE or SUPPRESS; any FABRICATE puts a session
> before 3E, SUPPRESS-only cases may follow it. Five cases fabricate, so 3D9
> is first. The table is on the 3D9 line.
> 3D6 moved ahead of 3E on evidence rather than caution: ADR-0006 made a
> year-over-year row a verdict, so a 12.50 base on a 50,000 shop is no longer
> a bad-looking figure but an actionable rule-1 finding that also fires the
> masked-shift alert with no hedge - a wrong verdict AND a wrong headline on a
> month where nothing happened. 3D7, 3D8 and 2E were run the same way and none
> of them can change a verdict or a headline 3E produces; each carries its
> reason on its own line.
> 3D5 comes before 3E because 3E is the verdicts, and a seasonal shop whose
> month genuinely halved currently produces no signal at all for its largest
> movement. 2E must precede 3F because 3F narrates figures that come from
> `metrics.json`, and `revenue_change_pct` is currently wrong for any shop
> with a negative previous period.
>
> **Commit grouping for the rest of Phase 3** (Thach, after 3D3): **3D4+3E**
> in one commit, **3F+3G** in the next. 3D3 was committed alone, because 3D4
> edits `signals.py` again and reroutes mode selection, so splitting them
> afterwards would not have been possible. The per-session scratchpad summary
> is written every session; the commit message is written once per group, at
> the end of its final session, organised by session.
>
> **Commit the signals work as its own group: 3D4 + 3D5 + 3D5b** (Thach,
> after 3D5b). It is a closed topic with its own ADR; 3E alone is large (the
> catalog, the headline rules, the S0-S11 generator) and grouping would pass
> the ~20-file bound; and if 3E goes wrong the way 3D2 did, this is a revert
> point with the signals policy intact. **Its message must tell the story
> straight** (Thach, after 3D5b): the level-chart gate was built in 3D5
> and then deleted in 3D5b by a policy decision, and the message says so
> rather than presenting the end state as if it were the plan. The reason
> belongs in it too - the gate's own best condition could not fire on a
> 24-month file, which is the project's reference length. A reader of
> `git log` should not have to open ADR-0006 to learn that a session's work
> was removed by the next one.
>
> **3D6 joins that group** (3D6, stated with the reason): the group was not
> yet committed when 3D6 ran, and 3D6 edits seven of its thirteen files
> (`signals.py`, `thresholds.py`, `contracts/diagnosis.py`, AI_PIPELINE,
> CONTRACTS, this plan, `test_yoy_base.py`), so it can neither stand alone
> nor join 3E without hunk-level staging - the 2A/2B situation. It is also
> the same topic: the magnitude half of 3D4's base guard. 14 files.
>
> **3D6b is committed ALONE** (Thach): a policy change with its own ADR is a
> coherent unit, and 3E is large enough on its own. The signals group was
> committed first (`a48009b`), so nothing overlaps.
>
> **Also frozen in this group: `docs/DIAGNOSE_DESIGN.md`** (Thach, after
> 3D5b). Its sections 5-9 are the historical design record as of 3A and carry
> a banner saying so, enforced by `tests/test_docs_single_source.py`. Twice a
> rule has lived in two catalogs and the copies drifted into opposite answers
> - C2's sign convention in 3C, the T3 rule in 3D5b - so a second live
> catalog is now a test failure rather than something to notice by eye.
>
> **Every remaining session runs BOTH a per-decision mutation check AND a
> doubt-review cycle** (Thach, after 3D). Neither substitutes for the other:
> they fail in opposite directions. A mutation check only mutates *code that
> exists*, so no mutant can represent an input nobody wrote a test for; a
> doubt-review reads for inputs but will not systematically probe whether each
> decision point is pinned. The evidence is 3D's own numbers: **19 mutants
> passed while all three criticals were live**, and in the same session the
> mutation check found three decision points the tests did not actually pin,
> which the review did not raise. Each technique found what the other could
> not. Budget both.

- [x] 3A SPECS UPDATE (docs only, no application code): CONTRACTS section 7
      rewritten to the 8-block `diagnosis.json`, AI_PIPELINE section 7 rewritten
      to the 8-step engine + threshold list, `prompts/root_cause.md` rewritten
      for narration only (+ the prompt test that never existed), this checklist
      split, ADR-0004 (Shapley) and ADR-0005 (pre-registered catalog)
- [x] 3B Foundations and checks: moved the shared transaction parsing
      (`ParsedTransactions`, `parse_transactions`, `require_column`,
      `pct_change`, `is_blank`, and - beyond the listed five - `normalize_text`
      and `product_identity`) from `stages/analyze/metrics_core.py` to
      `shared/transactions.py` so stage 3 never imports stage 2 (CLAUDE.md 3.1),
      plus `shared/contract_files.py` for the atomic write; then steps 1-4
      (frame, trust gate D1-D3, calendar, XmR signals) and `thresholds.py`.
      Stage 2 / stage 3 consistency test included: revenue, orders and active
      customers recomputed in stage 3 equal `metrics.json` exactly. All 1950
      stage 2 tests passed with no test file edited (`git diff -- tests/` empty).
      Doubt-review: 11 findings, 9 fixed here, 2 scheduled as 3D2
- [x] 3C Metric tree (AI_PIPELINE 7.6): Shapley levels 1 and 2 with the
      `orders*aov` fallback, masked-shift alert, customer bridge for both
      transitions, returns lens, product PVM, and `contracts/diagnosis.py`
      rewritten to CONTRACTS section 7 (closing 3A's time-boxed divergence).
      Every decomposition reconciles to its own total at 1e-9 - now enforced
      **at runtime** in `tree.py`, not only by tests. Doubt-review: 11
      findings, 2 critical, all fixed
- [x] 3C2 Normalize customer identity in BOTH stages (**prerequisite of 3D**,
      Thach, after the 3C doubt-review). `product_identity` has stripped and
      case-folded since 2C, but customer keys are grouped raw in stage 2 and
      stage 3 alike. Reproduced in 3C: one customer spelled three ways, buying
      100 in each month, reads as `new=200 / lapsed=-200` - total churn plus
      total acquisition in a flat month, which corrupts the C hypotheses and
      can reach the headline. The asymmetry of the risk decides it: a false
      split fabricates that story from ordinary data entry, while a false
      merge needs two genuinely different ids differing only by case or
      whitespace, which is rare for POS codes. 3D localizes by customer type
      from the bridge, so it must not be built on raw keys.
      Spec: a shared `customer_identity` helper in `shared/transactions.py`
      (strip + casefold, like `normalize_text`), used by stage 2 (active
      customers, RFM, new vs returning) and stage 3; record as evidence how
      many raw customer values were merged by normalisation; the stage 2 /
      stage 3 consistency test must still pass; **any stage 2 test that
      changes must be listed with its reason, and none weakened**.
      Done: six call sites keyed on `customer_identity`, the merged count in
      the bridge evidence (not metrics.json, which would be a stage 2 contract
      change), and **no existing test changed at all** - the count went
      1992+51 -> 2056 purely by addition. Doubt-review: replaced by a
      call-site mutation check, which found two sites the new tests did not
      actually protect
- [x] 3D Localization (AI_PIPELINE 7.7): members, "Other" grouping, new and
      removed members, mix vs rate, breadth - `members.py`, `mix_rate.py`,
      `localization.py`, plus `numbers.py` for the relative zero guard three
      files had each rediscovered. Every dimension reconciles to its own total,
      tested per dimension. Doubt-review AND a per-decision mutation check:
      26 mutants all killed; the review found 3 criticals the mutants could
      not reach
- [x] 3D2 Step-change detection and re-baselining - **ATTEMPTED AND REVERTED.**
      The method did not work. What shipped instead is the separable half: the
      XmR spread now uses the median moving range, falling back to the average
      when the median is zero, which fixes 3B finding 3a (an outlier widening
      the limits until nothing can signal) and regresses nothing. Re-baselining
      went to the Backlog with the record of how it failed; rule 2 is reported
      but no longer acted on. **3D2 is no longer the 3E prerequisite - 3D3 is.**
- [x] 3D3 Make rule 1 reliable (was the prerequisite of 3E, Thach, after 3D2).
      Fixed all four pre-existing defects (C1b, R3, R4, R6 from 3D2's table),
      each written first as a failing test from the symptom: a minimum spread
      in the mode's own units, the margin reduced to floating-point residue
      only, rule 2 gated by that margin, and a fall back to level mode when
      the CURRENT month has no year-ago comparator. Its own doubt-review found
      three criticals in the first attempt - including a floor that silenced a
      2% drop on a high-volume shop - and one pre-existing contract violation
      in `lever.py`. **3E is unblocked.**
- [ ] 3D4 Year-over-year against a non-positive base (**prerequisite of 3E**,
      Thach, after 3D3). Two defects in `signals._as_yoy`, both pre-existing,
      both recorded with reproductions in section 12.
      * **Sign inversion.** `(current - previous) / previous` flips sign when
        the year-ago month is negative, and revenue is signed in this codebase
        (returns are negative-quantity rows since 2A; ADR-0004 rejected LMDI
        precisely because a period can net to zero or below). Reproduced: a
        shop whose month went from -100 to -200 - **twice the loss** - reports
        `value_cur = +100.0`, `signal = "above"`, `rule = 1`. The engine calls
        a doubling of losses an unusually good month, using the rule step 7
        acts on.
      * **Non-finite from a denormal.** A year-ago value of 5e-324 yields
        `inf`, which `pd.isna` admits; the `Signal` validator then raises and
        the stage aborts instead of degrading.
      Likely fix is one line - `previous.where(previous > 0)`, making
      year-over-year undefined against a non-positive base, which 3D3's
      current-comparator fallback already turns into level mode - but it
      reroutes mode selection, so it needs its own sweep: what happens to a
      file where many months are non-positive, and is falling back to level
      right for all eight series. Tests per symptom first, as in 3D3.
      Doubt-review: yes. Mutation check: yes.
- [x] 3D5 Decide whether the level chart is informative before falling back
      to it (**prerequisite of 3E**, Thach, after 3D4). Closed 2026-09-23,
      then **SUPERSEDED the same day by ADR-0006** (session 3D5b): the gate
      this session built was deleted and the policy moved instead. Read the
      ADR before this entry - what follows is the record of an attempt, not
      of the current design. What survives from it: the year-over-year base
      guard's companion fixes (`no_current_value`, `no_measurable_spread`)
      and the finding that killed the approach, that the seasonal-position
      condition cannot fire on a 24-month file.
      3D4 shipped option (a): a series records `mode_fallback` when it would
      have charted year over year but its current month had no usable
      comparator, and T3 may not call such a month routine. **That is NOT a
      fix and must not be read as one.** On the measured case - a seasonal
      shop whose January halved against a normal January, the two files
      differing only in one month twelve months earlier - the series reports
      `within` and **no series fires rule 1 anywhere in the run**. A real 50%
      collapse produces no signal; all that was bought is a refusal to call
      the month routine. That loss is why this is scheduled rather than
      parked.
      The cause is a collision between two correct fixes: 3D3's fallback to
      level (without which a shop shut last February reports
      `insufficient_history` on an 80% collapse) and 3D4's base guard (without
      which a negative comparator inverts the sign). Falling back is right
      when the level chart is informative and wrong when it is not, and on a
      seasonal shop it is not - the level limits span 7,587 to 105,282.
      Scope: decide, per series and per file, whether level mode can see what
      year-over-year would have seen, and report `insufficient_history` rather
      than a misleading `within` when it cannot. This needs a TUNED THRESHOLD
      and therefore its own sweep with a clean context: two tuned constants
      have been wrong in three sessions. Sweep first, state what it was tuned
      against, and include the cases that must still FIRE.
      Before 3E because 3E is the verdicts, and this file currently produces
      no verdict for its largest movement. Note for whoever takes it: the tree
      DOES see the change (-125,000 on that file), but it compares with the
      previous MONTH, so on a seasonal shop it cannot separate the collapse
      from the season - and T2, the hypothesis that would, divides by the same
      year-ago month and needs 3D4's base guard applied to it.
      Doubt-review: yes. Mutation check: yes.
      **SHIPPED.** A fallback happens only when the level chart can see a
      halving; otherwise the series reports `insufficient_history` with
      `insufficient_reason = "neither_chart_informative"`. The new field is
      kept SEPARATE from `mode_fallback` on purpose (Thach, 3D5): the first
      says the series has no chart at all, the second says it IS charted, on
      level, and can still fire rule 1. Do not merge them for tidiness -
      CONTRACTS section 7 states why.
      **The brief asked for a tuned threshold and a sweep. It did not need
      one, and saying so is the finding.** A drop of fraction X moves a month
      X*centre from the centre, so `half_width >= X * |centre|` IS "blind to a
      drop of X": the constant and the drop size are the same number.
      `LEVEL_BLIND_SHARE = 0.50` states a policy - the chart must be able to
      detect a halving - rather than approximating anything. The first sweep I
      ran scored that rule against "would a halving be visible", which is the
      same expression, and returned zero errors because it could not return
      anything else. **That table was circular and was retracted to Thach
      mid-session.**
      What IS measured is the consequence, and it is a genuine trade-off:
      across sixteen shapes run through `compute_signals` twice, 0.50 gives
      one thrown-away detection and zero certified collapses, 0.60 gives zero
      and two. 0.50 wins because the two costs differ in kind - a thrown-away
      detection says "cannot say" about a month it could have called, while a
      certified collapse says a halving was normal. After the doubt-review the
      thrown-away column is zero at every policy from 30% to 50%, because the
      gate refuses only silence - a chart that FIRES is kept however wide it
      is. 0.30 to 0.50 score identically on the shape set; the table does not
      pick between them and the policy does.
      **This still does not restore the alarm** - the refused series produces
      no signal for its largest movement, only an explicit refusal instead of
      a wrong verdict. The note under 3E about the tree and T2 still stands.
- [ ] 3D8 **Re-triaged (Thach, 3D6b): after 3E, low priority.** Since
      ADR-0007 losing year-over-year mode loses only a descriptive row, never
      a verdict, so 3D8's stated consequence below no longer holds - its
      effect is on display only.
      The year-over-year residue guard is anchored on the whole series'
      maximum (its own line, Thach, after 3D5b; found by that session's
      doubt-review, outside its scope).
      `_as_yoy` computes `scale = column.abs().max()` and calls
      `is_negligible(base, scale)` with `RECONCILE_REL_TOLERANCE` (1e-9), so
      ONE freak month voids every ordinary base in the file. Reproduced: 26
      months of revenue 100 charts `mode=yoy`; change one month to 1e12 and
      usable year-over-year points drop from 25 to 1, so revenue charts
      `mode=level signal=below`.
      It needs a magnitude ratio around 1e9, so it is unlikely on money - but
      **ADR-0006 made the consequence worse**, because losing year-over-year
      mode now means losing the verdict, and T3 is then permanently
      inconclusive for that file. The structural objection stands whatever the
      likelihood: a RECONCILIATION tolerance is being reused as a DATA
      threshold, and anchored on the series maximum rather than on the base's
      own neighbours.
      Scope: pick the right anchor (a local window, or the base's own
      magnitude) and the right constant, with a sweep. Overlaps 3D6 (how small
      a base stops being a usable denominator) and may merge with it - decide
      with Thach.
      **Triaged against 3E (after 3D5b): NOT a blocker.** Reproduced - 26
      months of revenue 100 charts `yoy` and `is_verdict=True`; change one
      month to 1e12 and it charts `level`, `is_verdict=False`. So it removes a
      verdict rather than inventing one, and T3 becomes `inconclusive`. That
      is the SAFE direction: the engine says "we could not tell" instead of
      making a claim. It also needs a magnitude ratio around 1e9. It degrades
      3E's coverage, never its correctness.
      Doubt-review: yes. Mutation check: yes.
- [ ] 3D7 `_fallback_reason` reports a third fact as one of two labels
      (its own line, Thach, after 3D5b; independent of ADR-0006, may run with
      2E or 3D6).
      `mode_fallback` distinguishes `no_year_ago_value` - documented as "the
      month is absent from the file, the shop was shut" - from
      `unusable_year_ago_base`. But `_fallback_reason` derives the first from
      `months_with_rows` intersected with `complete_months`
      (`inputs.py`), so a file starting 2011-01-15 with `current = 2012-01`
      reports "the shop was shut" for a month that has rows and was simply not
      fully covered. Three facts, two labels, and 3F narrates the wrong one.
      Scope: distinguish "no rows at all" from "rows but incomplete coverage",
      either as a third `mode_fallback` value or by fixing the derivation.
      Decide which with Thach before implementing - it is a contract change
      either way. Note that `monthly_series` charts an empty month as 0.0,
      which contradicts `inputs.py`'s own 3B finding 2 and is why the series
      value cannot answer this question.
      **Triaged against 3E (after 3D5b): NOT a blocker.** Since ADR-0006
      `mode_fallback` gates nothing - `mode` decides what is a verdict - and a
      grep of AI_PIPELINE, CONTRACTS and DIAGNOSE_DESIGN finds no decision
      rule that reads it. It reaches only 3F's wording, so it must land before
      3F and cannot change a verdict or a headline 3E produces.
      **Also (3D6 doubt-review):** a series pushed into level mode because
      refused BASELINE bases left fewer than eight points carries
      `mode_fallback = null`, and reads exactly like a shop with too little
      history. True since 3D4's sign test; 3D6's share makes it more common.
      A fourth fact for the same field. Reproduction: 24 months at 500, then
      12 at about 50,000, current 50,000 (3D6 scratchpad `review/r4.py`).
      Doubt-review: yes. Mutation check: yes.
- [x] 3E1 The catalog, verdicts and headline rules (Thach split 3E in two
      with a commit boundary). Closed 2026-09-24. The catalog is DEFINED ONCE
      AS DATA in `stages/diagnose/catalog.py`, and AI_PIPELINE 7.8's table is
      checked against it cell by cell. Verdicts by kind (term / expectation
      with the residual band / directional); D decided: under the alert a
      TERM's own split's gross, an expectation always |the change|, never
      the pair; statements rendered from the sign (ADR-0005 clarification);
      rules 1-7 with rule 3 dormant and rule 4 hedged beside the net change;
      ranking by fit; T2 behind the 3D4/3D6 base guard. Session log below.
      **Interim in place until 2E:** B1 and B2 are `inconclusive` when either
      month has a refund, because stage 2 AND stage 3 count a return line as
      an order (verified in `metrics_core._bucket`: `orders = int(mask.sum())`
      over every row). **Observed on the demo runs, not changed:** headline
      rule 5 (T2, "+7,284.95 against the change of +4,925.00", share 1.48)
      outranks the better-fitting B1 (0.96) by rule order; 3E2's suite
      measures whether that order is right.
      **Doubt-review cycle 3 found five FABRICATEs** (sub-threshold missing
      days credited to B1; a gapped history month hiding a gap; an export
      starting mid-month; a year-ago gap read as the season; rule 6 naming a
      price rise as the cause of a fall) plus C4 reading rows after the
      period and four wording defects. All fixed by Thach's decisions, with a
      fourth cycle scoped to the fixes (Thach's stop rule: a critical there
      that is not a small local fix splits the remainder into 3E1c - since
      merged into 3E1b). **Cycle
      4** found two criticals, both small and local, fixed without a fifth
      cycle: a previous month with no sale in a file WITH history only
      cautioned (a product sold for eleven months headlined as "launched");
      the leading-days count keyed on the first row of any kind (a stock-in
      row hid a missing month). Also fixed: rule 6 on an exactly-zero change,
      a false D1 message, CONTRACTS drift. Its non-local High and Medium went
      to 3E1c (now part of 3E1b). **Known limits, accepted for v1 by Thach:**
      B1 is refused on 28 of 40 sparse shops and T2 on 30-32 of 40 (any
      zero-sale day beyond the learned pattern), both kept on the two demo
      runs; 3E2 reports them. C4 is `inconclusive` in v1 (Backlog).
- [ ] 3E1b **How D1 learns from history, and rule 6's size test** (one
      session; Thach, after 3E1: runs after 2E, before 3E2). Merges the two
      items 3E1 recorded as 3E1b and 3E1c. Parts A and B change the same code
      - `trust.d1_coverage`'s learning set and its caution threshold - and
      are decided by the same measurement (sparse, seasonal and half-gapped
      shops together), so splitting them would calibrate one rule twice.
      Part C is independent code (`headline.py`) and is here, not in 3E2,
      because 3E2 measures the headline and must measure a settled rule.
      Parts B and C need their own doubt-review scope. Since 3E2 now comes
      after, the measurements use the hand-built sweeps from 3E1's
      scratchpad (sparse r5b, seasonal, review9 r6/r7), and 3E2 re-checks on
      the generator. Re-measure B1's and T2's refusal rates afterwards: both
      read D1's learned pattern.
      **A. D1's check false-cautions on sparse and seasonal shops - a
      FABRICATE** (found in 3E1). With NO missing data, the D1
      check cautions on 11-12 of 40 sparse shops (6 on the current month,
      5-6 on the previous one), and because D1 now follows its check, D1 is
      supported and **headline rule 2 ("consistent with missing days of
      data") fires on 6-7 of 40**. The cause is the check's absolute
      `D1_CAUTION_DAYS` = 3: in a shop that trades a few days a week, three
      excess zero days is ordinary variation, not a gap. Tying D1 to its
      check (Thach, 3E1) cut the headline rate from 17-24 of 40 but cannot
      reach below the check. By the asymmetry rule a FABRICATE blocks; the
      candidate direction is a threshold scaled to the shop's own zero-day
      variability, measured on the 3E2 generator's sparse shapes.
      **Seasonal shops too (measured in 3E1 cycle 3):** on seasonal shops with
      NOTHING missing (daily Apr-Sep, 1-5 trading days a month off-season),
      D1 flags 61 of 120 current months - essentially every off-season month -
      because it learns one weekday pattern for the whole year. The 3E1
      learning exclusion (`D1_LEARN_MIN_ACTIVE_SHARE`) does not create this
      but turns 33 of those cautions into blocks (rule 1: 7 -> 40 of 120;
      rule 2: 9 -> 14). Wording since 3E1 names closures, so the rule-2
      sentence ("days with no sales - missing data, or days the shop was
      closed") is literally true of an off-season month, but a seasonal
      decline is not diagnosed as seasonal. Same item: D1 needs a notion of
      the shop's season before its absence-of-sales reading is a finding.
      **B. A half-gapped history month still hides a gap (FABRICATE)** (3E1
      doubt-review cycle 4, split out under Thach's stop rule rather than
      patched at cycle 4).
         `D1_LEARN_MIN_ACTIVE_SHARE` drops a history month only below half
         the history's median active days. With history {30, 17} active days
         (median 23.5, floor 11.75) a December missing 14 days is still
         learned from; D1 then expects 6.7 zero days in a February missing 6,
         reads `ok` with 0.0 excess, B1 is not refused, and rule 6 says
         "customers bought less often (lever lens, 100% of the change)" for
         930 -> 690. Also with December missing 15 and February 7. Near
         misses (excess 0.33; 2.57 with 3 of 8 months half-gapped) refuse B1
         but leave D1 `ok`, so the missing week (78% of the change) is never
         named - SUPPRESS. The same learned rates feed T2's year-ago check
         (not reproduced). Reproductions: scratchpad `review9/r6`, `r7`.
         Direction: learning needs a robust per-month test against the
         weekday pattern (e.g. leave-one-out), not a floor on active days;
         measure against part A's sparse and seasonal shapes together, since
         the same rule decides both.
      **C. Rule 6 checks the sign, not the size (misleading, not false).**
         Prices 10 -> 12 (+62 of gross) and a 60.00 refund: net +2, and the
         headline names "like-for-like prices changed (100% of the change in
         gross sales (+62.00))" while the refund that cancelled 97% of it is
         `ruled_out` for having the opposite sign. Every printed number is
         true. A design decision: bound a product-lens cause's
         `|contribution / net|` for the headline, or name the offset.
- [ ] 3E2 Hypotheses and scenarios (AI_PIPELINE 7.8 and 7.11): the
      fixed-seed scenario generator and the
      S0-S11 suite with its acceptance criteria - including **S11, the
      6-month truncated build**, whose headline must NOT be rule 3 (normal
      variation). Doubt-review: yes.
      **Since ADR-0007 (3D6b):** T3 is always `inconclusive` and headline
      rule 3 is dormant; **S0 and S11 both expect headline rule 7 with zero
      `supported` hypotheses** (AI_PIPELINE 7.11). **In scope, explicitly:
      re-run the `MASKED_MIN_CONTRIBUTION_SHARE` sweep against the real
      S0-S11 suite** - S6 (masked shift) must fire; S0 and S11 must not
      (their expected headline is rule 7); S9's expected headline stays rule
      5, and whether rule 4 displaces it is MEASURED, not assumed, since a
      seasonal mix shift can clear the floor by design - and the value is
      ALLOWED TO CHANGE. It was tuned on hand-built shapes
      in 3D6b because the generator did not exist; planted causes are ground
      truth only once the generator exists and was not built to fit it. Also
      report S9's rule-4 rate as a finding either way. **Also measure**
      (3D6b doubt-review cycle 2) which split 7.8's D uses when the alert
      is on - level 1's gross or the pair's; they differ up to 3x (level-1
      2,406.7 against the pair's 800 on one S6-like case) and every share
      moves with it - and how often an alert that fires dilutes
      7.8's shares below SUPPORTED_MIN_SHARE, since D becomes the gross,
      which exceeds three times the change whenever the alert is on.
      **3E1 decided D** (level 1's gross for B1, never the pair's; terms
      only); 3E2 still measures the dilution. **Also in 3E2** (Thach, 3E1):
      decide what happens to the known-limit tests pinned in 3D6 now that no
      signal is a verdict; **report the accepted v1 known limits** (Thach,
      after 3E1) as their own rows, re-measured on the engine as it stands
      after 3E1b and on the generator's shapes: B1 refused on 28 of 40 sparse
      shops and T2 on 30-32 of 40 at 3E1, both kept on the two demo runs; build the generator so it cannot be fitted to the
      engine (causes planted by construction from the scenario spec, never by
      inspecting engine output) and state how; runs AFTER 2E.
      **Also the trigger for the Figma Insights frame** (trust badge,
      hypothesis list with verdict labels): the shapes those need are final
      only once this session lands (Thach, 3A). The "normal-variation" state
      is DORMANT in v1 (ADR-0007) - design the rule-7 "no single tested cause"
      state instead.
- [ ] 2E Percentage change against a non-positive base, in STAGE 2
      (**must land before 3F**, Thach, after 3D4), **and the orders
      definition (moved ahead of 3E2, Thach, 3E1).** Stage 2 counts a
      return line as an order (`metrics_core._bucket`: `orders =
      int(mask.sum())` over all rows, returns included), and stage 3's tree
      matches it, so a month with refunds shows fewer units per order and a
      lower purchase frequency. Count only sale rows as orders in BOTH
      stages; the stage 2 / stage 3 consistency test ties them, so they move
      together. Then remove the B1/B2 returns interim in
      `hypothesis_evidence._returns_in_either_period` and its tests.
      **Also an incomplete previous period in stage 2** (Thach, 3E1 cycle 3).
      Stage 3 now blocks when the file starts partway through (or after) the
      previous month (`frame.previous_leading_days_missing`, AI_PIPELINE
      7.2), but stage 2 compares the same partial month, so
      `revenue_change_pct` and every period-over-period KPI on the Insights
      page are wrong for such a file. Stage 2 must detect an incomplete
      previous period and report the comparison as unavailable rather than a
      percentage, with the same advice: re-export from the 1st of the
      previous month. `shared/transactions.py`'s
      `pct_change` guards with `if previous else 0.0` - non-zero, not
      positive - so it inverts exactly as `_as_yoy` did before 3D4. This is
      the more serious instance, because it reaches the figures rather than
      only the verdicts, and 3F narrates figures that come from
      `metrics.json`. Verified:

          pct_change(-200, -100) = +100%    a doubled loss, as growth
          pct_change(500,  -100) = -600%    a recovery, as a collapse
          pct_change(1000, 1.39e-17) = 7.2e21%

      Two places it lands, both worked through:
      * `metrics_core.py` - `revenue_change_pct`, the headline KPI the whole
        report is built around. A shop whose month went from -100 to -200
        gets `revenue_change_pct = +100.0` written into `metrics.json`, and
        every later stage reads that number as growth.
      * `metrics_products.py` `_biggest_decliners` computes `pct_change` per
        product and keeps those with `change < 0`. So a product whose loss
        DOUBLED (-100 -> -200) scores +100 and is **dropped from the
        decliners list**, while a product RECOVERING (-100 -> +500) scores
        -600 and is **reported as the biggest decliner**. The list is
        inverted for any product with a negative previous period.
      **Triaged against 3E (after 3D5b): NOT a blocker; the existing
      before-3F schedule is right.** Stage 3 reads exactly three things from
      `metrics.json` - `period`, `core.revenue_current` and
      `core.revenue_previous` - grepped across `stages/diagnose/`, not
      assumed. `revenue_change_pct` and `products.biggest_decliners`, the two
      fields the defect lands in, are not among them, so no verdict, share or
      headline 3E computes can carry the inverted figure. 3F narrates from
      `metrics.json` directly, which is where it bites.
      **Fixing this changes values in `metrics.json`**, so the stage 2 /
      stage 3 consistency test is the thing that proves both stages moved
      together rather than one silently drifting. Expect stage 2 expectations
      to move; list every one with its recomputed derivation, as 3D3 did.
      Doubt-review: yes. Mutation check: yes.
- [x] 3D6 How small a base stops being a usable denominator
      (**BLOCKS 3E - runs immediately before it**, Thach, triaged after 3D5b;
      was "may run with 2E, before 3F").
      **Why it moved.** ADR-0006 made a year-over-year row a VERDICT, so this
      stopped being a cosmetic figure and became an actionable finding.
      Reproduced on a shop at 50,000 a month whose year-ago month was 12.50,
      with the current month back at an ordinary 50,000:

          revenue          yoy above rule=1   +399,900 %   is_actionable=True
          aov              yoy above rule=1   +399,900 %   is_actionable=True
          units_per_order  yoy above rule=1   +399,900 %   is_actionable=True
          masked_shift_alert=True  basis=yoy  gross_to_net=None

      `aov` is a level-1 factor, so the masked-shift alert fires on it - and
      with `basis=yoy` 3F states it WITHOUT the seasonal hedge. So **headline
      rule 4 speaks, as a finding, on a month that went 50,000 to 50,000 and
      in which nothing happened**, while T3 is ruled out by the same fake
      signals. A verdict and a headline, both wrong, both from one small
      month a year earlier.
      3D4 closed the residue half - `is_negligible` against the series' own
      scale - and left the magnitude half open: a base of 12.50 on a shop
      turning over 50,000 still passes and yields 406,300%, which then drags
      the mean centre and leaves every ordinary month firing. Closing it needs
      a BUSINESS threshold (how small a month stops being a valid
      denominator), and two tuned constants have been wrong in three sessions,
      so it gets its own sweep rather than a number chosen at the end of a
      long session (Thach, 3D4). Sweep first, state what it was tuned
      against, and include the cases that must still FIRE. The cases that
      must still fire now include a REAL 4,000% recovery - a shop that
      genuinely was tiny a year ago - because the threshold must separate "too
      small to divide by" from "small and the growth is real".
      Doubt-review: yes. Mutation check: yes.
      **CLOSED 2026-09-23 as a NARROW fix** (Thach chose it after two
      doubt-review cycles). A base is refused below `YOY_MIN_BASE_SHARE =
      0.03` of the series' typical magnitude - the median of |value| over the
      TRADING (non-zero) months of the history window. It removes the
      reproduction and the absurd end, and nothing else; what it cannot reach
      is 3D9, which now blocks 3E.
      * **The constant is a policy.** A base at fraction f is refused iff f <
        0.03, so any sweep of bases scored against it is circular (3D5's
        lesson), and the exclusion side has no edge: a comparator at HALF
        normal already fires an actionable +100% on an ordinary month. What
        was measured is the ceiling, from bases small AND real: a recovery
        after a slump of exactly half the window sits at 4.76% of its median
        and is lost from 0.045 at 5% noise, 0.035 at 20%, 0.03 at 30% (1 in
        80 seeds). Between 0.025 and 0.03 nothing separates them below 30%
        noise, so the asymmetry picks the one that refuses more.
      * **Rejected on evidence:** a cap on the result (drops a real +9,900%
        jump by construction); windows centred on the base (a nine-month
        closure passes them and fabricates); a mean yardstick (one freak month
        voids every base); the whole file as window (a shop that shrank long
        ago is judged against its past).
      * **Doubt-review cycle 1** found the first version inert on a stall
        shut most of the year (median 0, floor 0, +399,900% unchanged) - fixed
        by the trading-month median; that refusing a BASELINE base is NOT the
        safe direction (a growing off-season shop's ordinary January became
        an actionable `above`) - documented, not fixable by a share; and a
        `mode_fallback = null` for series eroded into level mode - moved to
        3D7. **Cycle 2** found the three families below, and two claims of
        mine false (the residue check "implied", the NaN branch
        "unreachable"). Both corrected, the first now pinned.
- [x] 3D6b ADR-0007: no step-4 row is a verdict in v1; the masked-shift
      alert rests on the tree (Thach, after 3D6). Closed 2026-09-23.
      `is_verdict` returns False, T3 is never `supported`, headline rule 3 is
      dormant, S0/S11 expect rule 7. The alert: against a floor of
      `MASKED_MIN_CONTRIBUTION_SHARE` (0.20, PROVISIONAL) times the largest
      of the typical month, last month and this month, one contribution of
      each sign ON THE ORDERS x AOV PAIR (new field `masked_shift_pair`)
      clears it, the revenue change stays under 20% of the larger compared
      month, and the three-factor `gross_to_net` reaches 3;
      `masked_shift_basis` removed; rule 4 always hedged. 3D4 and 3D6 guards
      kept for display. **Measured cost** (the rule as shipped,
      final_sweep.out): with nothing planted the alert fires 2.0-2.4% at
      realistic noise, 5.0-6.2% at 30/15/15, about 0 at 0.3x typical - a
      true statement in hedged wording, so it misleads by emphasis, not by
      fabrication. Deciding materiality on the three-factor split instead
      fired on 19-39% of months with stable orders and a swinging customer
      count - customers x frequency = orders, an identity - and was fixed
      before the commit by moving it onto orders x AOV (Thach): 0-2.4%; S6
      identical without noise, 0.2-1.8 points lower with it. Its own
      doubt-review then found the change bound measured against the floor
      calling a -75% trough month flat - now measured against the compared
      months. The floor as first
      decided (typical month alone) fired on 15-25% of peak months; the
      doubt-review measured it and Thach chose the max. Also guarded: a
      compared month netting zero or below gives a null alert with a reason
      (the Shapley terms change sign there).
      Doubt-review: yes. Mutation check: yes.
- [ ] ~~3D9~~ **MOVED TO THE BACKLOG** by ADR-0007 (Thach, after 3D6) - see
      "Unusualness verdicts" there. Kept here as the record of its triage.
      Base effects the 3D6 share cannot reach (was: BLOCKS 3E, Thach, 3D6,
      by execution: rule below).
      Triage rule (Thach): run each case to the headline; FABRICATE = an
      actionable rule-1 verdict or an unhedged headline the data does not
      support; SUPPRESS = a supported verdict removed or silenced. Any
      FABRICATE puts this before 3E. Run on the real pipeline
      (`run_data` -> `compute_signals` -> `compute_lever`), share 0 vs 0.03;
      script: 3D6 scratchpad `triage.py`.

      | case | shape | result, 3D6 | class |
      |---|---|---|---|
      | L1 | open Jun-Sep at 50,000, 300/month otherwise; year-ago June 12.50; June ordinary | revenue, aov, upo `above` +400,300%, actionable; unchanged by 3D6 | FABRICATE |
      | L2 | off-season 2,000 (7 months); year-ago June 100 | +49,950% actionable x3 | FABRICATE |
      | L3 | flat ripple at 50,000, 2010-06 at 3.5 / 5 / 10 / 25% of normal, current -0.5% | `below` rule 1 actionable x3, all four shares, before AND after 3D6 | FABRICATE (predates 3D6) |
      | L4 | off-season Jan-Jun growing 500 -> 1,000 -> 1,500, +-20% seeded noise, January +91% (reviewer's `review/r3.py`) | `within` -> `above` actionable: CREATED by 3D6 refusing six genuine off-season bases | FABRICATE (3D6) |
      | L5 | 12-month slump at 700 or 500, or 11 months at 700 and second recovery month | real recovery goes to level; not actionable; alert basis yoy -> level | SUPPRESS |
      | L6 | 3-month trough at 1.5% of normal, July halved | real halving goes to level | SUPPRESS |
      | L7 | 2011-03 at 12.50 as a year-over-year NUMERATOR, current ordinary | `above` actionable x3 (mean centre pulled to about -8 points) | FABRICATE (predates 3D6; measured ~13% of seeds vs 2.5% control) |

      No case fires the masked-shift alert with `basis = yoy` on a month
      where nothing happened; headline rule 4 is reached through the
      actionable rows, which feed the alert whenever revenue moves.
      L1, L3 and L5 are pinned as KNOWN LIMITS in `test_yoy_small_base.py`,
      asserting today's defective behaviour, so the fix fails them visibly.
      * **Candidate method, not a decision** (Thach): a robust centre in yoy
        mode (median rather than mean), which would absorb one anomalous base
        OR numerator point (L3, L4, L7 together). 3D2's reason for reverting
        a median centre was a level-mode problem - in yoy mode seasonality is
        already differenced out - so it does not carry over directly, but it
        needs its own sweep, including the cases that must still FIRE. L1/L2
        (the yardstick set by an off-season) likely need a separate idea.
      * **Rejected, with the reason** (Thach): making a yoy verdict
        actionable only when the level chart agrees. ADR-0006 exists because
        the level chart is uninformative on seasonal series, so that would
        silence year-over-year exactly where it is the only informative chart
        - the C1 case in reverse.
      Doubt-review: yes. Mutation check: yes.
- [ ] 3F AI narration (AI_PIPELINE 7.9): the narration call, the number/id/
      not-tested validator, degraded mode, one real API check (a few cents - the
      only session in Phase 3 that spends credit). Doubt-review: yes
- [ ] 3G Assembly and endpoint: full `diagnosis.json` written atomically,
      `POST /api/runs/{id}/diagnose`, state machine. Decide then whether a
      `diagnosed` status is added (Alembic migration) or `analyzed` + the file's
      existence is enough - note `analyzed` needed no migration in 2D because
      every status including `imported` was already in the first migration's
      CHECK constraint, so check there before assuming one is needed.
      Doubt-review: optional
- **DoD:** the S0-S11 planted-cause suite passes its acceptance criteria - every
  scenario produces its expected headline or verdict, S0 produces zero
  `supported` hypotheses, S11 produces no `supported` hypothesis and does not
  use headline rule 3, and the whole suite produces at most one `supported`
  hypothesis not implied by its planted cause. Headline accuracy, decoy count
  and false-alarm count are printed by the tests and quoted in the README

### Phase 4 - Stage 4 Predict
- [ ] 4A `forecast.py`: interpretable forecast (rolling/weighted trend +
      seasonality index) for revenue and per-product demand, with confidence
      intervals and an explicit "insufficient history" path. Tests
- [ ] 4B `ai_strategy.py`: AI turns metrics + diagnosis + forecast into ranked
      recommendations, each with insight, cause, action, expected impact
      (arithmetic shown), how to measure. Validated. Decide whether stage 4
      calls the AI when `diagnosis.json` has `ai_findings: null`. Tests with
      mocked AI
- [ ] 4C Assemble `forecast.json` + `POST /api/runs/{id}/predict`. Tests
- **DoD:** every recommendation cites a number that exists in the inputs; a
  manual review finds no fabricated figures

### Phase 5 - Stage 5 Report
- [ ] 5A `builder.py`: assemble `report.json` (3 layers: numbers, causes,
      actions) from all prior contracts. Tests. First define the layer
      structure in CONTRACTS section 9 (today `dict[str, Any]`), including
      how a `null` AI block shows as "unavailable" (AI_PIPELINE section 9) and
      where `provenance.ai_calls` is traced from
- [ ] 5B `html_report.py`: self-contained HTML with embedded Plotly charts;
      downloadable. Tests on structure, not pixels, including AI text escaped
      (SPECS SEC-3). Owner of the open decision to extend SEC-3 to text taken
      from the uploaded CSV (column names, product/category values): update
      SPECS first, then 5B and the Phase 6 screens follow it
- [ ] 5C `POST /api/runs/{id}/report` + download endpoints. Tests
- [ ] 5D `python -m stages.report --run <id>` CLI path verified (proves stage
      independence). Decide how a stage CLI gets the runs root without
      importing the backend (SEC-4), e.g. a `--runs-dir` argument (no stage
      has a CLI yet as of 1B)
- **DoD:** the HTML report is readable standalone and matches the contract data

### Phase 6 - Frontend
> Not started. A scoped, deliberate exception pulled 3 of these screens (Upload,
> Review, Results - the Stage 1 screens, whose backend was already built and
> manually verified) forward into their own session, ahead of phase order and
> without the Wave 3 skills. Insights (6E) and Dashboard (6F) still wait for
> Phase 2-5, whose data they need. Full account in section 12 Notes, dated
> 2026-09-22.
- [ ] Install skills Wave 3 (see docs/SKILLS.md)
- [ ] 6A Upload page + analyzing states (SPECS 4.1); decide how the
      client-side size check learns `MAX_UPLOAD_MB` without a second source of
      truth for the limit
- [ ] 6B Review screen part 1: column table with editable type / mapping / action
      (AI rationale rendered escaped, SPECS SEC-3). Issue examples are AI text
      of unknown shape (a real call returned the string "null"): render them
      as given, escaped, without assuming they are row references
- [ ] 6C Review screen part 2: before/after preview + confirm/cancel/reset
- [ ] 6D Results page: cleaning summary + downloads
- [ ] 6E Insights page: KPI cards, diagnosis panel, recommendations list (AI
      text rendered escaped, SPECS SEC-3)
- [ ] 6F Dashboard page: charts + low-stock table + report download
- **DoD:** a non-technical user completes upload -> report without instructions

### Phase 7 - Import and Persistence
- [ ] 7A Alembic migrations for `products`, `transactions` (`runs` is done in
      1A2)
- [ ] 7B Import service: approved clean data -> canonical tables, upsert by
      SKU/name, import summary with skipped rows and reasons. Tests
- [ ] 7C Dashboard endpoints read from DB (not from run files). Tests
- **DoD:** dashboard numbers match the source file, hand-checked

### Phase 8 - Hardening
- [ ] 8A Edge cases from SPECS section 10 (empty, header-only, non-UTF8, wrong
      delimiter, all-null column, non-inventory data, `MAX_UPLOAD_MB` boundary);
      duplicate header names (pandas renames the second `a` to `a.1`, so the
      review screen would show a name that is not in the file); a pathological
      header (e.g. a 1 MB column name), which 1C cannot cut because the AI's
      answer must repeat names exactly; a limit on (or a warning about) the number of
      columns: a file of hundreds of columns makes the preview slow and the AI sees 25
      (left here by Thach at the end of 1F)
- [ ] 8B Abuse guards: rate limits on uploads (SPECS section 11 abuse guards)
      and on every AI endpoint (SEC-2), each from its own required env var;
      a request-body size limit so an oversized upload is refused before it
      is fully received (today 1A returns 413 only after python-multipart has
      spooled the whole body); the retention cleanup also deletes run
      directories that have no `runs` row (left by a commit with an unknown
      outcome, see 1A2);
      the run-state transition for a rate-limited AI step (SEC-2); the
      trusted-proxy setting that yields the client IP (SEC-2; 9A sets the
      Render value); AI call budget per run (1G added a per-run, per-step attempt cap,
      `RunWork`, RATE_LIMITED after 3; SEC-2's IP-based limit is still open); retention
      cleanup job (also frees a run 1G's `load_live_run` never touched, and reads
      `RunWork`/`FrameCache`/`RetryBudgets` for one process only - 8B decides what
      changes if the backend ever runs more than one); startup `ALLOWED_ORIGINS`
      checks per SEC-5; `DATABASE_URL` handled as a secret so it never reaches logs
      (SEC-4)
- [ ] 8C Test sweep + coverage review on `stages/` and `backend/app/services/`
- **DoD:** every hostile input fails gracefully with the specified message

### Phase 9 - Deploy and Documentation
- [ ] Install skills Wave 4 (see docs/SKILLS.md)
- [ ] 9A Deploy API + Postgres to Render; env vars + CORS for the real domain,
      including origins with a trailing slash and Vercel preview domains
- [ ] 9B Deploy frontend to Vercel; production smoke test
- [ ] 9C README: problem, architecture diagram, stage contracts, AI design
      decisions, local setup, demo link, screenshots
- [ ] 9D "What I learned" section for interviews
- **DoD:** public demo link works; README understandable in 2 minutes

### Backlog (never start without explicit approval)
Auth/accounts, XLSX input, multi-file merge, scheduled re-runs, PDF export,
comparing two runs, email delivery of reports, mobile layout.

**Period-anchored customer segments, for C4** (3E1 doubt-review cycle 3).
C4 is `inconclusive` in v1 behind `SEGMENTS_ANCHORED_TO_THE_PERIOD` in
`hypothesis_evidence_customers.py`. Stage 2's segment counts are a snapshot
anchored at `data_end + 1` over every row, including the partial month after
the current one (`metrics_customers.py`), while the previous snapshot is
anchored at the previous month's end: the same January came out `ruled_out`
or "migrated to weaker segments", `supported`, depending on who bought on
2-10 February. Needs a snapshot at the end of each compared month. Second
defect to fix at the same time: R is scored by quintile rank, so R <= 2 is
always about 40% of customers and C4's "weak" half (At-risk + Hibernating
share) cannot move - `weak_share_change_points` was 0.0 in every run.

**Unusualness verdicts** (replaces 3D9; ADR-0007). Letting a step-4 row be a
verdict again - so T3 can be `supported` and headline rule 3 can speak -
needs BOTH:
1. a comparator of **at least three prior years** of the same calendar month,
   compared against their median, so one anomalous year cannot fabricate a
   verdict; and
2. a **robust centre** (a median, not a mean), because L7 - one tiny month
   as a year-over-year NUMERATOR - fabricates under ANY comparator scheme:
   it lives in the centre.
With eight baseline points each needing three lags, a file needs
`36 + 8 + 1 = 45` complete months. **No current demo dataset reaches it:**
the Kaggle set is about 36 months, Online Retail II about 24. Needs its own
sweep, including the cases that must still FIRE, and must flip the known-limit
tests in `test_yoy_small_base.py` (L1, L3, L5) before it switches verdicts on.
**Do not re-propose a two-year median** (Thach proposed it after 3D6 and it
was rejected on arithmetic): the median of two values is their mean, so it
halves an anomalous year instead of ignoring it - L1 becomes (50,000 +
12.50) / 2 = 25,006 and an ordinary June still reads +99.95%. A median
centre in year-over-year mode is a candidate for item 2: 3D2's reason for
reverting a median centre was a LEVEL-mode problem, and in year-over-year mode
seasonality is already differenced out, so it does not carry over directly -
but it needs its own sweep. Rejected with its reason: requiring the level
chart to agree (ADR-0006 exists because that chart is uninformative on
seasonal series).

**Step-change detection and re-baselining for the XmR signals.** Attempted in
session 3D2 and reverted. A later attempt should start from how this one
failed, not from the proposal, so the record is here rather than only in the
session notes.

The method was: a step change is **persistent** (the post-split median differs
from the pre-split median by >= 2 process sigmas), **abrupt** (>= half the
shift arrives in one month) and a **level** (the post-split segment's two
halves have similar medians). It was paired with a median CENTRE as well as a
median spread. Four ways it broke, each reproduced:

- **Multi-month seasons.** The persistence argument - "a spike reverts, so the
  months after it pull the median back" - holds only for a ONE-month peak. A
  two-month promotion moves the pre-split median; a four-month season fires at
  every offset. 40 of 72 swept seasonal shapes produced a step change, so the
  series reported `insufficient_history` through every peak season: the engine
  goes blind exactly when the user is looking. November plus December is the
  canonical retail peak and it is two months.
- **A business that steps twice.** With two passing splits, "largest shift"
  picks the earlier one and re-baselines onto a level the business has already
  left. The right rule is almost certainly the LATEST passing split, since the
  question is which level the business is on now.
- **Year-over-year mode.** Detection ran on whichever series was being
  charted, so in YoY mode it found the month the ratio reverts - twelve months
  after the business actually moved - and then discarded the twelve months
  that describe the new level. Detection has to run on the level series and be
  mapped across.
- **A real step it cannot see.** A shop that went from an alternating 60/100
  to a steady ~120 and stayed is silent: the median centre absorbs the shift
  and the abruptness test fails because the OLD process was volatile.

Also: the abruptness test compared adjacent POINTS rather than adjacent
months, so a data gap satisfied it; and the zero-sigma branch used
`RECONCILE_REL_TOLERANCE` (a float-residue tolerance) as a business
significance threshold, making a one-cent price rise a step change.

## 6. Working with Claude Code on This Project

- One sub-phase per session, in order. No skipping, no bundling.
- Read `CLAUDE.md` + section 12 of this file at the start of every session.
- Every function in `stages/` or `backend/app/services/` gets a test the same
  session, not later.
- AI calls are ALWAYS mocked in tests. Never spend real tokens in the test suite.
- Commits: `feat:` / `fix:` / `test:` / `docs:` / `refactor:`
- Feature outside the checklist? Stop and ask Thach.
- Explain decisions to Thach in Vietnamese in chat; all files, code, comments and
  commits stay in English.
- **Mandatory every session:** before ending the turn, edit THIS file with the
  file-editing tool: tick completed items, rewrite section 12 (phase in progress,
  concrete next step, Notes). Overwrite stale notes, don't append forever.

## 7. Model Usage Policy

- Development (Claude Code): Sonnet 5 by default; Opus 5 only for hard debugging
  or architecture decisions.
- Runtime: `claude-sonnet-5` for schema inference, cleaning plan, root cause and
  strategy; `claude-haiku-4-5` for cheap bulk tasks. Model ids from config only.
- Budget: max 4 AI calls per run (1 per AI step) + 1 shared retry.
- Full policy (why two settings, not a hardcoded id; why never the largest
  model at runtime) and the trade-offs accepted:
  `docs/adr/0003-model-selection-policy.md`.

## 12. Current Status

**Phase in progress:** Phase 3 (Stage 3 Diagnose), session **3E1** closed
2026-09-24: **the hypothesis catalog, verdicts and headline rules.** The
catalog is defined once as data (`stages/diagnose/catalog.py`) and
AI_PIPELINE 7.8's table is tested against it cell by cell. Verdicts by kind
(term, expectation with the residual band, directional); D decided (a term's
own split's gross under the alert, never the pair; an expectation always
|the change|); statements rendered from the data's direction (ADR-0005
clarification); rules 1-7 with rule 3 dormant and rule 4 hedged; ranking by
fit. Four doubt-review cycles, the last one beyond the bound by Thach's
approval with a stop rule: cycles 1-3 found fabrications that were all
fixed; cycle 4's two criticals were small and local and are fixed, and its
non-local FABRICATE (a half-gapped history month still hides a gap) is
**3E1c** (since merged into 3E1b), not patched. The measured costs are stated, not hidden: B1 is
refused on 28 of 40 sparse shops and T2 on 30-32 of 40; D1 flags 61 of 120
off-season months of seasonal shops with nothing missing (3E1b). pytest 2347
passed.
Previously, session **3D6b** closed
2026-09-23: **ADR-0007 - no step-4 row is a verdict in v1.** Thach's call
after 3D6, whose triage found five fabricating cases from two root causes -
one year-ago comparator that cannot vouch for itself, and a mean centre one
anomalous point drags. `is_verdict` returns False, T3 is never supported,
headline rule 3 is dormant, and S0/S11 now expect rule 7. The engine's claim
changes from "nothing unusual happened" to "it never invents a cause when no
hypothesis is supported". The masked-shift alert moved onto the tree: against
a floor of 20% of the largest of the typical month, last month and this month,
one contribution of each sign on orders x AOV clears it, and the revenue
change stays under 20% of the larger compared month. It works on any file
with one complete trading month in its history, and is
always worded as possibly seasonal. Its floor scales with the months compared
- the typical month alone fired on 15-25% of peak months, measured by the
doubt-review - and its constant is PROVISIONAL; 3E re-sweeps it on the real
suite. **The measured cost, stated plainly:** without a statistical half the
alert fires on ordinary noise about 2-3% of the time at realistic noise on
the models swept (5-6% at high noise). Materiality is read on orders x AOV:
on level 1's customers x frequency x AOV it read an identity as a masked
shift, 19-39% of months with stable orders and a swinging customer count -
found by the second review cycle, fixed before the commit (Thach). Its own
doubt-review then found the change bound calling a -75% trough month flat;
the change is now measured against the compared months.
pytest 2211 passed.
Previously, session **3D6** closed
2026-09-23 as a **narrow fix, by Thach's choice after two doubt-review
cycles**. A year-ago base is refused below 3% of the series' typical month
(the median magnitude over the history window's trading months), which
removes the reproduction - a 12.50 base on a 50,000 shop, +399,900%,
actionable on three series - and the absurd end of the range. It does not
fix base effects in general, and the session's main finding is that no share
can: a comparator at half normal already fires an actionable +100%. Each
review cycle found a hole the previous fix could not reach - a stall shut
most of the year (fixed), a trickle off-season (not fixable by a yardstick),
baseline bases at 3.5-25% still dragging the centre - and every known limit
was then **run to the headline and classified** (Thach's rule): five
FABRICATE, two SUPPRESS. So **3D9 runs before 3E.** Two claims of mine were
false and are corrected: the residue check was "implied" and the NaN branch
"unreachable". pytest 2180 passed.
Previously, session **3D5b** closed
2026-09-23, and it **deleted most of what 3D5 built**. Thach's decision, taken
after 3D5's own findings were in: the problem is structural, not a sequence of
bugs. An XmR chart assumes a stable process; a seasonal retail series is not
stable in level terms; year-over-year is what makes it stable; and when
year-over-year is unavailable, the information a level chart would need to
stand in for it is exactly the information that is missing. No gate can
synthesise it.
The decisive evidence came from 3D5's own gate: its seasonal-position
condition cannot fire on a 24-month file, because the history window holds one
prior occurrence of the current calendar month and that occurrence is the
comparator whose failure caused the fallback. **Twenty-four complete months is
the project's recommended demo dataset** - the fix could not run on the shape
it was written for.
So the policy moved instead of the arithmetic (`docs/adr/0006-level-signals-
are-descriptive.md`): **level-mode rows are descriptive, never verdicts.** They
are still computed, still carry limits and a rule, still written to
`diagnosis.json`; step 7 does not read them as judgements.
`contracts.diagnosis.is_verdict` decides which rows step 7 may read and
`is_actionable` which may become a cause - two predicates, because a rule-2
row blocks T3 and may never be a headline cause. T3 is `inconclusive`, never
`supported`, when revenue has no year-over-year verdict, at any file length.
The masked-shift alert is the one exception and records its
`masked_shift_basis`. `_level_is_blind`, `_month_not_comparable_to_centre` and
`LEVEL_BLIND_SHARE` are gone, and with them the last tuned threshold on this
path.
**The doubt-review then found that I had updated only one of the two T3 rows
in the documents**, leaving `AI_PIPELINE.md` 7.8 stating the superseded 3D4
rule - which on this session's own flat 14-month fixture evaluates to "within
normal variation", the exact conclusion the ADR forbids. Six more findings,
all mine, all fixed: `is_verdict` conflating two questions, every
masked-shift test running the one branch without a conjunction, an untested
contract validator, four self-contradicting `Signal` shapes the model
accepted, a code-written headline rule that ignored the basis, and a flagship
test whose second assertion was implied by its first. pytest 2156 passed.
Previously, session **3D5** closed
2026-09-23: a series falls back to its level chart only when that chart can
detect a halving. When it cannot, and its year-over-year comparator is also
unusable, the series reports `insufficient_history` with
`insufficient_reason = "neither_chart_informative"` instead of a `within` the
chart could not support. The new field is deliberately separate from
`mode_fallback`; CONTRACTS section 7 says why and says not to merge them.
**The session's main finding is about the evidence, not the code.** The brief
called for a tuned threshold and a sweep. The rule turns out to need neither:
`half_width >= X * |centre|` is the definition of "blind to a drop of X", so
the constant and the drop size are one number and `0.50` states a policy - the
chart must see a halving. **The sweep I first ran scored that rule against its
own definition and returned zero errors because it could not return anything
else; I reported it as validation and then retracted it mid-session.** The
honest measurement is the consequence table: across sixteen shapes 0.50 costs
zero thrown-away detections and zero certified collapses, and 0.60 lets two
collapses through.
**Then the doubt-review found that width was only the smaller half of the
question, and three of its findings were mine.** The width test assumes the
month being judged is expected to sit at the centre, which is false for any
seasonal month: a three-year shop whose December is 150,000 against a centre
of 52,083 reported a December of 75,000 - half its revenue gone - as `within`,
and the gate passed it through. The gate now also asks whether the centre is
the right yardstick for this calendar month. The same review found that
refusing a chart deleted rule-2 runs the contract requires to stay in the
output, and that it discarded real detections; the gate now refuses only
SILENCE, so a chart that fires is kept however wide it is.
The mutation check then caught a regression I had introduced in the same
session: having measured a minimum-spread line as inert I deleted it, but the
sweep behind that measurement only covered money series, where the floor is a
share of the centre. For `return_rate` the floor is absolute, and a shop
returning 0.5% of its orders is drawn with limits twice as wide as its centre.
The floor is back, keyed on the series' own name and mode, and pinned by a
test. **This still does not restore the alarm** - a refused series produces no
signal for its largest movement, only an explicit refusal instead of a wrong
verdict. pytest 2152 passed.
Previously, session **3D4** closed
2026-09-23: year-over-year is no longer computed against a base that is not a
usable denominator. The base must be positive and more than floating-point
residue, and non-finite results are dropped. Each defect was written first as
a failing test from the symptom. **Its doubt-review then found that a claim I
had made about the fix was false, and that the fix made one case worse.**
`price_per_unit` is not immune to the sign problem - I said it was, and the
fixture I offered as evidence had a single price throughout, so it was
arithmetically incapable of showing otherwise. And the guard turned a seasonal
shop's real 50% collapse from `below` rule 1 into a silent `within`, by
pushing the series onto a level chart whose limits span 7,587 to 105,282.
What shipped for that is option (a): the series records **why** it fell back,
and T3 may not call such a month routine - which is **not a fix**, since no
series fires rule 1 on that file at all. Session **3D5** took that on and
replaced the wrong verdict with an explicit refusal; it did not restore the
alarm, and nothing since has. pytest 2132 passed at the time.
Previously, session **3D3** closed
2026-09-23: the four defects that made rule 1 unreliable are fixed, and 3E is
unblocked. Each was written first as a failing test from the symptom - the
RED step is in the Notes - because all four had survived three sessions for
the same reason: no test. The fixes are a minimum spread expressed in the
units each series actually carries, a margin cut back to floating-point
residue alone, rule 2 gated by that margin, and a fall back to level mode when
the current month has no year-ago comparator.
**The doubt-review found three criticals in my first attempt**, and the worst
was the same shape as 3D2's: a floor chosen to stop false alarms that silenced
real ones. At 2% of the centre it hid a 2% revenue drop on a shop whose
ordinary month-to-month variation is 0.2% - a ten-sigma event, and with step 7
acting on rule 1 that does not soften the headline, it deletes it. The cause
was my sweep, not the constant: its "missed break" column only ever scored a
50% collapse, a break so large no floor could hide it, so the sweep was
structurally unable to measure what the floor suppressed. The constants are
now derived from a table of moves that must FIRE beside the ones that must
stay quiet, and that table is a test in the repo rather than a scratchpad
script. It also found a contract violation predating this session: `lever.py`
drove the masked-shift alert from any signal, ignoring the rule number, so
rule 2 reached a contract field that AI_PIPELINE says is decided on rule 1.
pytest 2117 passed. Previously, session **3D2** closed
2026-09-23, and it is the first session whose method did not work. Step-change
detection and re-baselining were attempted, reviewed, and **reverted**; what
shipped is the separable half. Full account in the Notes entry below - the
short version is that the design was wrong, not just the code, and that the
doubt-review also turned up **four defects that pre-date 3D2 and survive its
revert**, which is why the 3E prerequisite has been re-scoped from 3D2 to
3D3. A revert must not read later as "3D2 found nothing": it found thirteen
things, four of them already committed. pytest 2097 passed.
Previously, session **3D** closed
2026-09-23: localization (step 6) - the three fixed dimensions, the Other
grouping, mix vs rate, and breadth. **I ran both a mutation check and a
doubt-review, against the brief's suggestion that the mutation check might
replace it, and that was the right call**: mutation testing only mutates code
that exists, so it is structurally blind to a bug caused by input nobody wrote
a test for - and all three criticals were exactly that. (1) The set logic
keyed on the DISPLAY NAME, so when two keys shared a label - two SKUs under
one product name, the commonest shape in retail - the second member appeared
in neither the named list nor Other and simply vanished, taking 6.4% of the
change with it. (2) `share_of_change` divided by the total under an exact-zero
guard, so a month flat in business terms but -5.6e-17 in floating point gave a
member a share of -5.4e15 - the same mistake `lever.py` had already fixed
twice in 3C, which is why the guard now lives in `numbers.py` where the next
caller inherits it instead of rediscovering it. (3) The size test compared a
SIGNED share against a SIGNED base, so a returns line was judged "small and
quiet" while being the largest movement in the dimension, and a negative base
inverted the test outright. Eight more findings were real and fixed, including
a whitespace-only product name forming a second unflagged bucket, and the
mix/rate split handing itself to whichever metric a negative denominator had
made meaningless (a month that sold 50 and refunded 165 reported price per
unit +1050%). The mutation check earned its keep separately: 3 of its 19
mutants survived the first pass, each a gap in my tests rather than the code.
pytest 2087 passed. Previously, session **3C2** normalised the customer key in
both stages, through one shared `customer_identity` helper, at all six places
either stage groups or counts by customer. This was Thach's call after the 3C
doubt-review reproduced what raw keys do: one customer written three ways,
buying the same amount each month, reads as `new = 200 / lapsed = -200` -
"we lost everyone and gained a whole new base" printed on a flat month, which
feeds the C-family hypotheses and can reach the headline. It had to be done in
both stages at once, because stage 2 groups raw too and changing stage 3 alone
would have broken the agreement 3B's consistency test exists to protect. **No
existing test changed**: 2056 passed, up from 2043 purely by addition, which
is the strongest evidence available that this was a behaviour-preserving
change on well-formed files. Runs already analysed on disk keep their old
`metrics.json` until re-analysed; nothing rewrites them. Doubt-review was
optional at this size and was replaced by a call-site mutation check - a
better use of the budget here, and it earned its keep: the first version of
the tests left **two of the six call sites unprotected**, because the fixture
split a customer only *across* months, so any single-month count came to 3
either way. October, where two spellings coexist, is what discriminates.
Previously, session 3C of 7 closed the metric tree (step 5) - `shapley.py`, `lever.py`, `bridge.py`,
`pvm.py`, `tree.py` - plus the rewrite of `contracts/diagnosis.py` to
CONTRACTS section 7, which closes the divergence 3A opened deliberately.
Both documented Shapley examples reproduce exactly: the Figma sample gives
-10,909.58 / +1,904.44 / +997.14 and ADR-0004's large-swing case
-53,066.67 / +18,933.33 / +34,933.33, with gross-to-net 133.67 against
DIAGNOSE_DESIGN 1.2's quoted 133.7. The large-swing figures were derived by
hand from the closed form before the code was run, so the test is a check
rather than a recording. **The doubt-review was the session's real work: 11
findings, 2 critical, every one reproduced by execution.** The two criticals
were both silent wrongness rather than crashes - a missing `product_name`
cell gave a NaN identity that `groupby` dropped, so those rows left the
product lens while staying in the gross total it reconciles against (on the
reproduction gross sales had fallen 49 and the lens reported a rise of 1, a
direction flip in the numbers the headline is chosen from); and an infinite
price passed the `notna()` validity check, propagated through every sum, and
because JSON cannot hold infinity was serialised as `null` into fields typed
as a required float. Both are fixed at the boundary, and the review's deeper
point is now structural: `RECONCILE_REL_TOLERANCE` was declared in production
thresholds but imported only by tests, so "every decomposition reconciles"
held on seven fixtures and was unchecked on every real file. `tree.py` now
asserts it at runtime and raises `ReconciliationError`, because both
criticals produced a tree that does not reconcile and nothing noticed. A
mutation check was run before and after: of eleven mutants that survived the
first suite, ten are now killed and the eleventh is provably equivalent
(adding zero-quantity rows to a sum of zeros), verified with a no-op control
mutant that correctly survived. pytest 2043 passed (up from 1992). No AI call
(Stage 3 spends credit only in 3F); Vitest not re-run, no frontend touched.
Previously, session 3B closed foundations and steps 1-4. The
cross-stage refactor landed first and safely - `ParsedTransactions`,
`parse_transactions`, `require_column`, `pct_change`, `is_blank` and (beyond
the five the brief listed) `normalize_text` and `product_identity` moved to
`shared/transactions.py`, and 2D's private atomic writer to
`shared/contract_files.py`, with **all 1950 pre-existing tests passing and
`git diff -- tests/` empty**, which is the safety condition the design names.
Then `stages/diagnose/`: `thresholds.py` (every constant from AI_PIPELINE 7.10,
with `YOY_MODE_MIN_MONTHS` written as `YOY_LAG_MONTHS +
XMR_MIN_BASELINE_POINTS + 1` so it cannot drift from the parts it is made of),
`inputs.py`, `frame.py` (step 1), `trust.py` (step 2, D1-D3 + gate),
`calendar_effect.py` (step 3) and `signals.py` (step 4, XmR), plus the five
new blocks in `contracts/diagnosis.py` so every one of those outputs is
validated from day one. The stage 2 / stage 3 consistency test is exact, not
approximate: revenue, orders and active customers recomputed in stage 3 equal
`metrics.json` to the cent. **One doubt-review cycle ran** (the brief's
recommendation, and the right call - the artifact mixed a refactor with new
statistics): **11 findings, all reproduced by execution before being fixed**,
9 fixed in-session and 2 scheduled as the new **3D2, a prerequisite of 3E**.
Three needed Thach's decision and got it: `inconclusive` now downgrades the
trust verdict to `caution`; the XmR margin is `max(relative, absolute floor)`
because a purely relative margin is zero for a series centred on zero, which
`return_rate` is; and re-baselining is scheduled rather than deferred
open-ended, with every signal carrying its `rule` number until it lands. The
one finding worth remembering: **my own justification for a simplification was
disproved with numbers** - I had written, in a code docstring *and* in
AI_PIPELINE 7.4, that using the mean for weekday weights was safe because a
history gap "drags every weekday down by the same factor and the ratio
cancels". It does not; any run of days not a multiple of seven hits weekdays
unevenly, and a shop whose POS was down on Saturdays had 12.6% of its month's
movement invented as real decline. The median fixes it and needs no gap
detection. pytest 1992 passed (up from 1950 after the refactor: 42 new stage 3
tests). No AI call (Stage 3 spends credit only in 3F); Vitest not re-run, no
frontend code touched. Previously, session 3A closed the SPECS UPDATE,
documentation only, no application code. Phase 3
was re-planned from 3 sessions to 7 against `docs/DIAGNOSE_DESIGN.md` (Thach
chose the full engine, not the reduced MVP), and the old 3A-3C plan - sequential
substitution, the AI choosing which hypotheses to rule out - is gone. This
session rewrote `docs/CONTRACTS.md` section 7 (the 8-block `diagnosis.json`,
amended in place at `1.0` with a change-log entry), `docs/AI_PIPELINE.md`
section 7 (the 8-step engine, the fixed hypothesis catalog, the 7 headline
rules, the threshold table) and `prompts/root_cause.md` (narration only), split
the Phase 3 checklist into 3A-3G, and added ADR-0004 (Shapley attribution) and
ADR-0005 (pre-registered hypothesis catalog). **Only `prompts/root_cause.md`
and its new test are executable; no application code changed, and the full
suite passes unchanged apart from the 9 new prompt tests.** Four things worth
carrying forward: (1) the brief said to "update the root_cause prompt test",
but no such test existed - it was created, mirroring the two existing prompt
tests, so the rewritten prompt is not unpinned; (2) `run_id` from
DIAGNOSE_DESIGN section 6's skeleton was deliberately dropped, since no sibling
stage output carries it (only `report.json`, which is downloaded standalone);
(3) `docs/CONTRACTS.md` section 7 and `contracts/diagnosis.py` now deliberately
disagree until 3C rewrites the model - recorded in the section 10 change log
because CLAUDE.md section 1 forbids leaving a doc/code conflict silent; (4)
`YOY_MODE_MIN_MONTHS` is now derived, not a literal - see the Notes entry.
**Phase 2 (Stage 2 Analyze) is DONE**, closed 2026-09-22
with 2D: `stages/analyze/metrics_dimensions.py` (the `by_dimension` block -
revenue by category, current vs previous period; `country` always reports
`[]`, no canonical field carries country data, Thach's decision) and
`stages/analyze/assemble.py` (calls all four blocks' builders - `period`/
`core` from `metrics_core.py`, `customers` from `metrics_customers.py`,
`products` from `metrics_products.py`, `by_dimension` from this session -
validates the combined result against `contracts/metrics.py` and writes
`metrics.json` to the run directory atomically). `POST /api/runs/{id}/analyze`
wired (`backend/app/services/metrics.py` + `runs.py`): `cleaned` (or an
already-`analyzed` run) -> `analyzed`, no AI call anywhere in this stage
(docs/adr/0002), so no retry budget, no AI client, and no transient claim
status the way `execute`'s `cleaning` is - the computation is pure and
deterministic and metrics.json is written atomically, so a concurrent second
call is simply refused (`RunWork.execution`, reused as-is) rather than raced,
verified with a real `threading`-based test mirroring `test_api_races.py`. A
new error code, `ANALYSIS_FAILED` (422, added to `docs/SPECS.md` section 10
and `backend/app/errors.py`), covers both ways stage 2 cannot compute metrics
(a required canonical field, realistically `unit_price`, never mapped; or the
file was flagged NOT_INVENTORY at schema inference) - unlike CLEANING_FAILED
this does NOT fail the run, since `cleaned.csv` stays valid and downloadable
and only the optional stages 2-5 enrichment is unavailable (decided directly,
not asked, mirroring how a NOT_INVENTORY run already keeps its `cleaned`
status elsewhere; flagged for Thach to veto). `analyzed` needed no migration:
it was already in `RunStatus`, the first `runs` migration's CHECK constraint,
and `get_profile`'s own allowed-statuses list from day one - the session
brief's own recollection that it "wasn't defined" was stale, same class of
mistake as 2B's "SPECS section 5.1" reference. 2A-2C (`metrics_core.py`/
`metrics_customers.py`/`metrics_products.py`) closed earlier, committed as
`d5fceea` (2A+2B) and `4fb0f86` (2C). Before that: Phase 1 backend complete
(1A-1G, closed 2026-09-22). Two scoped-exception sessions ran after 1G, not
Phase 6 (full account in Notes below): the Stage-1-frontend session (Upload,
Review, Results), then a same-day bug-fix + Preview-pane-rebuild session -
both committed and pushed (`4d88e27`, `2694511`, `26bee96`). Earlier: Phase 0
(0A `b790448` ... 0D `24307c3`), 1A (`83eccbf`), 1A2 (`ee5d7c9`), 1B
(`f9b12d7`), 1C (`3d5d9d7`), 1D (`8ed0a19`), 1E (`4c96e92`), 1F (`afaa2a6`),
1G (`8f9c19d`), skills Wave 2 (`69697a9`). pytest 1941 passed (up from 1925:
8 new tests across `test_metrics_dimensions.py`/`test_assemble.py`, 7 more in
`tests/backend/test_api_analyze.py`, one existing test extended -
`tests/backend/test_errors.py`'s hardcoded SPECS-section-10 mirror table
gained the new `ANALYSIS_FAILED` row, which is what a pre-existing test
(`test_every_code_maps_to_its_specs_status`) caught and required, not a
weakening; no test deleted, skipped or had an assertion removed); Vitest not
re-run (no frontend code touched this session). No AI call this session
(Stage 2 makes none, ever). **No doubt-driven review cycle run this session**
(judgment call the brief asked for, explained in this session's Notes entry
below): the new arithmetic (`by_dimension.contribution_pct`) was verified to
reproduce both figures in docs/CONTRACTS.md section 6's own worked example
exactly, and the backend wiring composes already-reviewed primitives
(`run_state`, `RunWork`, `stage_errors`) rather than inventing new ones - the
one genuinely new runtime behavior (concurrent-call refusal) was verified
with a real multi-threaded test, not just read for plausibility.
**Next step:** Phase 2 session **2E** (percentage change against a
non-positive base, the orders definition, stage 2's incomplete previous
period), then **3E1b** (how D1 learns from history, and rule 6's size test;
carries the FABRICATEs), then **3E2** (generator, S0-S11, the
`MASKED_MIN_CONTRIBUTION_SHARE` re-sweep with the value allowed to change,
S0/S11 expecting rule 7, and the accepted v1 known limits). Order decided by
Thach after 3E1. 3D9 went to the Backlog ("Unusualness verdicts") with
ADR-0007.
Then 3E (Hypotheses and scenarios), which also carries S11. Step 6 is written
but **not yet wired into an engine** - `compute_localization` has no caller
outside its tests - so on Thach's instruction 3D added the contract round-trip
directly: a computed `Localization` goes through `DiagnosisContract`, out to
JSON and back, on three fixtures including the awkward one (blank categories,
a returns line, a self-cancelling product) and the flat-residue month. The
block is proven contract-valid before 3E builds on it.
Phase 6 (Insights, Dashboard) is
still not started; its Insights frame now waits on 3E (see
`docs/FIGMA_DESIGN_NOTES.md`).
**Action needed from Thach:**
1. Run `C:\Users\Happy\commit-3e1.ps1` - commits session 3E1 alone
   (message file `C:\Users\Happy\commit-3e1-msg.txt`). It stops before
   pushing. (3D6b is committed: `e920761`.)
2. Re-verify the rebuilt Preview pane live in the browser (still outstanding
   from before 2A; not touched by any Stage 2 or Stage 3 session).
3. `.env`'s `ANTHROPIC_API_KEY`: still not re-checked since the Stage-1-frontend
   session (no upload/browser action has run since) - confirm it is a fake
   key, not the `.env.example` placeholder, before the next browser-driven
   upload (see the Stage-1-frontend session's Notes paragraph below for what
   happened the one time this was missed). Phase 3 spends real credit only in
   session 3F.
4. Second demo dataset (decided 3A, no work done yet): Online Retail II,
   customer-sampled with a fixed seed to about 40MB, keeping every row of each
   selected customer, plus invoice-sampled no-Customer-ID rows at the same rate
   so the customer bridge's `unattributed` term has real data to exercise. The
   sampling script and what it sampled go in the README. Not needed before 3E.
- 2026-09-24, Phase 3 session 3E1 (catalog, verdicts, headline rules).
  Closed. pytest 2347 passed. Committed ALONE (commit boundary before 3E2,
  per Thach's split of 3E).
  - **Decisions (Thach):** 3E split into 3E1/3E2; D (terms: own split's
    gross under the alert; expectations: |the change|; never the pair);
    the residual band for expectations; D1 caution on the previous month and
    tied to its check; R3 top products still selling; rule 6 excludes D2/D3;
    statements rendered from the sign; fit ranking; B1/B2 refund interim with
    2E moved before 3E2; B1 (not B2) refused on any possible gap, after an
    execution check that a gap does not move B2; block an incomplete
    previous month through the trust gate; 2E also carries stage 2's
    incomplete previous period; cycle 4 with a stop rule.
  - **Mutation check:** 45 + 16 + 27 + 21 + 8 mutants across the session's
    rounds. Survivors were each given a test and re-run killed, except two
    shown equivalent by computation: A6 (a zero contribution already fails
    the same-sign test) and D0 (a split's gross is at least |its terms' sum|,
    which is the lens total for level 1, product and returns and AOV's
    non-zero contribution for level 2 under the alert - identity residuals
    0.0 on both demo runs).
  - **Doubt-review:** four cycles (cycle 4 beyond the bound, approved with a
    stop rule). Cycle 3: five FABRICATEs + C4 leak + four wording defects,
    all fixed. Cycle 4: two small criticals fixed; the non-local FABRICATE
    and one design question to 3E1c. Cross-model: skipped (Thach).
  - **After the session (Thach):** one 31-file commit accepted; a
    one-month file blocked accepted; B1/T2 refusal rates accepted as v1
    known limits (reported in 3E2); order 2E -> 3E1b -> 3E2, with 3E1c
    merged into 3E1b (same code, same measurement).
  - **Tests changed, each with its reason:** the headline fixture's
    contribution sign (share = contribution / D; it was inverted, harmless
    until rule 6 read signs); two 3B tests moved from a one-month file to a
    two-month file (a one-month file is now blocked - it fabricated "products
    launched (100%)"), intent kept; two T2 arithmetic tests moved to daily
    rows (one row a month is a legitimate zero-sale pattern T2 now refuses);
    one product-overshoot wording test moved to a net change that moves with
    the product cause; C4 rule tests switched on explicitly. None deleted.
- 2026-09-23, Phase 3 session 3D6b (ADR-0007: no step-4 row is a verdict in
  v1; the masked-shift alert on the tree). Closed. pytest 2198 passed. New:
  `tests/stages/diagnose/test_no_step4_verdicts.py` (7 tests written first,
  RED captured, then unit tests from the mutation check and both review
  cycles). **Committed ALONE** (Thach).
  - **Decisions implemented (Thach):** `is_verdict` returns False; T3 never
    supported; headline rule 3 dormant; S0/S11 expect rule 7; the engine's
    claim reframed to "never invents a cause when no hypothesis is
    supported"; masked-shift alert on the tree; `masked_shift_basis`
    removed; rule 4 always hedged; 3D4/3D6 guards kept for display; 3D9 to
    the Backlog as "Unusualness verdicts", with the two-year-median error
    recorded; the share PROVISIONAL and re-swept in 3E.
  - **One decision changed on evidence, by Thach, mid-session:** the floor.
    As first decided it was 20% of the typical month; the doubt-review
    measured it firing on 15-25% of peak months with nothing planted, and on
    a stall's in-season months against a trickle typical. Thach chose floor
    C: 20% of max(typical, last month, this month), plus a bound on the
    change - measured, after the pair's doubt-review, against the larger
    compared month rather than the floor. Over the pair the ratio test is
    implied (proved in `_masked_shift`, pinned by a test on
    MASKED_GROSS_TO_NET <= 3); the three-factor ratio it actually reads is
    not, and is kept live and pinned.
  - **Tests deleted, each with its reason** (all asserted behaviour ADR-0007
    removes): the alert needing a step-4 signal, a rule-2 signal not driving
    it, the two basis/hedge tests, the mixed-mode fixture, three basis
    contract cases, and 3D6's rule-4 test (vacuous once the alert stopped
    reading rows). **Flipped:** the yoy-verdict, rule-2-verdict and
    yoy-actionable tests. **Rewritten:** the short-file, quiet-month,
    ratio-path and ratio-threshold alert tests, the contract null-alert
    tests, 3D6's stall test (its only assertion had become constant-true).
  - **Mutation check:** 40 mutants (5 on the pair) on the policy, the floor, flatness,
    materiality, the yardstick, the sign guard and the validator - all
    killed except F2 (the ratio test), a predicted EQUIVALENT. It found:
    one-sided and boundary cases no row fixture can build (flat two-factor
    months split +x/-x) - now unit tests; the max pinned only by its typical
    term; the sign guard untested on the current month and at zero; and a
    DUPLICATED constant line I had introduced, which hid three mutants.
  - **Doubt-review, two cycles.** Cycle 1 (mine): old diagnosis.json files
    would not load while the change log said they did; I quoted only the
    kinder half of my own sweep (two-factor and stable-frequency rows) and
    left out 6.5% / 15%; the peak-month and doubled-month failures that led
    to floor C; stale text in six files; S9 both "must not fire" and "fires
    by design" in one paragraph; the Figma "normal variation" state still
    required. Cycle 2 (mine): section 12 still stated the old rule; a
    must-fire claim the saved output contradicts; two tests claiming ratio
    coverage they did not have; residue months counted as trading months;
    a revenue sign-crossing month narrated backwards - all fixed; and the
    customers/frequency identity read as a masked shift (19-39%), which
    Thach identified as structural, not a noise question for 3E: fixed by
    deciding materiality on orders x AOV, run before adoption, with a new
    contract field `masked_shift_pair` and the "4 customers once -> 1
    customer 4 times" test flipped to NO alert.
  - **Doubt-review of the pair step** (Thach: he had skipped the
    cross-model review, not the doubt-review - I had conflated the two).
    Findings, all mine: (HIGH) "the three-factor ratio never binds, 0 in
    12,000" was false - only 338 of those draws fired the pair, none in a
    trough, and a case with 2.975 against the pair's 3.05 exists; (HIGH) the
    change bound, measured against the floor, called a -75% trough month
    flat and fired - a fabrication in floor C; "S6 exactly as before" and
    the quoted cost contradicted the saved outputs; the validator did not
    tie the pair to level 1 or to a fired alert; the pair's orders carried
    residue (29.000000000000004); leftover level-1 wording; the 7.8 D split
    now ambiguous. All fixed except D, handed to 3E. The ratio check is now
    live and pinned; a targeted search (control finds 169 on the first
    bound) finds none under the shipped rule. Final pytest 2211 passed;
    mutation check: 10 more mutants on the review fixes, all killed (50 in
    the session, all killed except the predicted-equivalent pair ratio,
    which the fixes made live and is now killed too).
  - **Next step:** session **3E**.
- 2026-09-23, Phase 3 session 3D6 (how small a base stops being a usable
  denominator). Closed as a narrow fix. pytest 2180 passed; 17 new tests in
  `tests/stages/diagnose/test_yoy_small_base.py` (three are KNOWN LIMITS
  asserting defects for 3D9 to flip), three call sites in
  `test_yoy_base.py` given the new `history` argument. Mutation check: 18
  mutants on the guard's decision points plus a no-op control, all 18
  killed; of 3D4's four older checks the residue check is killed, the sign
  test and both non-finite drops survive as EQUIVALENT mutants (implied by
  the share, documented in `_as_yoy`). Doubt-review: two cycles, one fresh
  reviewer each; cross-model offered, Thach skipped.
  **Grouped with 3D4 + 3D5 + 3D5b, not committed.**
  - **RED first, from the symptom:** the reproduction failed with the exact
    plan figures (399,900 on revenue, aov, units_per_order; alert True basis
    yoy; the baseline route's centre at 33,058 points).
  - **Method.** Scale-free yardstick = median |value| over the history
    window's trading months. Candidates swept: none, the global median at
    0.01-0.1, windows centred on the base (+-6, +-2), a cap on the result.
    The flat-shape part of every sweep is circular - excluded iff f < k - and
    is labelled as such; the non-circular content is which yardstick survives
    which shape, and where business shapes land on the ratio line.
  - **Mine, found by my own mutation check:** the new guard caught every
    input 3D4 wrote for its residue test, so that check could be deleted
    with a green build. Pinned twice, as the mechanism moved.
  - **Mine, found by doubt-review cycle 1:** the guard was inert on a shop
    shut most of the year (median of zeros) - fixed; I had written that
    refusing any base "only removes a verdict", which is true for the
    current comparator only - corrected everywhere it appeared; my own
    cycle-1 check of two-regime shops was mislabelled (its "on-season"
    current month was off-season), found by cycle 2.
  - **Mine, found by cycle 2:** the residue check called implied (it is
    load-bearing when half the trading months are residue) and the NaN
    branch called unreachable (it is reached by `return_rate` on a shop with
    no returns, harmlessly). Both corrected.
  - **Not fixed, by decision:** L1-L7 on the 3D9 line. Thach's triage by
    execution put 3D9 before 3E.
  - **Also fixed in passing (pre-existing):** AI_PIPELINE 7.5 never described
    3D4's base guard at all, although the brief pointed there for it; it now
    describes all three conditions. Section 12's "Next step" had named 3D4
    since 3D3.
  - **Next step:** session **3D9**.
- 2026-09-23, Phase 3 session 3D5b (ADR-0006: level-mode signals are
  descriptive, never verdicts). Closed. pytest 2156 passed. 16 new tests
  (13 in `tests/stages/diagnose/test_level_is_descriptive.py`, 7 parametrised
  contract cases in `tests/contracts/test_diagnosis.py`); 10 tests deleted
  with 3D5's gate, listed below. Mutation check run twice: the second pass is
  19 mutants plus a no-op control and kills all 19. Doubt-review: 1 critical
  and 7 required/nice-to-have, ALL OF THEM MINE, all fixed - see below.
  **Not committed - groups with 3D4, 3D5 and 3E.**
  - **Thach's decision, and the reason it is a policy not a patch.** Four
    sessions (3D2 step detection, 3D3 floors, 3D4 base guard, 3D5 gate) each
    closed with deeper open items on the same block. An XmR chart assumes a
    stable process and a seasonal series is not stable in level terms; when
    year-over-year is unavailable, what a level chart would need to replace it
    is precisely what is missing. The clincher was 3D5's own gate:
    `HISTORY_MAX_MONTHS` is 24, so a 24-month file's window holds ONE prior
    occurrence of the current calendar month, and that occurrence is the
    broken comparator. The seasonal-position condition is therefore inert on
    the project's recommended demo dataset length.
  - **What the policy is.** Only `yoy` rows are verdicts
    (`contracts.diagnosis.is_verdict`). Level rows are computed, written and
    shown, and step 7 does not read them. T3 is `inconclusive`, never
    `supported`, when revenue has no year-over-year verdict at any file
    length, and its evidence lists every series without one.
  - **The one exception, with its reason recorded in the ADR.** The
    masked-shift alert may read level rows, because its other half
    (`gross_to_net`) divides by the change in revenue and so fires on every
    flat month by itself - resting the alert on the ratio alone would break it
    on exactly the files it exists for. `Lever.masked_shift_basis` records
    `yoy` or `level`, null exactly when the alert is null or false, enforced
    by a contract validator. A `yoy` row beats a `level` one when a run
    carries both.
  - **The handover is a rule, not a note** (Thach). The deleted gate was the
    only thing stopping a level `within` reaching a reader as "within normal
    variation". CONTRACTS section 7 now states that stage 5 renders level rows
    with different wording, and AI_PIPELINE 7.9 states that the 3F validator
    rejects any sentence calling a level-mode series normal OR certainly
    unusual, and hedges a level-based masked-shift alert as possibly seasonal.
  - **Deleted, and why each was deleted rather than weakened.** Ten tests went
    with the gate: the four width tests (`..._blind_level_chart...`,
    `..._can_see_a_halving_is_offered...`, `..._cannot_see_a_halving_is_
    refused...`, `..._rate_chart_is_judged_on_the_width...`), the coupling
    property test, the negative-centre test, and the four seasonal-position
    tests from the 3D5 doubt-review. Every one asserted behaviour of code that
    no longer exists; none asserted a behaviour the engine still has. The
    facts they protected did not evaporate - they stopped being decisions the
    engine makes. `test_the_fallback_does_not_restore_the_series_alarm`
    survives with its `insufficient_reason` assertion replaced by
    `is_verdict`, because its real claim (no rule 1 fires on that file) still
    holds.
  - **Kept from 3D5 deliberately:** `no_current_value` and
    `no_measurable_spread`. They fix a field that reported a wrong reason on
    two of its branches, which is unrelated to this policy.
  - **The mutation check found the policy's weak side was the positive case.**
    A mutant making `is_verdict` return False for everything survived the
    first pass: every test asserted what is NOT a verdict, so "nothing is ever
    a verdict" satisfied all of them - which would leave T3 permanently
    inconclusive and the engine unable to say a quiet month was quiet. Two
    more survivors needed a run carrying BOTH modes at once (revenue's
    year-ago base broken while the customer count's is clean). All three now
    have tests.
  - **The doubt-review found one critical, and it was a documentation miss
    that would have made the whole session pointless.** There are TWO T3 rows
    in the documents - one in `DIAGNOSE_DESIGN.md`'s catalog and one in
    `AI_PIPELINE.md` 7.8 - and I updated only the first. The second still
    carried the 3D4 rule, and on this session's own fixture (a flat 14-month
    file) it evaluates to **T3 supported, headline rule 3, "within normal
    variation"** - exactly what ADR-0006 forbids, reached from absence. Two
    source-of-truth documents giving opposite answers on the same file is the
    thing CLAUDE.md section 1 says to stop and reconcile. Fixed, along with a
    3D4 paragraph thirty lines above the live rule that a reader had no way to
    date.
  - **Six more, all mine, all reproduced before fixing.**
    - `is_verdict` was declared "the single definition" and expressed neither
      rule: a `yoy` rule-2 row is a verdict under it, which contradicts the
      rule-1-only contract - while `_masked_shift` filtered rule 1 itself, so
      the codebase disagreed with its own definition. Split into `is_verdict`
      (may step 7 READ this row - true for rule 2, which blocks T3) and
      `is_actionable` (may it become a CAUSE - rule 1 only). Both now tested,
      including the positive cases.
    - Every masked-shift test I wrote ran the `gross_to_net is None` branch,
      where the ratio has no denominator - so all four `basis` assertions
      exercised the ONE branch where the conjunction the ADR calls
      load-bearing is not evaluated. Added a ratio-path test, and the ADR now
      states that the flat branch is the ratio at its limit rather than a
      missing half.
    - The `masked_shift_basis` validator could be deleted entirely with a
      green build. Now has three rejection cases.
    - `Signal` accepted four rows that contradict the documents (a reason on a
      charted row; no reason on an unchartable one; a fallback on a yoy row; a
      rule on a `within` row). Two are mine, two predate 3D4. All four now
      raise - the same file argues at length that this class of invariant must
      be "enforced, not just documented". `_no_baseline`'s `reason` lost its
      default for the same reason.
    - Headline rule 4 is written by CODE and outranks rules 5-7, and my hedge
      for a level-based alert lived only in 7.9, which is skipped in degraded
      mode. The wording is now conditional on `masked_shift_basis` in 7.8 too.
    - The flagship test's second assertion was implied by its first, so the
      symptom in its docstring was asserted nowhere. It now pins the real
      content: a halved December and an ordinary one produce IDENTICAL signal,
      rule and limits.
  - **One finding changed the design, not just the docs.** The basis rule said
    "the stronger basis wins". Headline rule 4 names the two largest OPPOSING
    contributions, so if the evidence that a named contributor moved unusually
    is a level row, an unrelated year-over-year row elsewhere in the run is no
    reason to drop the hedge. It is now `yoy` only when EVERY contributing row
    is `yoy`.
  - **Scheduled, not fixed:** 3D8, the year-over-year residue guard anchored
    on the whole series' maximum. Reproduced: 26 months of revenue 100 charts
    `yoy`; change one month to 1e12 and it charts `level`. ADR-0006 made the
    consequence worse, because losing yoy mode now means losing the verdict.
  - **Next step:** session **3E** (hypotheses and scenarios). It carries S11,
    the T3 rule above, and T3's new evidence list.
- 2026-09-23, Phase 3 session 3D5 (decide whether the level chart is
  informative before falling back to it). Closed. pytest 2152 passed
  (2132 before), 20 new tests in `tests/stages/diagnose/test_yoy_base.py`.
  Mutation check run twice, before and after the doubt-review rework: the
  second pass is 19 mutants plus a no-op control and kills all 19. The first
  pass left three survivors, two of them unreachable from `compute_signals`
  (confirmed by exhausting all 8,192 presence masks) and one an exact-float
  boundary; the rework replaced that gate, so the second pass supersedes it.
  Doubt-review: run, see below. **Not committed - groups with 3D4
  and 3E.**
  - **What shipped.** `_level_is_blind(column, history, name)` measures the
    series' own level chart against its own centre before the fallback is
    taken. Blind means a halving would sit inside the limits. A blind series
    reports `insufficient_history` with `insufficient_reason =
    "neither_chart_informative"` rather than `within`. `insufficient_reason`
    is a new `Signal` field, kept separate from `mode_fallback` on Thach's
    instruction, with the reason written into the contract so a later session
    does not merge them.
  - **The brief asked for a tuned threshold and a sweep; the honest answer was
    that the rule needs neither, and the first sweep I ran was circular.** A
    drop of fraction X moves a month X*centre away from the centre, and the
    chart flags it only when that exceeds the half-width, so
    `half_width >= X * |centre|` IS "blind to a drop of X". The constant and
    the drop size are the same number. I nonetheless produced a table scoring
    that rule against "would a halving be visible" - the same expression - got
    zero errors of both kinds at 0.50, and reported it to Thach as evidence
    the constant was right. **Any threshold scored against its own definition
    returns zero errors.** I caught it while building fixtures from the table
    and retracted it in the same session. The lesson is narrower than "check
    your sweeps": a 0/0 result is not a strong result, it is a warning that
    the predictor and the truth column may be the same quantity.
  - **What replaced it.** Sixteen shapes run through `compute_signals` twice,
    once with the rule disabled, counting two costs that are computed
    independently of the threshold: detections thrown away (level would have
    fired rule 1 and we refused) and collapses certified normal (level says
    `within` on a halving). No policy scores zero on both:

        policy   refusals   thrown away   certified normal
          30%          10             3                  0
          50%           8             1                  0
          60%           5             0                  2
         100%           4             0                  3

    0.50 is chosen because the costs differ in kind, not size: the first is
    the engine saying "cannot say", the second is the engine making a false
    statement. **Where it behaves badly, by name:** a three-month Q4 peak
    lands at 50.5% and loses a `below` it would otherwise have fired, missing
    by half a percentage point.
  - **A model of the code is not the code.** My first sweep re-implemented the
    spread logic in the scratchpad. When I built real fixtures from its
    numbers they did not match: December x3 read 59.5% in the model and 86.6%
    through `compute_signals`. Every number that reached the test file was
    afterwards read back out of `stages/diagnose`, per the 3C lesson.
  - **The mutation check caught a regression I introduced this session.**
    Having measured a `max(spread, _minimum_spread(...))` line as inert across
    4,013 shapes, I deleted it as decoration. The deletion was half right: the
    line was wrong (it passed a BLANK series name, handing every series the
    money floor - 3D2's R4 finding by name) but deleting it outright broke a
    case the sweep could not see, because the sweep was all money series.
    For money the floor is a share of the centre and can never approach a 50%
    policy; for `return_rate` it is an absolute 0.01, so a shop returning 0.5%
    of its orders is DRAWN with limits twice as wide as its centre while its
    measured spread reads as a comfortable 25%. The floor is back, keyed on
    the real name and mode, applied exactly as `_signal_for` applies it.
    **A sweep that covers one series type characterises one series type**,
    which is the same shape of error as 3D3's miss column only ever testing a
    50% collapse.
  - **The two techniques, separately.** The mutation check found the
    `return_rate` regression above and a decoupling risk: `_level_is_blind`
    and `_signal_for` each derive a centre and width from the same baseline in
    two places, and nothing makes them agree - a median centre instead of a
    mean passes every other test in the suite. That is now pinned by a
    property test over six shapes, including a shop ramping from 2,000 to
    200,000 whose mean and median are an order of magnitude apart. Three
    survivors were accepted rather than tested: two are unreachable from
    `compute_signals` (a year-over-year point needs level values at both m and
    m-12, so the level baseline can never be shorter than the year-over-year
    one - confirmed by exhausting all 8,192 presence masks), and one is `>=`
    against `>`, which differs only at exact float equality.
  - **Three 3D4 tests were rewritten, with reasons, not weakened.** They
    asserted `mode_fallback` on the seasonal fixture, which correctly stops
    falling back after this change, so two moved to a flat fixture that still
    takes the fallback and one now asserts the new refusal. The behaviour each
    was written to protect is still asserted; what changed is the fixture that
    exercises it, and `test_the_fallback_does_not_restore_the_series_alarm`
    still holds its line - no series fires rule 1 on that file, before or
    after.
  - **Two smaller things found while checking the new field's own values.**
    Only two of its four members could ever be produced.
    `step_change_too_recent` named the feature 3D2 reverted, so it is out of
    the Literal until that backlog item lands - a contract value nothing can
    emit invites a consumer to handle it and a reader to believe the feature
    exists. And the branch where the baseline is complete but the current
    month has no value (`aov` on a month with no orders) reported
    `too_few_points`, the one explanation that is not true there; it now
    reports `no_current_value`. Written as a failing test from the symptom
    first.
  - **The doubt-review found three criticals and two required; three of the
    criticals were mine and one was not.**
    - C1, MINE and the worst: the width test asks whether a halving OF THE
      CENTRE would show, which is the right question only while the month
      being judged is expected to sit at the centre. On a seasonal peak it is
      not. A three-year shop whose December is 150,000 against a centre of
      52,083 reported a December of 75,000 as `within`, inside limits of
      (28,953 .. 75,214) - requirement (a) verbatim, waved through by the very
      gate written to enforce it. `_month_not_comparable_to_centre` now asks
      the second question, in magnitude so trough months are caught too. My
      own consequence table could not have shown this: all sixteen shapes put
      the current month at a TROUGH, so centre-relative and month-relative
      halvings never diverged upward. A shape set that varies one thing
      characterises one thing.
    - C3, MINE: refusing a chart deleted the whole row, including rule-2 runs
      that AI_PIPELINE 7.5 requires to stay in the output unacted on. The gate
      now refuses only SILENCE - a chart that fires is kept however wide it
      is, since wide limits make a chart fire LESS often, so firing despite
      them clears a higher bar. That one change also emptied the
      thrown-away-detections column at every policy and fixed the reviewer's
      R1: a return rate of 0.5% is blind to a halving and still catches a
      month at 30%, and that signal was being discarded.
    - R2, MINE: `insufficient_reason` lied on two of its three branches in the
      same session that added it. Both fixed, each written as a failing test
      from the symptom first.
    - C2 I had already found independently and closed in the docs before the
      review landed; its own repro confirms the new T3 rule blocks what the
      old one allowed.
    - **C1b I disagree with, and the data is why.** It reported a halved
      December read as `above` rule 1 on a 24-month file. That file's baseline
      contains exactly one December, `-2000`, and every other month is 50,000:
      nothing in it says December is a peak, so reporting 75,000 as above a
      flat 50,000 shop is correct inference from the evidence present. The
      halving is a fact about the fixture's intent, not about the data the
      engine was given. Recorded rather than "fixed", per the rule that an
      unreproduced or disputed report stays open with both readings.
  - **Left open, with the measurement, for Thach to schedule.** The gate is
    consulted only when the series was eligible for year-over-year mode. A
    20-month seasonal file charts on the same wide level chart unexamined and
    is free to claim `within` on a halving. Extending the gate to natively
    level series changes what every short file reports, which is past this
    session's scope - the brief was "before falling back to it". Also open:
    `_fallback_reason` reports `no_year_ago_value` ("the shop was shut") for a
    month that has rows but was not fully covered, a third fact wearing one of
    two labels.
  - **A hole in T3 that 3D5 opened and 3E must implement closed.** T3's three
    conditions are all about signals that DID fire, so none of them notices a
    series with no chart. Before this session a blind series carried
    `mode_fallback` and the third condition caught it by accident; now it is
    refused outright and carries none. On six seasonal files revenue reports
    `insufficient_history` with no rule firing, and T3 is blocked on all six
    only by a rule-2 signal on `return_rate` that has nothing to do with the
    revenue collapse. **T3 is now also `inconclusive` whenever `revenue` is
    `insufficient_history` for any reason** - written into AI_PIPELINE 7.5 and
    the DIAGNOSE_DESIGN T3 row. Step 7 does not exist yet, so this is a
    contract change, not a code change; 3E implements it.
  - **Next step:** session **3E** (hypotheses and scenarios), which carries
    S11. 3D5 was its last prerequisite. Then **2E** (stage 2's `pct_change`
    sign defect, must land before 3F) and **3D6** (the magnitude half of the
    base guard), then 3F and 3G. Commit: 3D4 + 3D5 + 3E together, one message
    organised by session, plus the commit script in Thach's home directory.
- 2026-09-23, Phase 3 session 3D4 (year-over-year against a non-positive
  base): new - `tests/stages/diagnose/test_yoy_base.py` (15 tests); edited -
  `stages/diagnose/signals.py`, `contracts/diagnosis.py`,
  `docs/AI_PIPELINE.md` 7.5 + the T3 catalog row, `docs/DIAGNOSE_DESIGN.md`.
  - **The fix.** `_as_yoy` required only a non-zero base, so it divided by
    negative months. A shop going -100 to -200 - twice the loss - reported
    +100%, `above`, **rule 1**, the rule step 7 acts on. The base must now be
    positive AND more than residue (`is_negligible`, the helper this codebase
    wrote for exactly this and which `signals.py` already imported and never
    called), and non-finite results are dropped.
  - **A claim I made was false, and my evidence could not have shown it.** I
    told Thach `price_per_unit` was immune because revenue and units flip
    together in a refund-heavy month. That holds only while every line carries
    the same price. One sale of 1 at 1000 against four refunds of 3 at 50
    leaves revenue at +400 and price per unit at -36.36. The fixture I cited
    used a single price of 10.0, so `price_per_unit` was CONSTANT across all
    25 months - the measurement was of the fixture, not the code. The guard is
    load-bearing for four series, not three.
  - **I shipped a tautological test.** `assert signal.value_cur ==
    pytest.approx(signal.value_cur)` compares a value to itself, and
    `assert signal.signal in (...)` enumerated every member of the Literal.
    It was the strongest stated evidence for the false claim and it could not
    fail. Rebuilt on a two-price fixture with hand-computed values.
  - **The fix made one case worse, and that is now recorded as 3D5.** On a
    seasonal shop whose January halved against a normal January, the guard
    turned `below` rule 1 into a silent `within` by pushing the series to a
    level chart spanning 7,587 to 105,282. Pre-3D4 the engine printed a
    garbage figure (-1350%) but rang the bell; post-3D4 it rings nothing.
    Option (a) shipped - the series records `mode_fallback` and T3 may not
    call the month routine - and it is explicitly NOT a fix: no series fires
    rule 1 on that file.
  - **How I got the reproduction wrong, which is worth keeping.** I could not
    reproduce the reviewer's case and nearly recorded it as unverified. My
    fixture put the non-positive month where it only eroded baseline points -
    11 usable, 3 to spare, nothing happens. The reviewer's put it at exactly
    `shift_month(current, -12)`, where it kills the current-month test with no
    erosion at all. Same defect name, different mechanism, and only one of
    them reproduces. Asking for its exact bytes rather than trusting either of
    our summaries is what settled it.
  - Two pre-existing defects surfaced and were NOT fixed: stage 2's
    `pct_change` has the same sign inversion in `revenue_change_pct` and
    inverts `_biggest_decliners` (scheduled as 2E, before 3F), and
    `monthly_series` charts a month with no rows as 0.0, contradicting
    `inputs.py`'s own 3B finding 2 (recorded here; it changes the baseline of
    every level chart, so it is not a tail-of-session change).
- 2026-09-23, Phase 3 session 3D3 (make rule 1 reliable): new -
  `tests/stages/diagnose/test_rule_one_reliability.py`,
  `tests/stages/diagnose/test_spread_floor_cases.py`; edited -
  `stages/diagnose/signals.py`, `stages/diagnose/thresholds.py`,
  `stages/diagnose/lever.py`, `contracts/diagnosis.py`, two existing test
  files, `docs/AI_PIPELINE.md` 7.5 + the threshold table,
  `docs/CONTRACTS.md` 7.
  - **The RED step, on the record.** All four defects were written as failing
    tests from the symptom before any fix: `a 1% rise reported as above
    against limits (0.0, 0.0)`; `assert 0.0 > 0.0`; `an unchanging decline
    reported as below against (-10.82, -10.24)`; `an 80% collapse reported as
    insufficient_history`. Six failing, two passing.
  - **One of the four is not reproducible as a symptom, and that is the
    finding.** R4 - the margin floors being in the wrong units for
    year-over-year mode - has no failing scenario: a perfectly steady return
    rate gives a YoY series of exactly 0 AND a current value of exactly 0, so
    it stays within limits however wrong the units are. R4 is the MECHANISM
    behind C1b and R6 rather than a defect with its own symptom, which is
    exactly why it survived three sessions with a green suite. Pinned as a
    unit test of `_minimum_spread` instead.
  - **The doubt-review's three criticals, and the one that matters.** A floor
    of 2% of the centre silenced a 2% drop on a shop turning over 1,000,000 a
    month whose ordinary variation is 0.2%: measured half-width 12,580 against
    a floor of 19,996. Every business enters that class once it has enough
    volume for the law of large numbers to bite. Also: `limits_method` lied
    whenever the floor bound, reporting the estimator that had returned zero -
    the precise thing Thach added that field to prevent, one session earlier;
    and zero-width limits still existed for a money series whose centre is
    exactly 0, which now reports `insufficient_history` rather than a floor
    picked out of the air.
  - **Why my sweep could not see it, which is the lesson.** The sweep scored
    two columns, false alarms and missed breaks - but every "break" it tested
    was a 50% collapse, which no floor could hide. The miss column was
    therefore structurally incapable of detecting an over-wide limit, so it
    read 2 for every candidate and I quoted that as evidence the floors were
    safe. Rescored with breaks at 2, 4 and 8 sigma, the same sweep shows
    misses rising from 8 to 11 to 18 as the floor grows.
    3D2's lesson was "evidence that only covers the cases you thought of
    proves nothing". This is its sharper form: **a metric that cannot fail
    is not evidence that something passed.** Ask what result would falsify
    the claim, and check the measurement can produce it.
  - **A contract violation predating this session.** `lever.py` selected
    signals for the masked-shift alert with `signal.signal in FIRED` and no
    rule check, so rule-2 signals drove a field AI_PIPELINE 7.5 states is
    decided on rule 1 - a contract written in 3D2 that the code never
    honoured. Fixed, with the test that would have caught it.
  - **Two defects deferred to 3D4, which is a PREREQUISITE of 3E.** Both are
    in `signals._as_yoy` and both pre-date this session. The reproduction that
    decided the placement: a shop whose month went from -100 to -200 reports
    `value_cur = +100.0`, `signal = "above"`, `rule = 1`. A doubling of losses
    read as an unusually good month, through the rule step 7 acts on. I had
    first written these up as "not blocking 3E's rule-1 path"; running the
    case showed the opposite, which is why it is scheduled ahead of 3E rather
    than after it. Nothing protects 3E from it in the meantime - the only
    thing that IS safe is the contribution figures, since the tree is computed
    from level data and never from the year-over-year series.
  - The mutation check found two decision points I had added without pinning
    (rule 2's margin, the residue floor) and **a bug in one of my own tests**:
    an offset of 1e-15 on a centre of 100 is below the float spacing there, so
    the "noise" I was testing did not exist.
- 2026-09-23, Phase 3 session 3D2 (step-change detection: ATTEMPTED AND
  REVERTED): shipped - the median moving range for the XmR spread with an
  average fallback (`stages/diagnose/signals.py`, `thresholds.py`), the
  `limits_method` field (`contracts/diagnosis.py`), and
  `tests/stages/diagnose/test_limit_estimator.py` (7 tests). Reverted -
  `stages/diagnose/baseline.py`, the median centre, and
  `tests/stages/diagnose/test_step_change.py`. Docs updated:
  `docs/AI_PIPELINE.md` 7.5 + the threshold table, `docs/DIAGNOSE_DESIGN.md`
  5.4, and the Backlog entry recording how the method failed.
  - **All thirteen findings.** Four PRE-DATE this session and survive the
    revert; they are the reason 3D3 exists.

    | # | Severity | Origin | What |
    |---|---|---|---|
    | C1a | critical | 3D2 | median mR = 0 gives zero-width limits; a 0.2% move fired rule 1 |
    | **C1b** | critical | **3B, still live** | YoY centre 0 + 1e-6 margin: a stable business growing 1% fires rule 1 |
    | C2 | critical | 3D2 | `RECONCILE_REL_TOLERANCE` used as a significance floor; a 1p price rise was a step |
    | C3 | critical | 3D2 | step reported 12 months late in YoY mode |
    | C4 | critical | 3D2 | a two-month promotion re-baselined |
    | C5 | critical | 3D2 | 40 of 72 seasonal shapes re-baselined; blind every peak season |
    | R1 | required | 3D2 | wrong split chosen; reports an abandoned level |
    | R2 | required | 3D2 | abruptness and sigma computed across data gaps |
    | **R3** | required | **3B, still live** | no current-month YoY comparator: an 80% collapse reads as `insufficient_history` |
    | **R4** | required | **3B, still live** | margin floors in money/fractions, not the mode's units |
    | R5 | required | 3D2 | replaced 3B's rule-2 test; a real 50% step went silent |
    | **R6** | required | **3B, still live** | constant-rate decline fires rule 1 every month in YoY |
    | R7 | required | 3D2 | non-monotonic or duplicated index silently corrupts the baseline |

  - **What shipped, and why it cannot regress.** The median moving range
    resists a single anomalous month (3B finding 3a: limits 650 wide and the
    series unable to signal, against 17 for the median). It falls back to the
    average whenever the median is zero, and on every series where that
    triggers the result is bit-for-bit what the average alone produced. The
    two 3B expectations that moved were recomputed BY HAND, not re-fitted:
    limits `(69.41, 130.59)` -> `(68.55, 131.45)` from a median mR of 10.0
    against a mean of 11.5; and `(59.3, 154.1)` -> `(75.22, 138.12)` on the
    rule-2 fixture, centre unchanged at 106.67 in both.
  - **A test I deleted, and should not have.** The rule-2 fixture was replaced
    on the argument that the mean centre fired there only because outliers had
    displaced it. That series has no outliers: the centre was displaced by the
    shop's genuine earlier level, which is what rule 2 is for. CLAUDE.md
    forbids deleting or weakening a test; this broke that rule. The test is
    restored with only its limit numbers recomputed.
  - **The process lesson, which is the same one as last session wearing a
    different hat.** I validated the method on FOUR hand-picked series and
    presented the result as if it characterised the method. It did not: the
    failures live on series I never generated - a two-month spike, a
    multi-month season, a business that steps twice, detection in YoY mode.
    Worse, the zero-width failure was ON SCREEN in that same run. My
    exploration printed `width = 0.00` twice, and I wrote it off in the
    proposal as "one honest caveat... 3B's margin already covers that" -
    asserting the margin covered it without ever computing whether it did. It
    does not: a margin of 0.5 against a move of 1.0.
    3D's lesson was "a test that passes under both the right and the wrong
    code proves nothing". This is that lesson one level up: **evidence that
    only covers the cases you thought of proves nothing either, and a caveat
    you notice but do not compute is not a caveat, it is a defect you have
    seen and approved.**
- 2026-09-23, Phase 3 session 3D (localization, step 6): new -
  `stages/diagnose/{members,mix_rate,localization,numbers}.py`,
  `tests/stages/diagnose/test_localization.py` (31 tests); edited -
  `contracts/diagnosis.py`, `stages/diagnose/{bridge,trust,lever}.py`,
  `docs/AI_PIPELINE.md` 7.7, `docs/CONTRACTS.md` 7.
  - **Thach's three edge-case decisions**, all implemented and each one
    changing the design more than it looked. Naming the top movers when
    nothing clears the bar needed `size_filter_waived` to have a precise
    meaning, and defining it exposed that `customer_type` - four fixed
    members, bar measured on PREVIOUS revenue, which `new` has none of - would
    have hidden new customers on every run. The reserved `(uncategorised)`
    label needed the bucket identified by its flag rather than its name, since
    a real category can be spelled that way. Presence-means-counted-rows came
    straight from the bridge, so the two lenses agree about who was there.
  - **Why I ran the doubt-review as well as the mutation check.** The brief
    suggested the mutation check might replace it. It cannot: mutation testing
    mutates code that exists, so no mutant can represent an input nobody wrote
    a test for. All three criticals were that shape, and all three were
    invisible to 19 passing mutants. Worth keeping as a rule - the two
    techniques fail in opposite directions, and step 6 groups on two key
    columns that can both be blank.
  - **The standing rule Thach drew from this session**, now in the Phase 3
    header: run both the mutation check and the doubt-review in every
    remaining session. 19 mutants passed while all three criticals were live,
    and the mutation check separately found three decision points the review
    never raised. Neither technique substitutes for the other.
  - **The one to remember: a comment asserting an invariant is not the
    invariant.** `members.py` carried a comment explaining that the gap key
    "carries characters `normalize_text` can never produce", which is true of
    the grouping key and was then quietly undone three lines later, where the
    set logic keyed on the display name instead. The comment described the
    design; the code did something else; the test that existed for exactly
    this case passed because its fixture had two members and therefore skipped
    the filter entirely.
- 2026-09-23, Phase 3 session 3C2 (normalise the customer key): edited -
  `shared/transactions.py` (new `customer_identity` and
  `merged_identity_count`), `stages/analyze/metrics_core.py`,
  `stages/analyze/metrics_customers.py`, `stages/diagnose/lever.py`,
  `stages/diagnose/bridge.py`, `stages/diagnose/signals.py`,
  `docs/AI_PIPELINE.md` 7.6, `docs/CONTRACTS.md` 7; new -
  `tests/shared/test_customer_identity.py` (13 tests).
  - **The six call sites**, all now keyed on `customer_identity`: stage 2's
    `_active_customers` (metrics_core) and the RFM table that feeds
    segments and new-vs-returning (metrics_customers); stage 3's
    `period_totals` and `customer_revenue` (lever), `_first_activity`
    (bridge) and `monthly_series` (signals). `_unattributed` still tests the
    RAW column with `is_blank`, which is correct: normalisation leaves a blank
    blank, and those rows are unattributed either way.
  - **No existing test changed**, so none was weakened - the requirement was
    met vacuously, which is itself the useful finding: no fixture in the repo
    had ever used two spellings of one customer, which is exactly why the
    defect survived to 3C.
  - **The mutation check was worth more than a doubt-review here.** Reverting
    each call site one at a time showed that two of the six were not actually
    protected by the new tests. The fixture split a customer only across
    months, so November held one spelling per customer and a raw count there
    is 3 anyway; only October, where two spellings coexist, tells the
    implementations apart. Same lesson as 3C in a new shape: a test that
    passes against both the right and the wrong code is not evidence, and
    reverting a call site is the cheapest way to ask.
  - `metrics.json` files already on disk are not rewritten; a run keeps its
    old figures until it is re-analysed.
- 2026-09-23, Phase 3 session 3C (metric tree, step 5): new -
  `stages/diagnose/{shapley,lever,bridge,pvm,tree}.py`,
  `tests/stages/diagnose/{test_shapley_and_lever,test_bridge_and_pvm}.py`;
  rewritten - `contracts/diagnosis.py`, `tests/contracts/test_diagnosis.py`;
  edited - `shared/transactions.py`, `stages/diagnose/{inputs,thresholds}.py`,
  `docs/CONTRACTS.md` 7 + 10, `docs/AI_PIPELINE.md` 7.6.
  - **`tests/contracts/test_diagnosis.py` was rewritten, as the brief
    anticipated.** It pinned the pre-3A shape, and the tests naming
    `decomposition`, `root_cause`, `ruled_out` and `secondary` could not
    survive blocks that no longer exist. Every rule that still applies is
    still tested and none was weakened: the four degraded-mode tests are
    unchanged in substance (the AI blocks are all-or-nothing; a dropped key
    must not parse as a degraded run), and the file gained tests for the new
    invariants - a level whose factors do not match its formula, a null lens
    with no recorded reason, `masked_shift_alert: false` on an absent tree,
    and a blocked run still carrying analysis blocks.
  - **Two decisions Thach made before implementation**, both now in
    AI_PIPELINE 7.6: a zero-order period makes lever level 1 inconclusive
    while zero identified customers with orders present takes the two-factor
    fallback; and a customer is active if they have any counted row whatever
    the sign, with no clamping, which also keeps "active" identical to stage
    2's. His two riders are implemented too - `gross_to_net` and
    `masked_shift_alert` are null rather than false when the tree is missing,
    and the count of new customers whose first-ever row is a refund is
    recorded as a left-censoring hint in evidence only.
  - **The lesson worth keeping from the doubt-review: a passing exactness
    test proves nothing on its own.** Three of the tests I wrote were green
    for the wrong reason. `test_gross_to_net_is_the_documented_ratio`
    re-implemented the formula in its own body and never called the function
    it was named after. `test_pvm_ignores_returns_...` refunded at the same
    price as the sale, so the lens returned the same answer with the bug and
    without it - it was green *under the defect it exists to catch*. And the
    whole-tree reconciliation test ran on a fixture with no returns at all,
    where `delta_gross` and `delta_net` are the same number, so an
    implementation that totalled the product lens to net revenue passed the
    one test whose job is to keep the two apart. A decomposition that returns
    all zeros reconciles perfectly; "the parts sum to the total" is only
    evidence when the total is independently known and the parts are not
    trivially zero. Mutation testing is what surfaced all three, and is worth
    repeating in 3D and 3E.
  - **Thach's two decisions after the review**, both recorded rather than
    implemented silently. (1) The bridge sign convention follows CONTRACTS:
    every term signed, identity the plain sum, so all of `diagnosis.json`
    obeys one rule - components sum to the change - shared with the Shapley
    contributions and the PVM effects. AI_PIPELINE 7.6 and DIAGNOSE_DESIGN
    5.5.5 were corrected in this session; they had stated the opposite, and an
    implementer following the prose would have negated two terms twice. A
    consequence was written into AI_PIPELINE 7.9 for 3F to build: the
    narration validator compares **magnitudes**, so "lost 219,000" matches
    `-219000.0` rather than spending the retry and degrading a run whose
    narration was correct. Fixing the convention also flushed out a dependent
    formula that would have shipped sign-flipped: **C2's contribution is now
    `lapsed(t) - lapsed(t-1)` with no outer negation** in both catalogs. The
    negation was correct only while `lapsed` was a positive magnitude; against
    a signed term it reports a POSITIVE contribution for a month in which more
    customers lapsed, in a hypothesis that can take the headline. C1 and C3
    needed no change. This is the second time in two sessions that a doc
    conflict hid a real defect rather than being merely untidy.
    (2) Customer keys are normalized in **both** stages
    as session 3C2, a prerequisite of 3D, not patched into stage 3 alone -
    doing that would have broken the stage 2 / stage 3 agreement that 3B's
    consistency test exists to protect.
  - I repeated the same mistake once more inside the fix: the first corrected
    test for the returns-first count asserted only the count, and with two
    customers a correct implementation and a sign-flipped one both report
    "1". Adding a third customer made the right answer and the wrong answer
    different numbers. Counting is not identifying.
- 2026-09-22, Phase 3 session 3B (foundations and steps 1-4): new -
  `shared/transactions.py`, `shared/contract_files.py`,
  `stages/diagnose/{thresholds,inputs,frame,trust,calendar_effect,signals}.py`,
  `tests/stages/diagnose/{diagnose_fixtures,test_frame_and_trust,
  test_calendar_and_signals}.py`; edited - `contracts/diagnosis.py` (five new
  models, `DiagnosisContract` untouched), `docs/AI_PIPELINE.md` 7.2-7.5 + 7.10,
  and the six stage-2 files that now import from `shared/`.
  - **Four judgment calls made rather than asked, flagged here for Thach to
    veto:**
    1. **Stage 3's "complete month" is stricter than stage 2's.** 2A picks the
       latest month fully elapsed by `data_end`; stage 3 additionally requires
       the month to be covered first-day-to-last, because a half-January in an
       XmR baseline invents a dip that the chart then reports as a signal. The
       two definitions therefore differ on purpose. Stage 3 still takes its
       `current`/`previous` pair from `metrics.json`, so the stages cannot
       disagree about *what* is being compared - only about which months are
       fit to be baseline.
    2. **`RequiredColumnMissingError` is re-exported from `metrics_core.py`**
       (with an `__all__` documenting it as deliberate). Four existing test
       files import it from there, and the brief's safety condition forbade
       editing any test. The alternative was editing tests to prove the
       refactor was safe, which would have destroyed the proof.
    3. **`normalize_text` and `product_identity` moved too**, beyond the five
       helpers the brief listed. `product_identity` (SKU else product name) is
       a row-level *definition* of what counts as one product, not a metric -
       if stage 3 re-implemented it, D2 and the product PVM could silently
       group differently from stage 2's Pareto over the same file.
    4. **The brief's own expectation about the calendar fallback is wrong**,
       and the code follows the spec rather than the brief: it says a 6-month
       file should fall back to `day_count`, but 6 months is about 150 history
       days, far past `CALENDAR_MIN_WEEKS`, so it correctly uses weekday
       weights. Only about two months of history triggers `day_count`. The
       test was written to the spec; say if the spec is what should change.
  - **An instruction from 3A was dropped and is only now recorded: scenario
    S11.** In the same 3A message where Thach accepted the threshold defaults,
    he asked for S11 (a 6-month file) to be added to the planted-cause suite.
    The other two items in that message were applied; S11 was not, and nothing
    in the repo recorded it, so a later session reading the docs would have
    found a suite of S0-S10 that looked complete and deliberate. It is now in
    DIAGNOSE_DESIGN section 8, AI_PIPELINE 7.11 and this checklist, with
    implementation in 3E. The lesson is about multi-item messages: when one
    message carries several instructions, each one needs its own landing place
    in the repo before the session closes, because a dropped item leaves no
    trace to notice later. This entry is the trace.
  - The three decisions Thach made during the doubt-review (inconclusive ->
    caution, the absolute margin floor, 3D2 scheduled not deferred) are now
    documented in AI_PIPELINE 7.3, 7.5 and 7.10 respectively, so the reasoning
    survives this session.
  - One test failure was a **bad fixture, not a bug**: `test_a_clean_file_is_
    trusted` broke when inconclusive started downgrading, because the fixture
    shop sold a single product and D2 cannot compare a one-product catalogue.
    The fixture was unrealistic; it gained 20 products. Worth remembering the
    shape - after a rule change, check whether the fixture or the rule is wrong
    before touching either.
- 2026-09-22, Phase 3 session 3A (SPECS UPDATE, docs only): `docs/CONTRACTS.md`
  section 7 + section 10 change log, `docs/AI_PIPELINE.md` sections 2, 7 and 9,
  `prompts/root_cause.md`, `docs/adr/0004-shapley-attribution.md`,
  `docs/adr/0005-pre-registered-hypothesis-catalog.md`,
  `docs/FIGMA_DESIGN_NOTES.md` header, the Phase 3 checklist above, and
  `tests/stages/diagnose/test_root_cause_prompt.py` (9 tests). Read `CLAUDE.md`,
  `docs/DIAGNOSE_DESIGN.md` in full, CONTRACTS 7, AI_PIPELINE 7,
  `prompts/root_cause.md`, `contracts/diagnosis.py` and `docs/adr/` first.
  - Six places where DIAGNOSE_DESIGN.md (written outside the repo) or the
    session brief disagreed with what is actually here, all flagged before
    writing rather than chosen silently:
    1. **No `root_cause` prompt test existed** to "update" - only
       `cleaning_plan` and `schema_inference` had one. Created, mirroring their
       pattern, so the rewritten prompt is pinned.
    2. **`run_id`** in the section 6 skeleton has no sibling precedent; dropped.
    3. **Docs now deliberately disagree with `contracts/diagnosis.py`** until
       3C. Recorded in CONTRACTS section 10, not left implicit.
    4. **AI_PIPELINE section 9 named the deleted `decomposition` block**; fixed,
       and split so stage 3's degraded mode (every deterministic block still
       written, including the code-written headline) reads differently from
       stage 4's.
    5. **C4 predates the "Needs Attention" segment** that 2B's doubt-review
       added. Not broken - it and "New" count towards neither group by design -
       but now stated in the catalog so 3E does not read it as an omission.
    6. **R3 and stage 2's `products.velocity` both report stockouts by
       different methods** and can legitimately disagree about one product.
       CONTRACTS section 7 now says which is which; stage 5 must not merge them.
  - Five decisions asked one at a time (DIAGNOSE_DESIGN section 12):
    1. **Thresholds**: accepted as written, with the
       `HISTORY_MAX_MONTHS`/`YOY_MODE_MIN_MONTHS` interaction documented.
    2. **Lapse window**: one period, keeping the customer-bridge identity exact.
       The 3-month alternative was rejected *because* it breaks that identity -
       a customer who bought two months ago would be neither lapsed nor
       retained, leaving their `prev` revenue unaccounted for. Output says
       "lapsed this period", never "churned".
    3. **ADR**: split into two, 0004 (Shapley) and 0005 (catalog), rather than
       one combined ADR - Thach's call, against the brief's singular wording.
    4. **Figma Insights frame**: after 3E, before Phase 6, recorded in
       FIGMA_DESIGN_NOTES.md's own pending list.
    5. **Second demo dataset**: Online Retail II, customer-sampled to ~40MB
       (full file is ~85-95MB as CSV, over the 50MB upload ceiling, so it would
       be rejected with FILE_TOO_LARGE before reaching stage 3). Thach added:
       keep no-Customer-ID rows too, invoice-sampled at the same rate, so the
       bridge's `unattributed` term has real data.
  - **`YOY_MODE_MIN_MONTHS` became a derived expression**, Thach's correction
    to the design doc and the one substantive change to section 9's table. A
    flat 25 would have excluded the very dataset chosen to demonstrate YoY mode:
    Online Retail II runs 2009-12-01 to 2011-12-09, which is 24 complete months
    (2011-12 is partial, so `current` is 2011-11). Both his claims were checked
    rather than taken on trust, and both hold. The derivation, verified
    independently: index complete months 1..N with `current` = N; a YoY point at
    month `m` needs month `m-12`, so YoY-capable baseline months run 13..N-1,
    giving `N - 13` points; requiring `XMR_MIN_BASELINE_POINTS` of them gives
    `N >= 12 + XMR_MIN_BASELINE_POINTS + 1` = 21. Written in code as that
    expression, not as `21`, so raising the baseline requirement cannot silently
    leave the YoY gate behind. At N=24 the dataset yields 11 YoY baseline
    points; the 26-month scenario suite is unaffected either way. S11, added
    later in the same session's thread, is the one exception: it truncates the
    build to 6 complete months and therefore sits far below this gate by
    design, which is the property it exists to test.
  - DIAGNOSE_DESIGN section 1.1's decomposition figures were re-derived from
    scratch before being quoted in ADR-0004, not copied: for the
    customers 1,000->600 / frequency 2.0->2.4 / AOV 50->70 example, sequential
    substitution gives customers anywhere in -40,000..-67,200 (68% spread) and
    AOV +24,000..+48,000 (exactly 2x) depending only on ordering, while Shapley
    gives -53,066.67 / +18,933.33 / +34,933.33 summing to exactly the +800
    change. All confirmed.
  - No doubt-review (DIAGNOSE_DESIGN section 11 marks session 1 "no"): this
    session wrote no algorithm - the arithmetic it quotes was verified by
    execution, and the design itself was already reviewed and approved by Thach
    before the session started.
  - pytest 1950 passed (up from 1941: the 9 new prompt tests), no existing test
    touched, none weakened. Vitest not re-run (no frontend code).
- 2026-09-22, Phase 2D (closes Phase 2): `stages/analyze/metrics_dimensions.py`
  + `stages/analyze/assemble.py` + `backend/app/services/metrics.py` +
  `backend/app/schemas.py` (`AnalyzeResponse`) + `backend/app/errors.py` +
  `backend/app/services/stage_errors.py` (`ANALYSIS_FAILED`) +
  `backend/app/routers/runs.py` (`POST /analyze`) +
  `tests/stages/analyze/test_metrics_dimensions.py` +
  `tests/stages/analyze/test_assemble.py` + `tests/backend/test_api_analyze.py`
  (8 + 7 = 15 new tests, hand-calculated / real-threaded, plus 1 existing test
  extended - see above). Read `CLAUDE.md`, `PROJECT_PLAN.md` section 12
  (including 2C's own notes on the 2D scope gap), `docs/CONTRACTS.md` section 6
  in full, `docs/SPECS.md` sections 3 and 8, and `metrics_core.py`/
  `metrics_customers.py`/`metrics_products.py` (2A-2C) before writing anything,
  per the session's own brief.
  - Two things the brief itself got wrong were caught before writing any code,
    both flagged back rather than acted on as stated:
    1. **`analyzed` needs no migration.** The brief said the state machine
       "wasn't defined" for Stage 2 completion and asked to confirm whether
       `analyzed` needs adding. It was already there: `RunStatus.ANALYZED` in
       `backend/app/models/run.py`, the very first migration's CHECK
       constraint (`2a9492d9af49_create_runs_table.py`, `2026-09-19`, before
       Stage 1 was even finished), `docs/SPECS.md` section 3's own state
       machine text (`uploaded -> profiled -> planned -> cleaned -> analyzed
       -> imported`), and `get_profile`'s own allowed-statuses list. Nothing
       to invent; just wire the transition. Same class of mistake as 2B's
       "docs/SPECS.md section 5.1" reference (a prior session's own notes,
       not the current docs, misremembered).
    2. **`by_dimension.country` has no data source at all**, a bigger gap
       than anything 2A-2C hit: `contracts/profile.py`'s `CanonicalField` has
       no `country` (product_name, sku, category, transaction_date, quantity,
       unit_price, transaction_type, supplier, customer, note, ignore -
       `category` is real, `country` never was), and `docs/SPECS.md` section 9
       never defined one either. Put to Thach before implementing: `country`
       always reports `[]` (the recommended, and only offered, option) rather
       than fabricate an attribution from an unrelated field; `category`
       computes normally. Revisit only if a country canonical field is added
       to the schema - a stage-1 change, out of scope here.
  - `contribution_pct`'s formula (docs/CONTRACTS.md section 6: "share of the
    total change attributable to that dimension member, signed, not share of
    revenue") was reverse-engineered by hand from the worked example before
    writing any code, then confirmed by the implementation reproducing both
    figures exactly: total_change = core.revenue_current - core.revenue_previous
    (-140000 in the example); member_change / total_change * 100 gives UK
    (940000-1020000)/-140000*100 = 57.14... ~= 57.1, and Home Decor
    (210000-268000)/-140000*100 = 41.43... ~= 41.4 - both match the documented
    figures to one decimal place. This is why `compute_dimension_metrics`
    takes `core: CoreMetrics` directly, unlike `compute_customer_metrics`/
    `compute_product_metrics` (2B/2C), which only needed `period`: the
    denominator is core's own total, not a locally-recomputed one, a real
    dependency the contract text itself names.
  - Not asked, decided directly: a category value is stripped and
    case-folded before grouping, the same pattern 2C's own doubt-review
    established for product identity (`metrics_dimensions.py`'s own
    `_dimension_changes`) - applied proactively this time since the bug
    class (formatting noise silently fragmenting one real value into
    several) was already proven, not just theorized; a blank category value
    is excluded, same "missing" definition `metrics_core.is_blank` already
    uses for `customer`; `by_dimension.category` is unbounded and includes a
    member with revenue in only one of the two periods (no positivity
    filter, unlike products' top_products - a category dropping to $0, or
    newly appearing, is exactly what this block exists to show).
  - `metrics_core.RequiredColumnMissingError` gained a structured
    `canonical_field` attribute (was message-text-only) so the backend layer
    can report which field is missing without parsing a sentence - needed
    for `ANALYSIS_FAILED`'s `details`, the first time a caller outside
    `stages/analyze` needed to inspect this exception programmatically.
  - metrics.json's write is a small, local atomic single-file helper in
    `assemble.py` (temp file, fsync, `os.replace`), not a reuse of
    `stages/ingest/contract_files.py`'s `write_files_atomically` - that
    would be a cross-stage import (CLAUDE.md 3.1), and this session only
    ever writes one file, so the multi-file rollback that helper also
    handles is more than 2D needs. Flagged, not acted on: stages 3-5 will
    each hit this same "one atomic file write" need again, and duplicating
    a ~15-line helper three more times is a real DRY smell worth revisiting
    (moving the single-file case to `shared/`) when stage 3 starts, not
    decided unilaterally this session since it would mean touching stage 1's
    already-shipped, tested code for a stage-2 session's convenience.
  - `POST /analyze` needs no transient claim status the way `execute`'s
    `cleaning` is (decided directly, not asked): the computation is pure and
    deterministic (no AI, docs/adr/0002) and metrics.json's write is atomic,
    so a crash mid-computation leaves the run exactly as it was - never
    "stuck" the way an abandoned `cleaning` claim could be. `RunWork.execution`
    (already-built "one piece of work at a time per run" infrastructure) is
    reused as-is to refuse a concurrent second call outright rather than let
    both redundantly compute; verified with a real `threading.Event`-based
    test mirroring `tests/backend/test_api_races.py`'s own technique for
    `execute`, not just asserted.
  - `ANALYSIS_FAILED` does NOT move the run to `failed`, unlike the seemingly
    parallel `CLEANING_FAILED` (decided directly, not asked, flagged for
    Thach to veto): `cleaned.csv` is still valid and downloadable when stage 2
    can't compute metrics (a missing `unit_price` mapping, or a NOT_INVENTORY
    file), so failing the whole run would be harsher than the situation
    warrants - mirrors how a NOT_INVENTORY run already keeps its `cleaned`
    status and downloads elsewhere in the product (docs/SPECS.md section 10).
    A NOT_INVENTORY file reaching `/analyze` at all is now checked explicitly
    (reusing `analysis.is_not_inventory`/`not_inventory_notice`, already built
    for stage 1), not left to surface as a confusing generic
    "missing canonical field" error.
  - **No doubt-driven review cycle run** (2A skipped, 2B and 2C each ran one
    that found real bugs; this session's own brief asked to decide and
    explain, given it mixes new arithmetic with mostly-assembly work): skipped,
    because every piece of genuinely new logic was independently verified by a
    stronger method than adversarial reading would add on top - the
    `contribution_pct` arithmetic against the documented worked example's own
    numbers (not just internally-consistent hand math, actual published
    figures), and the concurrency behavior against a real multi-threaded race,
    not a single-threaded mock. What's left (`assemble.py`, the router, the
    schema) is thin composition of already-reviewed pieces (2A-2C's builders;
    `run_state`, `RunWork`, `stage_errors` from 1G), not novel algorithmic
    surface like 2B's two-pass RFM re-snapshot or 2C's implied-stock
    derivation - both of which is exactly where those sessions' review cycles
    found real, non-obvious bugs. If a future session finds a bug in this
    session's code, this reasoning - not the size of the diff - is the thing
    to revisit.
  - pytest 1941 passed (up from 1925), `tests/test_architecture.py` included,
    no existing test touched or weakened (one extended, per above).
- 2026-09-22, Phase 2C: `stages/analyze/metrics_products.py` +
  `tests/stages/analyze/test_metrics_products.py` +
  `tests/stages/analyze/test_metrics_products_declines_and_velocity.py` +
  `tests/stages/analyze/products_fixtures.py` (shared test builders, same
  pattern as `tests/stages/ingest/cleaning_fixtures.py`; the test file was
  split in two - `products_fixtures.py` 26 lines, the two test files 237 and
  104 - to stay under CLAUDE.md section 5's ~300-line guideline after the
  doubt-review fix-up added more tests). 15 tests, hand-calculated, then 4
  more from the doubt-review cycle below - 19 total. Read `CLAUDE.md`,
  `PROJECT_PLAN.md` section 12, `docs/CONTRACTS.md` section 6 (the `products`
  block) and `metrics_core.py` (2A/2B) before writing anything, per the
  session's own brief.
  - Confirmed, same pattern as 2A/2B: `docs/SPECS.md` has no section defining
    Pareto/velocity beyond one line under section 4.5 ("last N=14 days"), and
    that line is for the live Dashboard (Phase 7, DB-backed, querying real
    "now") - a different surface than this per-run file analysis. Neither
    `top_products` nor `biggest_decliners` has a documented list-size cap
    anywhere either (the Dashboard's own "top-5" bar chart, also section 4.5,
    is that different surface's own number).
  - The most consequential gap, bigger than anything 2A/2B hit: `days_to_stockout`
    needs a current-stock-on-hand figure per product, but Stage 2 has no such
    canonical field at all, and SPECS section 9's only stock formula ("net in
    minus out, floored at 0") is textually scoped to Phase 7's DB import, not
    this stage - without resolving this, `days_to_stockout` cannot be computed
    by any method. Four decisions were put to Thach before implementing, all
    four answered with the recommended option:
    1. **Stockout data**: derive the same "net in minus out, floored at 0"
       balance from cleaned.csv's own whole-file transaction history instead
       of a DB - every "in" row adds, every counted/"out" row subtracts (a
       return's negative quantity nets back in automatically, same sign logic
       as 2A's revenue). Self-contained pandas, no DB, no cross-stage
       dependency.
    2. **Velocity window**: `period.current` (the calendar month every other
       block already uses), not the Dashboard's fixed 14-day window - a
       static file upload has no "now" to anchor a rolling window to.
    3. **Zero velocity**: a product with no measurable current-period
       velocity is omitted from `velocity` entirely (not a placeholder) -
       also answers the "only ever an 'in' row" edge case from the brief.
    4. **List size**: `top_products` and `biggest_decliners` are each capped
       at the 10 highest-ranked entries, ties broken by product name.
       `velocity` stays unbounded (a stockout-risk inventory, not a
       leaderboard) - decided directly, not asked, since the brief's list-size
       question was specifically about the two ranked lists.
  - Not asked, decided directly: product identity is the row's `sku` value
    when present, else `product_name` (docs/AI_PIPELINE.md section 11's
    business-key precedent, extended here to a per-row fallback since a
    mapped sku column can still have blank cells row by row); `top_products`
    excludes a net-negative-revenue product (not a "top" performer);
    `biggest_decliners`' population is exactly products with nonzero
    previous-period revenue, reusing `metrics_core.pct_change`'s own
    zero-denominator convention rather than a new one; ties in both ranked
    lists break on product name for a deterministic, hand-checkable order.
  - `metrics_core.py` touched again (2A/2B's own 54 tests re-run unchanged
    after, all still green): `ParsedTransactions` gained a `valid` field
    (date/quantity/price present, regardless of transaction_type - needed to
    isolate "in" rows for the stock derivation, since `counted` alone can't
    be inverted back to "in" without it); `_require_column`/`_pct_change`
    promoted to public `require_column`/`pct_change` so this module reuses
    them verbatim instead of redefining "what's a valid decline" or "what
    happens when a required column is unmapped."
  - **Doubt-driven review cycle run** (this module introduces a genuinely new
    kind of computation - deriving an implied stock balance from transaction
    history, no precedent anywhere else in the codebase - plus several
    interacting groupby operations across current/previous/all-time row
    subsets and two different cap/tie-break implementations; comparable
    complexity to 2B, which found real bugs): one fresh-context adversarial
    cycle, cross-model offered and declined again (no gemini/codex CLI
    installed here). 4 findings, all reconciled as valid and fixed:
    - Fixed: product identity mixed `sku` and `product_name` values in one
      flat string namespace with no normalization - a SKU that happened to
      read the same as an unrelated product's name would silently merge
      them, and whitespace/case noise on the same real SKU
      ("SKU1"/" SKU1"/"sku1") fragmented one product into several duplicate
      rows. Fixed by stripping+case-folding the identity value before
      grouping (the same pattern `metrics_core.py` already uses for
      transaction_type matching) and keeping the sku- and name-sourced halves
      in separate namespaces (`sku:`/`name:` prefixes) so they can never
      collide.
    - Fixed: `TopProduct.units` used `int()`, which truncates a fractional
      summed quantity toward zero (a systematic downward bias) rather than
      rounding to the nearest whole unit - quantity is not guaranteed
      integral anywhere in the schema. Now uses `round()`.
    - Fixed: `Pareto`'s population (every product with any current-period
      revenue, including net-negative or net-zero) disagreed with
      `top_products`' population (revenue > 0 only) - two numbers in the same
      contract object that a reader would expect to relate to each other
      could describe different sets of products, understating concentration
      by more than half in the reviewer's reproduction. Pareto now applies
      the same revenue > 0 filter.
    - The reviewer investigated and explicitly dropped a fifth candidate (period
      drift between `product_metrics_for_run`'s own `select_period` call and
      core's) after verifying it is not practically reproducible - noted here
      only because it shows the review actually ran code rather than pattern-matching.
    - All 4 fixes are each pinned by a new hand-calculated regression test;
      the 15 pre-existing tests were re-run unchanged after every fix and
      stayed green throughout.
  - pytest 1925 passed (up from 1910), `tests/test_architecture.py` included,
    no existing test touched, none weakened.
- 2026-09-22, Phase 2B: `stages/analyze/metrics_customers.py` +
  `tests/stages/analyze/test_metrics_customers.py` (33 tests, hand-calculated,
  then 4 more from the doubt-review cycle below - 37 total). Read `CLAUDE.md`,
  `PROJECT_PLAN.md` section 12, `docs/CONTRACTS.md` section 6 (the `customers`
  block), `docs/SPECS.md` section 7.3, and 2A's `metrics_core.py` before
  writing anything, per the session's own brief.
  - The brief's own `docs/SPECS.md` section 5.1 reference for segment
    thresholds does not exist - section 5 is entirely the stage-1 confirmation
    contract, and section 7.3 is the *only* RFM text anywhere in the docs
    ("RFM scoring uses quintiles on the run's own data; the reference date is
    max(transaction_date) + 1 day"). The exact R/F thresholds Thach listed in
    the brief are not written down anywhere in the current docs (grepped
    `PROJECT_PLAN.md`, `docs/AI_PIPELINE.md`, `prompts/strategy.md` too - only
    the five segment *names* appear, in the Phase 2 checklist line and the AI
    strategy prompt's mapping-logic examples, never the thresholds) - same
    "confirm before assuming the old design is current" situation 2A hit.
  - Four decisions were put to Thach before implementing, all four answered
    with the recommended option:
    1. **Segment coverage**: the five given rules (Champions R>=4&F>=4, Loyal
       R>=3&F>=3, At-risk R<=2&F>=3, Hibernating R<=2&F<=2, New R>=4&F<=1)
       leave 4 of the 25 R x F combinations unclassified - (3,1), (3,2),
       (4,2), (5,2), a customer who is reasonably recent but
       low-to-middling frequency. A 6th catch-all segment, "Needs Attention",
       covers them; `segment` is a plain string in the contract, so a sixth
       value validates fine.
    2. **customers_previous**: docs/CONTRACTS.md's `SegmentSummary` has this
       field ("period-over-period comparison") but nothing says what
       "previous" means for a segment count, since RFM is normally one
       whole-history snapshot. Re-runs the same RFM pipeline restricted to
       transactions through the end of the previous period, anchored the day
       after it, and counts customers per segment under that earlier
       snapshot - shows real segment migration, matching the worked example
       (129 Champions last period -> 118 now).
    3. **Return-only customer**: a customer whose only-ever revenue-counted
       row is a return (negative quantity, 2A's convention) is scored and
       segmented like anyone else - no special case; their Monetary is
       honestly negative.
    4. **N=1 customer**: with 2-4 distinct customers, rank-based quintiles
       already spread them across 1-5 without error (verified empirically
       before asking, not assumed). With exactly one customer in the whole
       file, pandas' `qcut` cannot form bins at all (nothing to rank
       against); that lone customer scores 5 and 5 (best available).
  - Not asked, decided directly: RFM (Recency/Frequency/Monetary/segment) is
    one whole-file snapshot anchored at `metrics_core`'s own `Period.data_end
    + 1 day` (directly reused, not recomputed - confirmed this matches
    docs/CONTRACTS.md section 6's own worked example exactly: data_end
    2011-12-09 -> rfm_reference_date 2011-12-10), not scoped to
    current/previous period, since section 7.3 says "the run's own data" and
    a real quintile requires one full, stable population to bin against;
    quintiles use `.rank(method="first")` before `qcut` so ties spread across
    all 5 buckets instead of collapsing into one (a genuine "quintile" needs
    five equal-sized groups) - decided directly rather than asked, since it
    follows from the word "quintile" itself, not a business judgment call; no
    mapped `customer` column degrades the whole block to
    `segments: []`/`new_vs_returning` all zero rather than raise, mirroring
    2A's `active_customers = 0` in the same situation (`rfm_reference_date`
    is still computed - it doesn't depend on `customer`).
  - `metrics_core.py` refactored (2A's own tests re-run unchanged after, all
    still green) to extract `ParsedTransactions`/`parse_transactions`: the
    row-parsing and revenue-scope logic 2A already had, now a function both
    modules call instead of `metrics_customers.py` re-deriving it - same
    stage package, so importing it is not a cross-stage dependency (CLAUDE.md
    3.1). `compute_core_metrics`'s own behavior is unchanged; `select_period`
    also reused as-is.
  - **Doubt-driven review cycle run** (Thach's call was left to judgment,
    given this module's two-pass "previous snapshot" re-computation, rank-based
    tie-breaking and date-boundary arithmetic have more surface area for a
    subtle, hard-to-notice bug than 2A's did): one fresh-context adversarial
    cycle, cross-model offered and declined (neither `gemini` nor `codex` CLI
    is installed here). 4 findings, reconciled against the artifact text
    (not rubber-stamped):
    - Fixed: `NewVsReturning`'s "empty" result was a single mutable
      module-level singleton returned by reference from three call sites
      (`ContractModel` is not frozen) - an in-place mutation on one run's
      degraded result could have leaked into every other run's for the rest
      of the process's life. Now a fresh instance per call
      (`_empty_new_vs_returning()`).
    - Fixed: a whitespace-only `customer` cell was not treated as missing
      (only a true null was), fabricating a phantom customer with their own
      segment row - more consequential here than in 2A's mere off-by-one
      count. `docs/AI_PIPELINE.md` already defines "missing" as "null, or
      holding only spaces" elsewhere, so the fix (a shared `is_blank` helper
      in `metrics_core.py`) extends an existing convention rather than
      inventing one - and was backported into 2A's `_active_customers` too,
      so both blocks agree on who counts as an identified customer.
    - Fixed: `revenue_share_pct` divided by the raw signed whole-file total,
      so a net-negative dataset (returns outweighing sales) flipped every
      segment's sign - a small revenue-*positive* segment showed a negative
      share while the loss-making one showed over 100%. Now divides by the
      magnitude (`abs(total_monetary)`), a no-op for the ordinary all-positive
      case, sign-consistent otherwise.
    - Not fixed, classified as noise (already-decided in 2A, not a new bug):
      a missing `unit_price` mapping makes `parse_transactions` raise
      `RequiredColumnMissingError`, same as 2A's `compute_core_metrics` - this
      module correctly inherits that rather than fabricating a 0 Monetary or
      a misleadingly-empty customers block. Documented explicitly in the
      module docstring since the reviewer's question ("is this really
      intended") was fair even though the answer was already settled.
    - All 3 fixes are each pinned by a new hand-calculated regression test;
      the 50 pre-existing tests (2A's 17 + 2B's 33) were re-run unchanged
      after every fix and stayed green throughout.
  - pytest 1910 passed (up from 1873), `tests/test_architecture.py` included,
    no existing test touched, none weakened.
- 2026-09-22, Phase 2A: `stages/analyze/metrics_core.py` + `tests/stages/analyze/
  test_metrics_core.py` (17 tests, all hand-calculated). Read `CLAUDE.md`,
  `PROJECT_PLAN.md` section 12, `docs/CONTRACTS.md` section 6, `docs/adr/0002`,
  `CONSTRAINTS.md`, `contracts/metrics.py`, `docs/SPECS.md` section 9,
  `docs/FIGMA_DESIGN_NOTES.md`'s flagged open question, `docs/AI_PIPELINE.md`
  sections 5/11/12 and `tests/test_architecture.py` before writing anything, per
  the session's own brief.
  - Four decisions were flagged as genuinely unresolved (no config.yaml exists,
    no period field in `Settings`, and FIGMA_DESIGN_NOTES.md section 8 explicitly
    says "SPECS does not define how returns are identified... decide before Phase
    6") and put to Thach before implementing, all four answered:
    1. **Period selection** (no config anywhere; must come from the data itself,
       since stages stay framework-free and runnable standalone): `current` is the
       latest calendar month fully elapsed by `data_end` (`select_period` in
       `metrics_core.py`); `previous` is the month before it. Reproduces
       docs/CONTRACTS.md section 6's own worked example exactly (data_end
       2011-12-09 -> current 2011-11, the partial December excluded) - a
       dedicated test pins this. Falls back to `now`'s month when the data holds
       no parseable date at all.
    2. **Revenue scope**: an "in"-type row (stock coming back, e.g. a supplier
       restock) is excluded from revenue/orders/AOV entirely, never subtracted -
       `transaction_type` is stock movement direction only (docs/AI_PIPELINE.md
       section 5), never a returns concept, so folding it into a signed sum would
       misreport a restock as negative revenue. Unmapped transaction_type, or an
       unrecognised per-row value, defaults to "out" (docs/SPECS.md section 9).
    3. **Return detection**: a return is a revenue-counted row with negative
       quantity (the common POS convention of a negative-quantity sale line).
       `return_rate` = count of those rows / count of revenue-counted rows in the
       period. Works whether or not `transaction_type` is mapped, since it only
       depends on quantity's sign - the safer "always 0.0, deferred" alternative
       was offered and not chosen.
    4. **Zero denominators**: `revenue_change_pct` with `revenue_previous == 0`,
       and `aov`/`return_rate` with `orders == 0`, all report `0.0` - never a
       manufactured "100% growth from nothing" figure. A dedicated test
       (`test_zero_orders_in_the_previous_period_...`) pins this against the
       rejected alternative.
  - Not asked, decided directly (lower-stakes, no real alternative to weigh):
    `orders` = count of revenue-counted rows (the canonical schema has no
    invoice/order-id field to group by, so a row is the only unit available);
    `active_customers` = count of distinct `customer` values among
    revenue-counted rows in the period, `0` when `customer` isn't mapped (same
    "no signal -> 0" pattern as the return-rate design, just not one FIGMA_DESIGN
    _NOTES.md had already flagged); `unit_price` not being mapped (legal at stage
    1 - only `product_name`/`transaction_date`/`quantity` are required fields,
    docs/AI_PIPELINE.md section 11) raises `RequiredColumnMissingError`, since
    revenue cannot be computed without a price and pandas must not invent one
    (docs/adr/0002); a row whose date, quantity or price does not parse is
    excluded from every period-based number rather than guessed at (a real gap:
    docs/AI_PIPELINE.md section 12 notes a plan cannot require `transaction_date`
    to be parsed, so cleaned.csv's date column is not guaranteed to be ISO 8601)
    - `select_period`'s `data_start`/`data_end` still use every parseable date in
    the file, not just revenue-counted rows, since they describe the dataset's
    own span, not revenue's.
  - `compute_core_metrics(df, column_mapping, now=None)` is pure (no disk I/O);
    `core_metrics_for_run(runs_root, run_id, now=None)` reads `cleaned.csv` +
    `cleaning_report.json` via `shared/run_registry` and calls it - mirrors
    `profiling.py`'s `profile_csv`/`profile_run` split. Neither writes anything:
    assembling and writing the full `metrics.json` (the `customers`, `products`
    and `by_dimension` blocks too) is 2B-2D. `cleaned.csv` is read with
    `dtype=str` and every needed column converted explicitly in this module
    (`pd.to_datetime`/`pd.to_numeric`, `errors="coerce"`), the same "read every
    value as raw text" approach `profiling.py` uses for `raw.csv`, since nothing
    guarantees stage 1 already cast these columns.
  - No doubt-driven review cycle run: the session's own brief said to skip it if
    the hand-checked tests alone gave confidence once implemented, and 17 tests
    covering every branch (both zero-denominator paths, unmapped
    transaction_type/customer, case/whitespace-insensitive type matching, an
    unrecognised type value, unparseable dates/quantities/prices, a fully empty
    dataframe, all three required-column-missing paths, and the exact CONTRACTS.md
    worked example) did.
  - A pandas gotcha hit and fixed during testing, not part of any design
    decision: `df[type_col].str...` raised `AttributeError` on an empty or
    all-missing column, because an empty/NaN-only column can read back as
    `float64`, and `.str` only works on object/string dtype. Fixed with
    `.astype(object)` before `.str`; a dedicated empty-dataframe test still
    passes.

Earlier ask, now met - the real `.env` needed two lines `.env.example` had already
gained (`PREVIEW_CACHE_MAX_MB`, `PREVIEW_CACHE_TTL_SECONDS`):
```
PREVIEW_CACHE_MAX_MB=300
PREVIEW_CACHE_TTL_SECONDS=900
```
**Notes:**
- 2026-09-22, `docs/adr/` session (docs-only, no application code; git tree
  clean at start), using `documentation-and-adrs` (Wave 2). Read
  `PROJECT_PLAN.md` section 2 and the Phase 0/1 history, `docs/CONTRACTS.md`
  section 1 and `docs/AI_PIPELINE.md` sections 1-3 first, rather than
  summarizing from memory. Wrote exactly the three ADRs the Phase 2 checklist
  line names, in `docs/adr/` (the location that line and this session's brief
  both name; the skill's own default is `docs/decisions/`, but its own
  instructions say an established convention overrides that default, and
  `docs/adr/` was already established by the checklist line before this
  session ran):
  - `0001-stage-isolation-single-repo.md`: cites the 0A session's own
    Notes bullet ("ONE repo with five independent stage packages... instead
    of five separate repos... Splitting into separate repos later stays
    possible precisely because of that boundary") as the decision record,
    and section 2's rationale line, for the alternative-considered section
    the brief asked for.
  - `0002-pandas-computes-ai-interprets.md`: sourced from `CLAUDE.md` 3.2 and
    `docs/AI_PIPELINE.md` sections 1 and 3 (bounded input, the whitelisted
    transform catalog, the validate-retry-degrade policy).
  - `0003-model-selection-policy.md`: sourced from `docs/AI_PIPELINE.md`
    section 2 (`MODEL_REASONING`/`MODEL_BULK` split, `MODEL_BULK` unused in
    v1 but required like every other setting) and `backend/app/config.py` /
    `backend/app/services/analysis.py` (confirmed by reading the code, not
    assumed, that both of v1's stage-1 AI calls pass `settings.model_reasoning`
    today). States the policy, not a model id, as the brief asked.
  Each ADR uses the skill's own template (Status, Date, Context, Decision,
  Alternatives Considered, Consequences), with Consequences split into
  Benefits and Trade-offs accepted per the brief - the skill's default
  template does not separate them, this session's brief explicitly asked to.
  Linked from both `CLAUDE.md` (section 1's doc index, section 2's model line,
  3.1's and 3.2's "Why" paragraphs now point at the matching ADR instead of
  restating the rationale inline) and `PROJECT_PLAN.md` (section 2 and
  section 7), per the "docs hold the rule, ADRs hold the why" split the Phase
  2 checklist line itself states. Both checklist items now ticked (Wave 2
  install; `docs/adr/`). pytest 1856 / Vitest 54 re-run and unchanged (no
  application code touched). Thach confirmed in chat: Phase 2A is the next
  step right after this session, resolving the ambiguity the Wave 2 session
  had flagged between this checklist line and Phase 2A.
- 2026-09-22, skills Wave 2 install (tooling session, no application code;
  git tree was clean at start; Phase 1 1A-1G complete confirmed the trigger
  condition). CLI syntax re-verified with `npx skills add --help` rather than
  assumed from Wave 1: unchanged (`add -a <agent> --copy -y -s <skill>`, same
  as `docs/SKILLS.md` section 5). Installed exactly the four Wave 2 skills
  (`code-review-and-quality`, `code-simplification`, `documentation-and-adrs`,
  `ci-cd-and-automation`) via one `npx skills add` call; `skills-lock.json`
  updated automatically with correct source/hash entries, no manual edit
  needed. `npx skills list` shows all 14 (10 Wave 1 + 4 Wave 2), no more, no
  less. The two Wave 2 personas (`test-engineer`, `code-reviewer`) were copied
  by hand into the new `.claude/agents/` (this is the first session with any
  persona - Wave 1 installed no personas, so there was no literal prior
  precedent for "same mechanism"; used the same clone-to-scratch-copy-delete
  approach `docs/SKILLS.md` section 5 describes for skills): cloned
  `addyosmani/agent-skills` into the session scratchpad, copied
  `agents/code-reviewer.md` and `agents/test-engineer.md`, deleted the clone.
  Both files' "Composition" section links to `../docs/agents.md`, which
  resolves to `.claude/docs/agents.md` from `.claude/agents/` - that file is
  not installed (`docs/SKILLS.md` section 2 only names `.claude/references/`
  for shared checklists, nothing about agent docs), so the link is dangling;
  left as-is, flagged for Thach, not fixed since it is outside this session's
  named scope. `performance-checklist.md` copied into `.claude/references/`
  the same way; confirmed `code-review-and-quality/SKILL.md`'s
  `../../references/performance-checklist.md` link resolves. Added
  `.github/workflows/ci.yml` (ubuntu-latest, Python 3.14 matching
  `backend/requirements.txt`'s own pin, `pip install -r backend/requirements.txt`
  then `pytest` - `tests/test_architecture.py` runs as part of that, already
  collected by `pytest.ini`'s `testpaths`). No secrets or services:
  `tests/conftest.py` sets `DATABASE_URL=sqlite://` and every other required
  `Settings` field via `os.environ` before any test imports `app.config`, so
  CI never touches Postgres or needs `.env`. Decided without asking, for Thach
  to veto: triggers on both `push` (any branch) and `pull_request` into `main`,
  not `push` alone as the session brief's literal wording said - standard CI
  practice, costs nothing extra, still needs no secrets either way. Checked
  `CLAUDE.md`'s "Skill precedence" section against all four new skills' own
  text (grepped for commit/push/autonomous-run language): no new conflicts,
  so left unchanged, matching what `docs/SKILLS.md` predicted. Verified after
  every install step: pytest 1856 passed (repo root, via `backend/venv`'s
  `python -m pytest`), Vitest 54 passed across 9 files - both counts unchanged
  from before this session, as expected, since nothing in `stages/`,
  `backend/app/`, or `frontend/src/` was touched.
- 2026-09-22, later the same day: a bug fix + a Preview pane rebuild, both on
  the Review screen the previous session built.
  - **Bug fix** (found manually testing Review with real Kaggle data): the AI
    mapped a "Payment Method" column (Cash / Credit Card / Digital Wallet) to
    canonical_field `transaction_type`, which `docs/SPECS.md` section 9
    defines as stock movement direction (`in`/`out`) - an unrelated concept
    the field's own name (containing "type" and "transaction") invites
    confusing it with. Nothing downstream would have caught it: the mapped
    value is an ordinary string either way, so this would have silently
    corrupted `current_stock` once Phase 7 exists. Fixed in
    `prompts/schema_inference.md` (new "CANONICAL FIELD NOTES" section: the
    definition, what it is not, a concrete negative example mapped to
    `ignore`) and `docs/AI_PIPELINE.md` section 5 (same clarification,
    inline). Regression test: `tests/stages/ingest/test_schema_inference_prompt.py`
    (4 tests, mirrors the existing `test_cleaning_plan_prompt.py` pattern of
    testing a prompt's own content, since the fix is prompt wording and there
    is no code to unit-test). A real-API check that the model now avoids the
    wrong mapping (like 1C's one-off) was not run this session - offered to
    Thach, not done, given the token-spend note two bullets down.
  - **Preview pane rebuild**: `design/mockups/Review.png` was re-exported
    (file-modified today) but `docs/FIGMA_DESIGN_NOTES.md` was not updated
    alongside it (unchanged since 2026-09-19, no "Preview pane" section). The
    missing section 7 was written from the new PNG plus Thach's own
    description before building against it (old section 7 "Handoff notes" ->
    8, "Design principles" -> 9; nothing elsewhere in the repo references
    either by number). `frontend/src/components/PreviewPane.tsx` rebuilt as
    one table (was Before/After side by side): a pinned Row column, only
    columns changed in the displayed sample shown by default (the rest behind
    "Show unchanged columns (N)"), a dotted underline as the non-color signal
    on a changed/filled cell (SPECS section 11), the original value and the
    action that ran in a tooltip on hover AND keyboard focus
    (`tabindex="0"`, `aria-describedby`), numeric columns right-aligned with
    a trailing ".0" dropped, the row-count chip labeled "(full file,
    projected)". New domain module `frontend/src/domain/previewDisplay.ts`.
    Dropped-row reasons ("No qty", "Duplicate") are real now, not the
    fabricated-vs-honest tradeoff the previous session's Notes flagged -
    `PreviewResult` still carries no reason field, but the reason is now
    *derived* from the plan actually submitted plus the row's own "before"
    values (both already available once `PreviewPane` takes the `plan` as a
    prop): "Duplicate" when `remove_exact_duplicates` is planned and another
    displayed row has identical "before" values (checked first, since that
    action runs before any column action in the fixed execution order,
    `docs/AI_PIPELINE.md` section 6); otherwise "No `<field>`" when a
    required field's column has `drop_rows_missing` and this row is blank
    there; otherwise "Dropped", claiming nothing further, when neither is
    determinable from the 20 rows on screen (a duplicate whose pair fell
    outside them, or a non-required column's `drop_rows_missing`). 12 new
    domain tests + 6 new component tests
    (`frontend/src/domain/previewDisplay.test.ts`,
    `frontend/src/components/PreviewPane.test.tsx`).
  - Checked, as asked: whether "no cells appeared visually tinted" in the old
    preview was a pre-existing bug. The old component's code did set the
    `preview-cell--changed`/`--added`/`--removed` classes correctly, and the
    previous session's own live-browser screenshot (before this rebuild)
    showed yellow/green/red cells rendering. Does not look like a code bug;
    moot now regardless, since that component no longer exists - if it
    recurs with real data after this rebuild, it needs its own look with the
    exact file that showed it.
  - **No AI tokens spent this session** (contrast with the paragraph below):
    `.env`'s `ANTHROPIC_API_KEY` was checked before touching anything
    upload-related, and no browser/upload flow was driven this time - Thach
    asked to re-verify live himself. Both dev servers were started only to
    confirm a clean boot (`/health`, then left running for Thach to check),
    never driven past that.
- 2026-09-22 Stage-1 frontend session (scoped exception, not Phase 6 - see the note
  under Phase 6 above): built `frontend/src/pages/{Upload,Analyzing,Review,Results}Page.tsx`
  wired to the real 1G API, per `docs/FIGMA_DESIGN_NOTES.md` frames `Upload` (`7:851`),
  `Upload - Analyzing` (`7:955`), `Review` and its 4 variant frames, `Results` (`7:1098`),
  using the design tokens in that file's section 4 (`frontend/src/styles/tokens.css`).
  No router: `App.tsx` is a small screen state machine (Upload -> Analyzing -> Review ->
  Results), since only these 3 screens exist and Insights/Dashboard need Phase 2-5 data
  that does not exist yet. 33 Vitest tests (up from 9): upload validation, the
  plan-edit-to-preview debounce (fake timers), required-field gating, NOT_INVENTORY
  mapping-disabled mode, error-state rendering per `design/mockups/Errors.png`, and an
  `App.test.tsx` integration path including the branch that must skip `POST /plan`
  when the schema step came back AI_UNAVAILABLE (no `schema_inference.json` written,
  so `/plan` would itself answer INVALID_STATE). `npx tsc -b` and `npm run lint` clean.
- **Real AI tokens were spent, by accident.** The repo's real `.env` (not `.env.example`)
  already held a real `ANTHROPIC_API_KEY`, not the placeholder. Manual browser
  verification of the Upload -> Review flow (CLAUDE.md "Definition of Done": verify at
  runtime, not only via tests) was run without first checking the key, so the one
  upload made 2 real calls (schema inference, cleaning plan) against Thach's account -
  small (this project's earlier 1C real-call note: about 3 cents for one call), but a
  real miss of CLAUDE.md section 8 / the DoD item ("run with a fake `ANTHROPIC_API_KEY`
  ... real tokens are spent only when Thach asks"). Flagged to Thach the moment it was
  noticed, mid-session; no further AI-triggering action (re-upload, "Try AI again") was
  taken afterward - the rest of the manual check (editing the plan, the debounced
  preview, Confirm & Clean, the Results downloads) used `/preview` and `/execute`,
  neither of which calls the AI. Lesson for every future session: check which key is in
  the real `.env` before the first browser-driven upload.
- Two gaps in the built API were found while building the screens the API is supposed
  to serve, and fixed rather than worked around, since both are already implied by
  `docs/SPECS.md` section 8 and needed by SPECS section 4.2/4.3, not new scope:
  - `GET /api/runs/{id}/profile` (`app/services/analysis.py:get_profile`,
    `tests/backend/test_api_profile.py`, 4 tests): the Review screen's dataset summary
    strip (SPECS 4.2 A: rows, columns, duplicate rows, missing %) and the Analyzing
    screen's row/column count need `profile.json`, which no endpoint returned;
    `schema_inference.json` cannot substitute (capped at 25 columns, no dataset
    totals). Read-only, no work claim; INVALID_STATE before the run is profiled,
    EXPIRED if the file is gone.
  - `GET /api/runs/{id}/download/cleaned.csv` (`app/services/downloads.py`,
    `tests/backend/test_api_downloads.py`, 5 tests): the Results screen's CSV download
    (SPECS 4.3) - `execute`'s response never carried `cleaned.csv` itself, only the
    report (SPECS 8 already says "download urls" belong on that response; 1G did not
    build them). The uploaded filename is user-supplied and only its extension was
    checked at upload (SEC-1), so the download filename is sanitized to
    `[A-Za-z0-9._-]` before it reaches the `Content-Disposition` header (a test proves
    a filename with `"`, `;` and CRLF cannot inject a header). `cleaning_report.json`
    needed no endpoint: `execute`'s response already carries the full report, so its
    download button serializes that in the browser.
  These were decided without asking, for Thach to veto: both are thin, read-only,
  reuse the existing state-machine/error patterns (`run_state.require_status`,
  `stage_errors.files_gone`), and were each given the same test coverage a 1G endpoint
  got.
- UI simplifications versus the mockups, decided without asking, for Thach to veto:
  - The Action cell's params editor is inline under the dropdown, not a floating
    popover (`design/mockups/Review - Edit Action.png`); `fix_negative` is one dropdown
    entry ("Fix negative values") with an inline strategy select, not the mockup's two
    entries ("Flag negatives (keep)" / "Fix negative values..."). Same data submitted
    either way - the difference is only how many clicks reach the params.
  - The mockup's "abs" strategy label is "Set to 0"; the transform actually replaces a
    negative with its absolute value (-5 -> 5), never 0
    (`stages/ingest/transforms.py fix_negative`, `strategy="abs"`). Built as "Make
    positive (absolute value)" instead of copying a label that misdescribes the data.
    Flagged for Thach to fix the mockup text or confirm the behavior is what he wants.
  - The preview pane's dropped-row reasons ("No qty", "Dup. row") and the "What ran"
    table's expanded row (specific row numbers, "Reason recorded per row:
    missing_required_field(quantity)") in the mockups are not data
    `PreviewResult`/`ChangeLogEntry` actually carry (`stages/ingest/preview.py`: a
    dropped row's `changed` is forced empty, with no reason code; `ChangeLogEntry` has
    no row list). Built honestly instead of invented: the preview shows "Row dropped"
    with no reason, and a "What ran" row only expands when it has real params to show.
    Worth a contract addition later if Thach wants the mockup's level of detail.
  - `drop_column` entries are shown one per column (`docs/CONTRACTS.md` section 5: one
    `ChangeLogEntry` per column dropped), not aggregated into the mockup's single
    "4 columns" row - aggregating would need grouping rules the contract does not
    define.
  - Column issue badge severity (low/medium/high, the badge color) is a client-side
    heuristic (`frontend/src/domain/issueSeverity.ts`): `ColumnIssue`
    (`docs/CONTRACTS.md` section 3) carries no severity, only `DatasetIssue` does. The
    rule: `missing_values` is high on a required field or at >= 5% elsewhere (the same
    5% line SPECS section 6 uses for impute-vs-Unknown), medium below that; cosmetic
    codes (whitespace, case, near-duplicates, exact duplicates) are low; codes that can
    corrupt a column or drop data unnoticed (`all_null_column`,
    `non_numeric_in_numeric`) are high; everything else is medium. Matches every badge
    color in `design/mockups/Review.png`'s sample data by construction, but is a rule
    this session invented, not one SPECS or CONTRACTS states - for Thach to veto or
    move into SPECS if it should bind the backend too.
  - Upload's client-side size check uses the SPECS section 1 ceiling (50MB), not the
    server's actual configured `MAX_UPLOAD_MB` (open question left by the original 6A
    line: no second source of truth for the real, possibly lower, limit exists on the
    frontend). A file over 50MB is rejected before upload; a file the server's real
    limit rejects (if lower than 50MB) still gets the server's real FILE_TOO_LARGE
    answer, shown the same way. `frontend/src/domain/upload.ts` has the reasoning.
- Not built this session (deliberately out of scope, per the session's own brief):
  dataset-actions editing (`remove_exact_duplicates` / `flag_duplicate_keys` are shown
  nowhere in the UI; a manually-built plan always starts with none, an AI plan keeps
  whatever it proposed); an accessibility or Vitest coverage pass beyond what the tests
  above already exercise; i18n (none needed, SPECS 11 says English only).
- 1G decisions (Thach): none asked mid-session; the design choices (profiling folded
  into `analyze-schema`, preview/execute allowed from `profiled` for a hand-built plan,
  the NOT_INVENTORY waiver, byte-budgeted cache over a cell-budgeted one, a per-run
  per-step AI attempt cap) are explained in the 1G checklist line and in `docs/SPECS.md`
  section 3's new state table for Thach to veto.
- 1G review (one doubt-driven cycle, fresh reviewer, cross-model declined by Thach):
  5 high-severity findings (a leaked server path, a run strandable in `cleaning`, an
  unbounded AI call count with a state-mismatch race, one preview able to starve the
  server) and 6 medium (the cache counted cells not bytes; an evict during a read could
  restore a stale frame; a NUL byte in a run id reached PostgreSQL as a 500; a
  concurrent `analyze-schema` on a fresh run read a stale status; `MemoryError`/`OSError`
  wrongly failed the run for good; the real `.env` needed updating). All fixed, each
  with a reproducing test (`tests/backend/test_api_hardening.py`,
  `test_api_recovery.py`, `test_run_state_hardening.py`); the fixes were then checked by
  mutation testing (every mutant killed), not reviewed a second time, by the same
  one-cycle decision as 1C/1F.
- One bug found while splitting long test files after the review (not in the reviewed
  code itself): Python 3.14 defers annotation evaluation (PEP 649), so a missing
  `import` used only in a type hint or inside a lambda is not a `NameError` until that
  code actually runs - a test with a stray missing import can pass for the wrong reason
  if the code under test also happens to answer 500. Fixed by pinning the real cause
  with `caplog` in `test_a_missing_prompt_template_is_a_500_that_shows_no_server_path`.
- Old 1F notes (kept for history):
- 1F decisions (Thach): a date written with a UTC offset keeps its date and time as
  written and drops the offset; `drop_rows_missing` is its own step before the
  imputations (`EXECUTION_ORDER`, AI_PIPELINE section 6); execute rejects a plan that
  drops a column mapped to a required field (the preview allows it); one review cycle
  only, cross-model skipped.
- 1F choices made without a question, for Thach to veto: execute also writes
  `plan_final.json` (CONTRACTS lists it, nothing owned it); the preview is its own
  module (`preview.py`, 300-line rule) and `cleaning.py` holds the shared engine;
  `cleaned.csv` keeps the source column names, writes ISO dates and holds the `__flag_*`
  columns; `column_mapping` omits ignored and dropped columns; a plan that leaves no
  row is refused; a parsed year outside 1900-2100, `now`, `today` and a bare time are not
  dates (the range is my choice: say if it should differ); a `standardize_categories`
  mapping may not target an empty text or a missing-value token, and the report warns
  (`text_reads_as_missing`) when cleaned text would read back as missing; a file whose
  rows have an extra field that holds data is rejected (PARSE_FAILED).
- 1F review (one doubt-driven cycle, fresh reviewer, cross-model skipped): 17 findings.
  The high one was in 1B: a trailing delimiter on every row made pandas use the first
  column as the index, so `profile.json` was wrong, the preview crashed and execute wrote
  shifted data. Fixed with tests, all in AI_PIPELINE section 12: that, the rollback when a
  rename fails (Windows refuses to replace a file another process holds open), flag
  columns overwriting a source column or left all False, infinity counted as a number,
  `now` / `10:30` / year-less dates, offset forms like `+10` and `UTC`, an honest
  change-log detail, wide files (execution 45 s -> 17 s, the problem-row search bounded by
  cells), `write_contract` line endings, `fsync`. Not fixed: a blank required cell
  survives (one action per column, `drop_rows_missing` drops only missing), concurrent
  executes (1G claims the run), the preview date format on a sampled file, preview over
  3 s on files near 50 MB (the read alone is 2.6 s: cache the frame), nanoseconds
  truncated. The fixes made after the review were not reviewed again, by decision.
- Tests changed in 1F, none deleted or skipped: two 1E tests that pinned "mixed offsets
  fail until Thach decides" now test the decided behavior; `test_the_order_is_the_documented_one`
  has the new order (every earlier pair is still asserted); one `test_contract_files`
  expectation followed the rollback (a failed second rename no longer leaves the first
  file behind).
- 1E in short (details in AI_PIPELINE sections 11 and 12): pandas overwrites the AI's
  issue counts, with no retry on a difference, and a count of 0 removes the issue; the
  business key is sku (else product name) + transaction date + transaction type; the
  plan step's answer checks report every problem in the one retry message
  (`plan_checks.py`); three review cycles found a plan dropping the column its own
  `flag_duplicate_keys` needs, a lone UTF-16 surrogate crashing the write (fixed once, in
  `shared/ai_client.py`) and more. The plan prompt met the real model once (Thach, a
  25-row file, no retry needed, no required field imputed).
- Decided by Thach at the end of 1F: the date range 1900-2100 stays;
  `near_duplicate_labels` is reported only for text and categorical columns (so a number,
  an identifier, a date and a boolean are outside it; "A+" and "A-" in a text column
  still count as near-duplicates, which was accepted); `drop_rows_missing` also drops a
  cell of only spaces; one action per column stays until the review screen (6B) shows
  what is needed; CLEANING_FAILED (422) for a run that fails on its data; a column-count
  limit is left to 8A.
- Accepted limits of 1E's answer checks: an impossible issue count still uses the retry,
  counts describe the raw file, rows with a missing key part count as sharing the key,
  `examples` and `domain_reasoning` are not number-checked, the recount has no cost bound
  (about 3 s per 300,000 rows of unique text over 11 codes).
- Tooling: heredocs through the Bash tool collapse `\\` to `\`, so a script that writes
  escape sequences (`\ud800`, regexes) must be written with the file-writing tool, not a
  heredoc.
- 1D catalog decisions: `cells_affected` counts cells this action changed or
  removed, `rows_affected` counts rows it dropped or marked, and one action
  fills one of the two (the table in `transforms.py`'s docstring is the list).
  An action that ran and changed nothing is still logged with two zeros
  (Thach). A failed cast or parse leaves the cell missing and adds a boolean
  flag column `__flag_<kind>__<column>`, added only when something is flagged.
  Dropping rows keeps the row index, so a gap shows where a row was.
- 1D `cast_type` targets are integer / float / string / boolean, and
  `normalize_case` modes title / lower / upper; both are data in
  `transform_catalog.py` for 1E to validate a plan against. Casting "3.7" to
  integer is a flagged failure, never a 4.
- 1D issue counts: every one of the 15 issue codes has a source for its number:
  three come from `profile.json`, eleven from `issue_counts.count_column_issue`
  and `duplicate_business_key` from `count_duplicate_business_key`. 1E wired
  them into `ai_schema.py` through `issue_recount.py` (see the 1E notes).
- 1D counting definitions worth knowing: `invalid_dates` and
  `mixed_date_formats` count 0 unless more than half the column's values
  parse as dates (otherwise every product-name column would report its whole
  length); `inconsistent_case` counts cells that are not the dominant
  spelling of their case-folded label; `near_duplicate_labels` ignores case,
  spacing and punctuation but never counts a pure case difference, so the two
  codes stay disjoint; `mixed_types` counts the minority kind when a column
  holds both numbers and text.
- 1D sample rows: `_problem_masks` now has six kinds, not three (added: text
  in a column of numbers, padded whitespace, an unparseable date). Because
  six kinds share the 30 rows, `PER_PROBLEM_KIND` went from 5 to 3, so
  ordinary rows are still visible - the semantic types are inferred from
  them. `test_each_problem_kind_is_capped_at_five` was renamed and rewritten
  for the new cap (a stricter assertion, not a weaker one); the four new
  kinds have their own tests.
- 1D performance: deciding a column's kind uses a 500-row probe
  (`column_kinds.PROBE_ROWS`) before converting the whole column, the same
  trade-off `profiling.py` already makes for its numeric probe. Measured on
  this machine: `pd.to_datetime(format="mixed")` is about 0.025 s per 200k
  values and `pd.to_numeric` about 0.1 s, so an unprobed scan of 25 columns
  of a 50MB file would have cost seconds.
- 1C call policy (`docs/AI_PIPELINE.md` sections 1-3 updated): no sampling
  parameters, because `claude-sonnet-5` rejects `temperature` with a 400;
  thinking disabled, so the 3000 tokens and 30 s cover the JSON answer; the
  SDK's own retries off, so every retry is counted against the run budget.
  The caller passes the API key, the model id and the run's `RetryBudget`
  (`shared/` may not read settings, SEC-4). Structured outputs
  (`output_config.format`) are a later candidate, to be checked with a real
  call first.
- 1C degraded mode: `AIUnavailable.reason` is one of timeout, network, auth,
  rate_limited, api_error, invalid_response, truncated, refused. Truncated
  and refused answers are not retried; API failures do not spend the retry.
  The reason is logged and carried by the exception, never written to a
  contract (Thach). A degraded run writes no `schema_inference.json` and
  deletes an earlier one, so no later step reads a valid-looking file; other
  errors (a broken template) leave it alone.
- 1C bounded input: 25 columns (not 60: more does not fit in 3000 output
  tokens), 30 stratified sample rows, every value cut to 100 characters
  including the mark. Sample rows go as a header plus positional value
  lists, so 25 names are not repeated 30 times. Column names are never cut,
  because the answer must repeat them exactly; a pathological header belongs
  to 8A.
- 1C answer checks (all use the single retry): every sent column exactly
  once, one canonical field per column, column issue counts within the rows
  and dataset counts within the cells, and the figures the profile holds
  (`missing_values` vs `null_count`/`null_pct` with a 0.1 tolerance,
  `duplicate_rows`, `all_null_column`) must match. Any other code must have
  `pct: null`. The AI's names are matched back to the file's exact names
  when trimming and case-folding leaves one candidate. Answers are validated
  strictly (`true` is not 1.0), and unknown extra keys are ignored on
  purpose, since they are dropped rather than stored.
- 1C review: three doubt-driven cycles (the skill's limit), each with a
  fresh-context reviewer; cross-model skipped by Thach each time. Cycle 1
  found the unbounded value size and the unchecked figures; cycle 2 the
  dataset counts measured in cells and the stale-profile hole; cycle 3 a
  real bug in cycle 2's own fix (an `elif` chain skipped the `pct` rule for
  `all_null_column`). Everything actionable is fixed with tests. Accepted
  trade-offs: issue `examples` have no length cap, and the dataset figures
  cover the whole file while only 25 columns are described (the profile the
  AI sees now says how many).
- Why call 1 was rejected in that check: the model put cell values in issue
  `examples` and wrote a real `null` there, which `list[str]` refuses (the
  schema layer in `shared/ai_client.py`, five times). The retry turned it into
  the string "null" and passed. `prompts/schema_inference.md` now says
  `examples` are row references ("row 4"), never a value and never null, so
  that the run's single shared retry is not spent on formatting.
- 1C verified against the real API once (2026-09-20, Thach ran a throwaway
  script on a 12-row messy CSV, about 3 cents): call 1 was rejected, the
  retry corrected itself and passed both the schema and the stage checks, and
  the model obeyed the new `pct` rule. It distinguished `duplicate_rows` from
  `duplicate_business_key` and found `mixed_date_formats` and
  `near_duplicate_labels` in the planted dirt. Everything else in the suite
  is mocked; this was the only real call.
- CONSTRAINTS F4 is active: `tests/conftest.py` blocks the real httpx2/httpx
  transports and records every attempt, so a call the SDK or our client
  swallows still fails the test at teardown. Verified with a probe that
  caught the error and still failed.
- 1B decisions (Thach): missing = the 19 pandas 3.0 default NA tokens, listed
  explicitly in `NA_TOKENS` (so "NA" counts as missing, even when it means
  Namibia); `sample_values` = up to 5 values per column from evenly spaced
  rows (`i * (n - 1) // 4`), raw text, missing kept as null.
- 1B design: the file is read once with every value as text, so
  `top_values`/`sample_values` show the file's own spelling ("0012",
  "12.50"). A column is numeric when it has at least one value and every
  non-missing value is a finite number; then `dtype` is pandas' `int64` /
  `float64` (float64 when there are gaps) and the stats are filled, else
  `dtype` is `str` and the stats are null. Quartiles and median use pandas'
  default linear interpolation. `unique_count` compares raw text ("8.5" and
  "8.50" are two values). Top values: count descending, ties by value.
  Percentages are not rounded.
- 1B encoding and delimiter: UTF-16 BOM -> `utf-16`; else strict UTF-8 (BOM
  stripped from the first column name); else `latin-1` (SPECS section 10).
  The latin-1 warning belongs in `cleaning_report.warnings`
  (`encoding_fallback`, CONTRACTS section 5), so 1B only records
  `encoding_used` and 1F emits the warning (written into the 1F line).
  Delimiter: `csv.Sniffer` over `, ; \t |`; a header with none of them is a
  single-column file; otherwise `CsvParseError`.
- 1B errors: the stage raises `EmptyCsvError` (`code = EMPTY_FILE`: no lines,
  or header-only) and `CsvParseError` (`code = PARSE_FAILED`: a row with too
  many fields, invalid UTF-16, undeterminable delimiter). 1G maps them to the
  envelope (written into the 1G line). `profile.json` is written atomically
  (temp file + `os.replace`).
- 1B performance (SPECS section 11: profiling a 50MB file under 3 s): a
  generated realistic 50 MB CSV (712,645 rows x 9 columns) took 5.1 s at
  first; two result-preserving optimizations brought it to 3.3 s (a
  200-value probe that rejects text columns before a full numeric
  conversion, and reusing `value_counts` for unique count and top values);
  `pyarrow==25.0.1` (Thach approved; pandas 3 then uses it as its string
  backend, no code change) brought it to 2.86 s. The margin is thin (~5%);
  re-measure if profiling grows. No timing test in the suite (it would be
  machine-dependent and flaky).
- One-off security check for the new dependency (Thach's request, 1B), not
  the official W3 install: pip-audit 2.10.1 ran from a throwaway venv that was
  deleted afterwards (project venv unchanged, 52 packages). `pyarrow==25.0.1`:
  no known vulnerabilities. Whole project venv: one finding, pip 26.1.2
  `PYSEC-2026-3721` (fixed in 26.2); pip is the venv installer, not a
  `requirements.txt` dependency. Fixed with Thach's approval: the project
  venv now has pip 26.2.1. A recreated venv must upgrade pip the same way.
- 1A2 schema: `runs` has exactly the 7 SPECS section 9 columns, with no JSON
  columns (contract files live on disk). Types behave the same on SQLite and
  PostgreSQL: `id` is `String(36)` (the canonical UUID string, not a native
  UUID); `status` is an enum of the SPECS section 3 states stored as VARCHAR
  + CHECK `ck_runs_run_status` (`create_constraint=True` explicitly: its
  default is False in SQLAlchemy 2.0); timestamps use `UtcDateTime` (naive
  UTC stored, aware UTC returned; the TZDateTime pattern from the SQLAlchemy
  docs), because SQLite keeps no timezone.
- 1A2 consistency rule: a `runs` row exists only if its `raw.csv` is complete
  on disk. Order: file (fsynced) -> flush -> commit. A flush failure means
  nothing was committed, so the directory is deleted. A commit failure has an
  unknown outcome, so the directory is kept; a directory without a row is
  garbage for the 8B retention cleanup. Both branches are tested.
- Alembic: run it from the repo root with
  `backend\venv\Scripts\alembic -c backend\alembic.ini <command>`. `env.py`
  reads `DATABASE_URL` through `Settings` (no URL in `alembic.ini`), or uses
  a connection passed by tests. `render_as_batch=True` because tests migrate
  SQLite. Migrations never import the models (the first one uses
  `sa.DateTime()` where the model has `UtcDateTime`). Tests: upgrade, no
  drift against the models (`compare_metadata`), the CHECK constraint name
  (autogenerate does not compare CHECKs), and downgrade.
- Tests never touch a real database: `tests/conftest.py` sets
  `DATABASE_URL=sqlite://`, and `create_app(settings, engine=...)` takes an
  injected in-memory engine.
- Launch decision (1A): the dev server runs from the REPO ROOT with
  `python -m uvicorn app.main:app --app-dir backend --reload`, the same two
  path entries as `pytest.ini` (root + `backend`). Starting it from
  `backend/` now fails with `No module named 'shared'`, which is intended.
  CLAUDE.md section 8 and README updated. pytest still works from both.
- 1A upload rules: checks run type -> size -> empty -> binary. The type check
  creates no run; any later rejection deletes the run directory. The file is
  copied in 64 KB chunks with a running byte count, never read whole.
  Limitation: FastAPI/python-multipart has already spooled the whole body
  before the handler runs, so an oversized upload is still received in full
  (to a temp file) before the 413; a request-size limit at the server or proxy
  belongs to 8B abuse guards.
- 1A decisions (Thach): endpoint first, DB in 1A2; SQLite for tests;
  header-only files rejected in 1B; NUL-byte check for binary files in 1A.
  Messages are English UI copy in `services/uploads.py`.
- F10 now also covers `npm run lint` in `frontend/` (approved by Thach).
- 0D frontend setup: one `.env` at the repo root for both apps. Vite reads it
  through `envDir: '..'`, and only `VITE_*` variables reach the browser.
  `VITE_API_BASE_URL` is in `.env.example` and must be in every local `.env`
  (without it the page says "not configured").
  `server.strictPort: true` so Vite never drifts off the port listed in
  `ALLOWED_ORIGINS`. Layout: `src/api/` (fetch + response checks),
  `src/components/`; tests next to the code (`*.test.ts(x)`, jsdom).
- 0D template changes: the current `create-vite` react-ts template has no
  `"strict": true` (added to both tsconfigs for F5) and ships oxlint (swapped
  for ESLint + typescript-eslint `strictTypeChecked` + react-hooks, as Thach
  asked). The config is `eslint.config.ts` (no plain .js), which needs the dev
  dependency `jiti`; ESLint's native TS loading is still behind an unstable
  flag. `npm run lint` uses `--max-warnings=0`. ESLint enforces F6 too:
  planted `any`, `@ts-ignore` and a reasonless `@ts-expect-error` were all
  errors.
- Floors now active: F5 (`npx tsc -b`), F6, Vitest in F1 (`npx vitest run` or
  `npm test`), W4 (`npm audit --audit-level=high`). `CONSTRAINTS.md` F10 still
  names only ruff; adding `npm run lint` in `frontend/` to F10 is a tightening
  (allowed by F11) for Thach to approve in a docs session.
- 0C2 design: `shared/` may not import the backend, so the registry does not
  read settings. The caller passes an absolute runs root (from 1A on, a
  service passes `settings.runs_dir`); a relative root raises `ValueError`.
  `config.py` anchors a relative `RUNS_DIR` to its existing `REPO_ROOT`, the
  only place that finds the repo root. `REPO_ROOT` was not moved into
  `shared/`, because `config.py` would then import `shared`, which is not
  on `sys.path` when uvicorn runs from `backend/` (see the Phase 1 launch
  note below).
- Registry API: `create_run(runs_root) -> NewRun(run_id, path)`, `run_dir`,
  `run_file` (the file need not exist; stages write to it). Only a canonical
  lowercase UUID is accepted as a run id (`InvalidRunIdError`, a
  `ValueError` -> 400 later), so an id from a URL can never climb out of
  `runs/` (SPECS section 11: never user-supplied paths); a well-formed id with
  no directory raises `RunNotFoundError` (a `LookupError` -> 404 later).
  Filenames must be bare names.
- Tests never touch the real `runs/`: `tests/conftest.py` sets `RUNS_DIR` to
  an absolute temp dir outside the repo, and a test in
  `tests/backend/test_config.py` fails if that changes. Registry tests use
  `tmp_path`.
- 0C rules, decided with Thach: stages may not import another stage, `app` /
  `backend`, or fastapi / starlette / sqlalchemy / alembic; a file directly in
  `stages/` (not in a stage) may import no stage, so it cannot become a back
  door; `contracts/` may import none of `stages`, `shared`, `app`,
  `backend`, the frameworks; `shared/` may import neither `stages` nor
  `app` / `backend`. `backend/app/` is walked but has no rule yet (a
  routers -> services rule could be added there later).
- How the guard works: the walker and the rules live in
  `tests/test_architecture.py` itself, so the F3 review of that file covers
  them. Stage ownership comes from the path (no list of stage names).
  Relative imports are resolved; `from stages import x` counts as importing
  `stages.x`; imports under `TYPE_CHECKING` or inside functions count;
  `importlib.import_module` / `__import__` count only with a literal name (a
  computed name cannot be resolved statically). `app.*` and `backend.*` are
  the same boundary, because `backend/` is on the path.
- Fixtures: `tests/architecture_fixtures/violations/` (18 files, one
  violation each, all listed in the test) and `clean/`. They are parsed,
  never imported, and are outside the four scanned roots; a test asserts
  that. A test also asserts that all four real roots are reached, so a typo
  in `SCAN_ROOTS` cannot silently scan nothing. F3 verified: an import
  planted in `stages/ingest/` and in `contracts/` failed the build, then was
  removed.
- 0B decisions (Thach): unknown fields are ignored (`extra="ignore"` on
  `ContractModel`, matching CONTRACTS section 10); strict AI-output checks
  stay in the stages (1C/1E/3B/4B). `report.json` layers are
  `dict[str, Any]` until 5A. Degraded AI in stages 3-4: the AI blocks are
  required keys with nullable values, all null or all filled; CONTRACTS
  sections 7, 8 and 10 and the SPECS section 10 error row were amended in
  place at `1.0` (no file existed yet), recorded in the SPECS change log.
- 0B conventions for later contract work: `_base.py` holds `ContractFile`
  (`schema_version` must be `1.x`, `generated_at` must carry a timezone) and
  the shared types (`Percent`, `UnitInterval`, `YearMonth`, ...). Enums are
  `Literal`s, only where the docs define one (AI_PIPELINE sections 5-6,
  plan `source`); everything else is `str`. Bounds only where definitional
  (counts >= 0, percentages of a whole, confidence, `low <= point <= high`,
  chart `len(x) == len(y)`); revenue, shares and return rates are unbounded
  because refunds can make them negative. Nullable fields are required keys
  (no default) so a dropped key never parses as `null`.
- Follow-ups found in 0B live in their owning sub-phase lines in section 5:
  1C (every profiled column exactly once), 2A/2C (zero denominators vs
  required numbers), 3A (insufficient-data decomposition), 4B (AI call when
  `ai_findings` is null), 5A (layer structure, "unavailable", `ai_calls`),
  1C (why the AI was unavailable: carried by `AIUnavailable`, logged, and
  maybe recorded in degraded files). Not addressed (run-model question, not a contract one): a
  re-run of stage 3 after stage 4 ran degraded leaves `forecast.json` stale.
- `pydantic==2.13.5` is now pinned in `backend/requirements.txt` (it was
  already installed as a FastAPI dependency; `contracts/` imports it
  directly). Pytest adds the repo root to the path, so `tests/contracts/`
  imports `contracts` without an install step.
- Wave 1 has no personas, so `.claude/agents/` does not exist yet;
  doubt-driven-development's mention of `agents/` is prose, not a link. Personas
  arrive with Wave 2 (test-engineer, code-reviewer) and Wave 4 (security-auditor).
- `CONSTRAINTS.md` exists at enforcement level "written only": the agent runs
  the checks at task end, Thach before committing. Not installed yet, each
  needing Thach's approval: `pytest-cov` + `diff-cover` (W1/W2; add
  `coverage.xml` to `.gitignore` then), `pip-audit` (W3), a project ruff config
  (F10). W4 (`npm audit`, from 0D) confirmed by Thach on 2026-09-19.
- The 8 open items from the SPECS UPDATE doubt review now live in their
  owning sub-phase lines in section 5, so they survive Notes rewrites: 0C
  (`app`/`backend` imports from `stages/`/`shared/`), 1A (binary renamed to
  `.csv`), 1C (`shared/ai_client.py` + F4 guard fixture), 5B (extend SEC-3 to
  CSV-derived text; SPECS first), 6A (size limit without a second source of
  truth), 8B (rate-limited run-state transition; trusted proxy, value set in
  9A), 9A (CORS trailing slash, Vercel preview domains).
- Local root folder is renamed by Thach manually to
  `C:\Users\Happy\Desktop\dataclarity` (Windows cannot rename a folder that
  Claude Code / VS Code / a terminal is using). A venv hardcodes its absolute
  path (`pyvenv.cfg`, `activate*`, every `Scripts\*.exe` launcher such as
  `uvicorn.exe`, `pytest.exe`, `pip.exe`), so after the rename `backend\venv` is
  recreated (same name `venv`) and requirements reinstalled.
- Claude Code history and memory are keyed by folder path: after the rename,
  `claude -c` in the new folder will not find old sessions. This section is the
  handover.
- Images in `design/mockups/*.png` may still show "CleanStock" as drawn text;
  they are binary Figma exports and are not edited here.
- 0A delivered: git repo (`main`), empty packages for `contracts/`, `stages/*`,
  `shared/`, `backend/app/{routers,services,models}`; `create_app(settings)`
  factory + `GET /health` in `routers/health.py`; `config.py` (pydantic-settings,
  every variable required, no defaults, `.env` read from repo root,
  `hide_input_in_errors` so the API key never lands in logs); CORS from
  `ALLOWED_ORIGINS` (comma-separated); `pytest.ini` at repo root.
- `.env` lives at the REPO ROOT only (not `backend/`); created with dev values,
  `ANTHROPIC_API_KEY` left as a placeholder for Thach. First startup failure
  (8 missing fields) was simply the missing `.env`, not a path bug.
- Local Python is 3.14 (via `py`); `python` on PATH is the Microsoft Store stub.
  `backend/requirements.txt` is pinned to versions verified on 3.14.
- `pytest` works from the repo root AND from `backend/` (CLAUDE.md section 8).
  pytest honours `testpaths` only when invoked from the rootdir, so the root
  `conftest.py` redirects a bare run from a subdirectory to `testpaths`; runs
  inside `tests/` or with explicit paths are untouched. `pytest.ini` adds `.`
  and `backend` to the path.
- `tests/conftest.py` forces fake env values before `app.main` is imported, so
  the suite never reads the real `.env` or API key.
- Not created on purpose: `runs/` (created on the first run through
  `shared/run_registry.py`; gitignored).
- pytest shows 1 DeprecationWarning from `starlette/testclient.py` (anyio
  renamed `BlockingPortal`). Third-party, not our code; ignore until starlette
  updates. Do not count it as a new lint warning.
- Running a command via `!` in Claude Code uses Bash: use forward slashes
  (`backend/venv/Scripts/python -m pytest`), backslashes get stripped.
- No Python linter is configured yet (a global ruff config flags `app` imports
  as third-party); consider adding a ruff config when Thach approves. The
  frontend has ESLint since 0D.
- Architecture decision made this session: ONE repo with five independent stage
  packages and contract files between them, instead of five separate repos.
  Boundary enforced by `tests/test_architecture.py` (Phase 0C). Splitting into
  separate repos later stays possible precisely because of that boundary.
- Figma frames are being designed by Thach in parallel. Frontend phases (6A-6F)
  must not start until `docs/FIGMA_DESIGN_NOTES.md` has real node ids.
- No auth in v1; public demo protected by rate limits and retention cleanup.
- Forecasting (Phase 4A) deliberately uses interpretable statistics, not ML
  models, so every number in the report can be explained in an interview.

## 13. Definition of Done for every sub-phase

The standing bar every sub-phase clears before it is ticked. It adapts
`.claude/references/definition-of-done.md` to this project. `CLAUDE.md` section 7
is canonical: this checklist links to its items and adds only the items the
reference contributes (runtime verification, contract discipline, decision
records). If the two ever differ, `CLAUDE.md` section 7 applies. The **DoD:** line
under each phase in section 5 is that phase's acceptance criteria, checked in
addition to this list.

- [ ] Scope: only the sub-phase's items are implemented (`CLAUDE.md` section 7
      item 1)
- [ ] Tests written and passing: new code in `stages/` or
      `backend/app/services/` has tests with hand-checked expectations
      (`CLAUDE.md` section 7 item 3 and `CLAUDE.md` section 5); every suite
      passes (`CLAUDE.md` section 7 item 2)
- [ ] Constraints respected: every Floor row in `CONSTRAINTS.md` passes,
      including no new lint warnings (`CLAUDE.md` section 7 item 4; checked by
      command once a ruff config exists); Warn rows are reported to Thach
- [ ] Verified at runtime where the sub-phase delivers something runnable: a
      stage via `python -m stages.<name> --run <run_id>`, an endpoint via the
      running API, not only via tests. Run with a fake `ANTHROPIC_API_KEY` so
      every AI step takes the degraded path; real tokens are spent only when
      Thach asks
- [ ] Contracts: any contract change follows `docs/CONTRACTS.md` section 10
- [ ] Decision records: from Phase 2 on, an architectural decision worth
      keeping gets an ADR in `docs/adr/`
- [ ] Current Status updated: checklist ticked and section 12 rewritten with the
      file-editing tool (`CLAUDE.md` section 7 item 5; section 6 of this file)
- [ ] Key decisions explained to Thach in Vietnamese (`CLAUDE.md` section 7
      item 6)
- [ ] Commit proposed: exact `git add`, `git commit -m "..."` and `git push`
      commands given to Thach ("Skill precedence" in `CLAUDE.md`)

Reference items that do not apply in v1: observability beyond basic logging
(`docs/SKILLS.md` section 4), feature flags (none in this project), and a
rollback path (only for the Phase 9 deploy, via the Wave 4 skills). "Human
review before merge" is met because Thach reviews and types every git command.
