# SKILLS SETUP PROMPT

Before starting: copy `docs/SKILLS.md` into the repo's `docs/` folder, make sure
the working tree is clean (`git status`), then open a new Claude Code session in
the repo root and paste everything below the line.

---

This session installs engineering skills into DataClarity. It is a tooling
session, not a feature sub-phase: write no application code.

Before doing anything, read in this order:
1. `CLAUDE.md`
2. `PROJECT_PLAN.md`, especially the phases section and the Current Status section
3. `docs/SKILLS.md` (the plan for this session; follow it exactly)

SCOPE OF THIS SESSION

1. Pre-checks. Run `git status` and stop if the tree is not clean. Run
   `node --version`; if Node is missing, stop and tell me to install Node.js LTS.
2. Decide which waves are due. Wave 1 is always due. From the Current Status
   section, determine whether Waves 2, 3 or 4 are also due by now (see the
   trigger of each wave in `docs/SKILLS.md` section 3). Tell me your conclusion
   and wait for my confirmation before installing.
3. Install the skills of every due wave with one command per wave, from the
   repo root, for example Wave 1:
   ```
   npx skills add addyosmani/agent-skills -a claude-code --copy -y -s incremental-implementation -s test-driven-development -s constraint-driven-development -s context-engineering -s source-driven-development -s api-and-interface-design -s security-and-hardening -s doubt-driven-development -s debugging-and-error-recovery -s git-workflow-and-versioning
   ```
   Do not install any skill that is not listed in `docs/SKILLS.md`.
4. Shared files. Clone the source repo into a temporary folder OUTSIDE this repo:
   `git clone --depth 1 https://github.com/addyosmani/agent-skills.git <temp>`.
   From it, copy into this repo:
   - the reference files listed for each due wave into `.claude/references/`
   - the persona files for each due wave from `agents/` into `.claude/agents/`
   - `LICENSE` to `.claude/THIRD_PARTY_LICENSES/agent-skills-LICENSE`
   Then delete the temporary clone.
5. Verify, and show me the evidence:
   - `npx skills list` shows exactly the expected skills
   - every `../../references/<file>.md` link inside the installed `SKILL.md`
     files points to a file that exists in `.claude/references/`
     (grep the links and check each one)
   - `skills-lock.json` exists at the repo root
   - the full test suite still passes (`pytest`)
6. Add this section to `CLAUDE.md` if it is not already there, without changing
   any other rule:
   ```
   ## Skill precedence
   - Rules in this file override any installed skill (see docs/SKILLS.md).
   - Never run git commit or git push. Propose the message; Thach types the commands.
   - One sub-phase per session. Never start the next task without Thach's approval.
   - Never skip, delete or weaken a test to make it pass. tests/test_architecture.py may be created (Phase 0C) or extended to cover new boundaries, but never relaxed to make a build pass.
   ```
7. In `PROJECT_PLAN.md`, add one unticked item "Install skills Wave N (see
   docs/SKILLS.md)" at the start of the phase where each not-yet-due wave
   becomes due. Do not change anything else in the plan.

WORKING STYLE (mandatory)

- Before each step, state briefly what you will do and why.
- Explain what each installed skill will change in how you work on this
  project, in Vietnamese in chat. Files and commit messages stay in English.
- Do not declare success before I confirm `pytest` passes on my machine
  (Windows, VS Code).
- Ask me 2 short comprehension-check questions (for example: which file wins
  when a skill and CLAUDE.md disagree, and why the references folder was
  needed) and wait for my answers.
- Before ending: update the Current Status section of `PROJECT_PLAN.md` with
  what was installed and the next step, which is the SPECS UPDATE session.
- Then guide me through `git add` and `git commit` myself with the message:
  `chore: install engineering agent skills (wave 1)` (list extra waves if any).
