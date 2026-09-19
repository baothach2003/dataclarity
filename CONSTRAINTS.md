# Constraints

Last reviewed: 2026-09-19 (drafted by Claude Code, decisions approved by Thach)

The measurable quality bar for DataClarity. Rules about how the agent works live
in `CLAUDE.md`; product behaviour, including runtime numbers such as performance
limits, lives in `docs/SPECS.md`. This file holds only the gates on code and
process: what is checked, by which command, from when, and whether a failure
blocks. Where a rule already exists elsewhere, the row links to it instead of
restating it. On a conflict with another source-of-truth file, stop and reconcile
with Thach (`CLAUDE.md` section 1).

Enforcement level: written only. The agent runs the checks at task end, and Thach
runs them again before committing. No CI exists yet. The time budget for all
task-end checks together is 90 seconds. Checks that need the network run only
before commit (marked "before commit" below).

"The diff" in every check below means `git diff HEAD` plus every untracked file
listed by `git ls-files --others --exclude-standard`. Plain `git diff` misses new
files, and most sub-phases create them.

## Floor (blocks: the task is not done while any of these fails)

| # | Rule | Source of the rule | Checked by | Active from |
|---|---|---|---|---|
| F1 | Every test suite passes with no failed, error, skipped, xfailed or xpassed result. Warnings are reported, not blocking | `CLAUDE.md` section 7 item 2; "Skill precedence" (never skip, delete or weaken a test) | `backend/venv/Scripts/python -m pytest -rsxX` from the repo root; from 0D also `npx vitest run` in `frontend/` (never watch mode) | now (Vitest from 0D) |
| F2 | No test weakened or switched off: no deleted or renamed-away test file, no removed assertion in a test that stays, no new `skip`, `skipif`, `xfail`, `importorskip`, `pytest.skip()`, Vitest `.skip` / `.only` / `.todo`, and no new `-k`, `--deselect`, `--ignore` or `collect_ignore` | "Skill precedence" | review of the diff over `tests/`, `conftest.py` files, `pytest.ini`, and test files under `frontend/` | now |
| F3 | `tests/test_architecture.py` is never relaxed or deleted. Extending it to cover a new boundary is allowed | `CLAUDE.md` section 3.1; "Skill precedence" | the test passes; every diff to the file is reviewed and adds no allow-list entry, skip or early return; a deliberately planted cross-stage import still makes it fail | 0C (the file is created there) |
| F4 | No test reaches the real Anthropic API | `CLAUDE.md` sections 2 and 6 | the guard fixture in `docs/AI_PIPELINE.md` section 10 fails the suite on any real HTTP call to the API | 1C (the first sub-phase that calls the AI client) |
| F5 | TypeScript compiles in strict mode with zero errors | `CLAUDE.md` section 5 | `npx tsc -b` in `frontend/` (checks every referenced project), with `"strict": true` in each tsconfig that includes `src/` | 0D |
| F6 | No `@ts-ignore` and no `@ts-nocheck`. `@ts-expect-error` only with a reason on the same line | this file | search the diff for `@ts-ignore`, `@ts-nocheck`, and for `@ts-expect-error` without a trailing reason | 0D |
| F7 | Python suppressions only in scoped form with a reason: `# type: ignore[<code>]  # <reason>` and `# noqa: <CODE>  # <reason>`. Not allowed: a bare `# type: ignore` or `# noqa`, `# pragma: no cover`, file-level `# ruff: noqa`, `# mypy: ignore-errors`, or `# pyright: ignore` without a rule name | this file | search the diff for `type: ignore` without `[code]`, `noqa` without `: CODE`, and the other forms listed | now |
| F8 | No unfinished work: no `raise NotImplementedError` outside abstract or Protocol methods, no `TODO` standing in for an implementation, no `except` block that only passes | this file | review of the diff | now |
| F9 | No secrets in source or fixtures (log leakage is tested by SEC-4) | `CLAUDE.md` section 5; `docs/SPECS.md` section 11 SEC-4 | review of the diff; tests use the fake values in `tests/conftest.py` | now |
| F10 | No new lint warnings | `CLAUDE.md` section 7 item 4 | `ruff check .` with the project config; `npm run lint` in `frontend/` (ESLint, `--max-warnings=0`) | `npm run lint`: now (added 2026-09-19, approved by Thach); `ruff`: when a project ruff config exists (not yet approved) |
| F11 | This file is never loosened to make a change pass. Tightening is fine. Loosening (a lower number, a row removed, a block turned into a warning, a new exception) needs Thach's explicit approval in a docs session and an entry in the `docs/SPECS.md` change log | this file | `git diff HEAD -- CONSTRAINTS.md` (or the whole file while it is untracked) reviewed on every commit that touches it | now |

## Warn (reported at task end; does not block)

| # | Dimension | Rule | Checked by | Active from |
|---|---|---|---|---|
| W1 | Coverage of changed lines | at least 80% of changed lines in `stages/` and `backend/app/services/` are covered | the F1 run with `--cov=stages --cov=backend/app/services --cov-report=xml` added (one run, not two), then `diff-cover coverage.xml --fail-under=80` | when `pytest-cov` and `diff-cover` are installed (needs Thach's approval) |
| W2 | Project coverage | does not fall below the recorded value (tolerance 0.5 percentage points) | same run as W1 | same as W1 |
| W3 | Python dependency vulnerabilities | no known vulnerability. `pip-audit` reports no severity, so every finding is reported to Thach; one without a fixed version is noted in `PROJECT_PLAN.md` section 12 | `pip-audit -r backend/requirements.txt`, before commit (needs the network) | when `pip-audit` is installed (needs Thach's approval) |
| W4 | npm dependency vulnerabilities | nothing at high severity or above | `npm audit --audit-level=high` in `frontend/`, before commit (needs the network) | 0D |

W3 and W4 are the external constraints: their verdicts come from public
vulnerability databases, not from tests this project wrote.

Why these numbers: 80% of changed lines is high enough to force a test for every
new function and still leaves room for a config line. Project coverage uses
measure-and-hold because no baseline exists yet, and an invented target gets
ignored. The 0.5-point tolerance absorbs drift when an unrelated file moves the
total. "High and above" for npm because lower severities are mostly noise for a
demo app; for Python every finding counts because the tool gives no severity to
filter on.

## Measured, not yet enforced

| Metric | Today | Direction |
|---|---|---|
| Project coverage (`stages/`, `backend/app/services/`) | not measured: `pytest-cov` not installed | must not fall once recorded |
| Python dependency vulnerabilities | not measured: `pip-audit` not installed | count must not grow once recorded |

## Owned elsewhere (not restated here)

- Performance limits and accessibility: `docs/SPECS.md` section 11
- Security behaviour (SEC-1 to SEC-5): `docs/SPECS.md` section 11
- Test content rules (hand-checked expectations, edge cases): `CLAUDE.md` section 5
  and `docs/AI_PIPELINE.md` section 10

## Exceptions

A new exception needs an owner and an expiry at most 90 days out, and is added
under the F11 process.

| ID | Rule | Path | Reason | Owner | Expires |
|---|---|---|---|---|---|
| - | - | - | none yet | - | - |
