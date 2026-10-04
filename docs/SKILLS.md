# Engineering Skills Used in DataClarity

This project uses a curated subset of Addy Osmani's
[agent-skills](https://github.com/addyosmani/agent-skills) (MIT License) to make
Claude Code follow senior engineering workflows. Skills were selected against
this project's actual stack and rules, not installed wholesale.

## 1. Precedence

`CLAUDE.md` always wins over any skill. Two known conflicts are resolved in its
"Skill precedence" section, which the skills setup session adds:

- `incremental-implementation` and `git-workflow-and-versioning` tell the agent to
  commit after each slice. In this repo **the agent never commits or pushes**;
  it proposes a message and Thach types the git commands.
- Multi-task autonomous runs conflict with **one sub-phase per session**
  (`PROJECT_PLAN.md` sections 5 and 6). The agent never starts the next task
  without Thach's approval.

## 2. Where things live

| Path | Content |
|---|---|
| `.claude/skills/<name>/` | Installed skills (copied, not symlinked, for Windows) |
| `.claude/references/` | Shared checklists the skills link to via `../../references/` |
| `.claude/agents/` | Reviewer personas (Claude Code subagents) |
| `.claude/THIRD_PARTY_LICENSES/agent-skills-LICENSE` | MIT license of the source repo |
| `skills-lock.json` | Pinned source and hash of every installed skill |

Why `.claude/references/`: the per-skill `npx` install copies only
`skills/<name>/`, not the repo-level `references/` folder. Skills point to
`../../references/<file>.md`, which from `.claude/skills/<name>/` resolves to
`.claude/references/`. Copying the checklists there makes every link work.

## 3. Installation waves

Skills are installed when the project reaches the phase that needs them, so the
agent is not distracted by skills it cannot use yet.

### Wave 1: backend stages (install at setup)

| Skill | Used in DataClarity for |
|---|---|
| incremental-implementation | Thin verified slices inside one sub-phase |
| test-driven-development | "Every new function gets a test in the same session"; mocks only at the Anthropic API boundary |
| constraint-driven-development | Writes `CONSTRAINTS.md` and flags any skipped, deleted or weakened test, especially `tests/test_architecture.py` |
| context-engineering | Keeping `CLAUDE.md` and the Current Status section effective across fresh sessions |
| source-driven-development | Checking official docs for fast-moving APIs: Pydantic v2, SQLAlchemy 2, Alembic, FastAPI, Anthropic SDK, statsmodels |
| api-and-interface-design | FastAPI endpoints and the Pydantic contracts between stages |
| security-and-hardening | CSV upload (size, type, parsing), LLM output as untrusted input, secrets, CORS, rate limiting on AI endpoints |
| doubt-driven-development | Adversarial review of stage 3 root-cause logic, stage 4 forecasts and `expected_impact` arithmetic, and contract changes. Spawns a fresh-context reviewer, so use it only where correctness matters |
| debugging-and-error-recovery | Root-cause debugging instead of guessing |
| git-workflow-and-versioning | Atomic commits and clean history (messages proposed, never executed) |

References: `definition-of-done.md`, `testing-patterns.md`,
`security-checklist.md`, `orchestration-patterns.md`.

### Wave 2: after the first stage package is complete

| Skill / persona | Used for |
|---|---|
| code-review-and-quality | Five-axis review before code lands on main |
| code-simplification | Keeping code simple enough to defend in an interview |
| documentation-and-adrs | `docs/adr/` records for key decisions; professional README |
| ci-cd-and-automation | GitHub Actions running pytest and the architecture test on every push |
| agent: test-engineer | Finding untested messy-CSV cases (encodings, date formats, duplicates) |
| agent: code-reviewer | Staff-level review pass |

References: `performance-checklist.md`.

### Wave 3: first frontend phase (Phase 6; the 0D skeleton does not count)

| Skill | Used for |
|---|---|
| frontend-ui-engineering | Stage 1 review-and-approve UI, accessible charts and forms |
| browser-testing-with-devtools | Reading real console errors and network calls between React and FastAPI. **Requires the chrome-devtools MCP server** |

References: `accessibility-checklist.md`.

**Installed 2026-10-04** (approved by Thach on the fourteenth report): both
skills via `npx skills add addyosmani/agent-skills -a claude-code --copy -y
-s frontend-ui-engineering -s browser-testing-with-devtools` (source and hash
in `skills-lock.json`; the files were read before installing and are
identical to the source at commit 1401c8b), `accessibility-checklist.md`
copied into `.claude/references/`. The chrome-devtools MCP server is in the
project's `.mcp.json`: the official package `chrome-devtools-mcp` **1.10.1**
(github.com/ChromeDevTools/chrome-devtools-mcp, Apache-2.0, published by
Google's npm account), pinned rather than `@latest`, with `--isolated` (a
temporary Chrome profile wiped on close - never the daily profile) and the
`cmd /c` wrapper Windows needs for `npx`. Claude Code asks to approve a new
project MCP server and loads it at the next session start. Under the memory
rules the automated browser is a heavy process: never with a measurement,
the test suite or a mutation run.

### Wave 4: deployment phase

| Skill / persona | Used for |
|---|---|
| shipping-and-launch | Pre-launch checklist and rollback plan for Render and Vercel |
| agent: security-auditor | Full security pass before the public demo goes live |

## 4. Deliberately not installed

| Skill | Reason |
|---|---|
| spec-driven-development | Built for projects with no spec yet; `docs/SPECS.md` and `docs/CONTRACTS.md` already exist and must stay the single source of truth |
| planning-and-task-breakdown | `PROJECT_PLAN.md` already defines phases and sub-phases |
| interview-me, idea-refine | Requirements and concept are settled |
| using-agent-skills | Router for the full bundle; not needed for a curated set |
| performance-optimization | 50 MB pandas ceiling; revisit only if a measured problem appears |
| observability-and-instrumentation | Aimed at production systems with real users; basic logging suffices |
| deprecation-and-migration | No legacy system; Alembic migrations on a demo DB need no zero-downtime process |
| web-quality-skills (all 6) | SEO and Core Web Vitals do not matter for an upload app; accessibility and best-practices overlap with installed skills |
| agent: web-performance-auditor | Same as performance-optimization |

## 5. Maintenance

Install a wave (example, run from repo root):

```
npx skills add addyosmani/agent-skills -a claude-code --copy -y -s code-review-and-quality -s code-simplification
```

Then copy any listed reference files from a temporary clone into
`.claude/references/`, and persona files into `.claude/agents/`.

- List installed: `npx skills list`
- Update: `npx skills update -p` (review the diff before committing)
- Remove: `npx skills remove <name>`
- Restore on a new machine: `npx skills experimental_install` (reads `skills-lock.json`)

Skills run with full agent permissions. Read a skill's `SKILL.md` before
installing or updating it.
