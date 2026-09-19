# SPECS UPDATE PROMPT (reusable)

Use this prompt every time the project documents need to change. Paste
everything below the line into a new Claude Code session, then replace the
CHANGE REQUEST block at the bottom. The block is pre-filled for the first use:
integrating the engineering skills.

---

This session updates DataClarity's project documents. It is a documentation
session: write no application code and change no tests.

Before doing anything, read in this order:
1. `CLAUDE.md`
2. `PROJECT_PLAN.md`, including the Current Status section
3. `docs/SPECS.md`
4. `docs/CONTRACTS.md`
5. `docs/AI_PIPELINE.md`
6. `docs/SKILLS.md`
7. `CONSTRAINTS.md` and `docs/adr/` if they exist

SOURCE OF TRUTH

- `docs/SPECS.md`: what the product must do (functional and non-functional)
- `docs/CONTRACTS.md` + `contracts/`: the data exchanged between stages
- `PROJECT_PLAN.md`: order of work, phases, status
- `CLAUDE.md`: how the agent must work in this repo
- `CONSTRAINTS.md`: the measurable quality bar
Each fact lives in exactly one of these files; the others link to it instead of
repeating it.

PROCESS (follow in order, stop where marked)

1. Impact analysis. For the CHANGE REQUEST, produce a table with columns:
   file, section, current text (short), proposed change, reason. Include files
   that need NO change if a reader might expect one, and say why.
2. Conflict check. List anything in the request that contradicts an existing
   decision, a contract, a "never cut" item, or another document. For each,
   propose a resolution. Never resolve a conflict silently.
3. Doubt review. Run doubt-driven-development on the impact analysis. Report
   what the reviewer challenged and what you changed because of it.
4. STOP. Present steps 1 to 3 to me and wait for my approval or edits.
5. Apply only the approved changes, with minimal edits. Keep existing section
   numbering; append new sections at the end of the relevant file rather than
   renumbering. Never delete a requirement unless the request says so explicitly.
6. Contracts rule. If a change touches a JSON contract, update
   `docs/CONTRACTS.md` and the Pydantic model description together, bump that
   contract's `schema_version`, and add a plan item to update the model and its
   tests in a later coding session.
7. Consistency pass. Re-read all changed files and confirm that names, numbers,
   file paths and phase ids match across documents. Report any mismatch.
8. Log the change. Append a dated entry to a "Change log" section at the end of
   `docs/SPECS.md` (create it if missing): what changed, why, which files.

WORKING STYLE (mandatory)

- Explain the changes and their reasons to me in Vietnamese in chat. All file
  content stays in English.
- Ask me 2 short comprehension-check questions about the changes and wait for
  my answers.
- Before ending: update the Current Status section of `PROJECT_PLAN.md`.
- Then guide me through `git add` and `git commit` myself with a message of the
  form `docs: <short summary>`.

CHANGE REQUEST
============================================================
Title: Integrate engineering skills into the project workflow

1. CONSTRAINTS.md. Use constraint-driven-development to interview me and
   create `CONSTRAINTS.md`. It must include at least: full pytest suite passes;
   no skipped or deleted tests; `tests/test_architecture.py` is never modified
   to pass; the Anthropic API is always mocked in tests; TypeScript strict mode
   with no `@ts-ignore` once the frontend exists. Propose default thresholds
   for anything else and let me decide. Do not copy rules that already live in
   `CLAUDE.md`; link to them.
2. CLAUDE.md. Add a short "Skill usage" section mapping the session workflow
   to skills: session start (context-engineering), implementing
   (incremental-implementation + test-driven-development), library or SDK code
   (source-driven-development), stage 3 and 4 logic or any contract change
   (doubt-driven-development), errors (debugging-and-error-recovery). Keep the
   "Skill precedence" section unchanged.
3. docs/SPECS.md. Check the non-functional requirements for the items below.
   Add only what is missing, and write each as a testable requirement:
   upload size cap from `MAX_UPLOAD_MB` and file type validation; rate
   limiting on every endpoint that calls the Anthropic API; LLM output treated
   as untrusted and validated before use; secrets only from environment
   variables; CORS only from `ALLOWED_ORIGINS`.
4. PROJECT_PLAN.md. Add a "Definition of Done for every sub-phase" section
   referencing `.claude/references/definition-of-done.md` adapted to this
   project (tests written and passing, constraints respected, Current Status
   updated, commit message proposed). Confirm the skill-wave items added in the
   setup session sit at the right phases, and add, in the phase where Wave 2 is
   installed, one item to create `docs/adr/` with ADRs for: one repo with five
   independent packages; pandas computes and AI only interprets; model choice
   per task (reasoning model vs bulk model, never the largest model at runtime).
5. Out of scope: no changes to contracts, stage logic, phases order, or the
   "what to cut first" list.
============================================================
