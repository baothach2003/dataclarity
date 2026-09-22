# ADR-0001: One repo, five independent stage packages, communicating only through contract files

## Status
Accepted

## Date
2026-09-18 (Phase 0A; formalized in this ADR 2026-09-22)

## Context
DataClarity's pipeline has five distinct stages - Collect, Analyze, Diagnose,
Predict, Report - each answering a different question about the uploaded
data. They need to run independently (`python -m stages.<name> --run
<run_id>`, `CLAUDE.md` section 4), be testable in isolation, and stay
replaceable without one stage's internals leaking into another's.

Two ways to get that separation were on the table at Phase 0A:

1. **Five separate repositories**, one per stage, each with its own
   dependencies and its own release.
2. **One repository, five packages**, with the boundary enforced by tooling
   instead of physical repo walls.

The project is a solo effort on a fixed timeline (also a portfolio piece for
a 190 visa application, `PROJECT_PLAN.md` section 1), so the cost of any
extra process falls entirely on one person, immediately - there is no team to
amortize it across.

## Decision
Use **one repository** with five stage packages (`stages/ingest`,
`stages/analyze`, `stages/diagnose`, `stages/predict`, `stages/report`) that
may import only the standard library, third-party packages, and `contracts/`
(`CLAUDE.md` section 3.1). A stage **never imports another stage**. Data
crosses the boundary exclusively through JSON contract files written to
`runs/<run_id>/` (`docs/CONTRACTS.md` section 1: `profile.json` ->
`schema_inference.json` -> ... -> `report.json`), validated on both ends by
the Pydantic models in `contracts/` - the one package every stage may share.

The boundary is not just a convention: `tests/test_architecture.py` parses
every file under `stages/`, `contracts/`, `shared/` and `backend/app` with
`ast` and fails the build on a cross-stage import, or on a stage importing a
web/ORM framework (`fastapi`, `starlette`, `sqlalchemy`, `alembic`). A
deliberately planted cross-stage import is expected to fail this test - that
expectation is itself asserted, so the guard cannot silently stop guarding
anything. `CONSTRAINTS.md` F3 pins the rule permanently: the file may be
*extended* to cover a new boundary, never relaxed to make a build pass.

## Alternatives Considered

### Five separate repositories
- **Pros:** Physical separation is the strongest possible guarantee - a
  cross-stage import is not just rejected, it is a compile-time impossibility
  since the code is not even checked out. Each stage could, in principle,
  version and release independently from day one.
- **Cons:** Five repos means five CI setups, five dependency-update chores,
  and cross-repo coordination for every change that touches a contract shape
  (which, early on, is most changes). For a single developer building five
  stages that all still depend on the same not-yet-stable contract schemas,
  that overhead lands immediately and repeatedly, while the benefit -
  independent versioning - has no consumer yet: nothing outside this project
  depends on any one stage today.
- **Rejected:** at the version-sync cost of 5 repos today, for a benefit
  (independent release) the project cannot use yet. Recorded at Phase 0A
  (`PROJECT_PLAN.md` section 12 Notes, the 0A session block): "ONE repo with
  five independent stage packages and contract files between them, instead of
  five separate repos... Splitting into separate repos later stays possible
  precisely because of that boundary."

## Consequences

**Benefits**
- One `pip install`, one CI run, one place to look for the whole pipeline.
- Each stage is still independently runnable and testable (`python -m
  stages.<name> --run <run_id>`), because the contract-file boundary is real,
  not just a suggestion - `tests/test_architecture.py` makes it a build
  failure to violate, not a code-review nit.
- The option to split into five repos later is preserved rather than
  foreclosed: because no stage imports another today, extracting one into its
  own repo tomorrow is a copy, not a untangling.

**Trade-offs accepted**
- The boundary is enforced by a test, not by the filesystem or a package
  manager - it can only fail a build after the fact (CI or a local run), not
  prevent the import from being typed in the first place. This is accepted
  because the alternative (five repos) fails the same "prevent it before
  typing it" bar for cross-repo *contract* mistakes anyway (a stage can still
  send an evolved contract shape another stage doesn't expect), while costing
  far more for everything else.
- A change to a contract's shape (`contracts/`) can still ripple through
  every stage that reads or writes it, since they all live in one repo and
  see the change at once. This is treated as a feature during active
  development (nothing to keep in sync across repo boundaries while contracts
  are still evolving), not a cost to design around yet.
- If the project ever does need independent per-stage releases (e.g. stage 3
  reused in another product), migrating out is deferred work, not free -
  `tests/test_architecture.py` proves the code *can* separate, it does not
  perform the separation.
