# KICKOFF PROMPT

Copy everything below the line into Claude Code for session 1.
For later sessions, reuse the same structure and change only the SCOPE block to
the next sub-phase from PROJECT_PLAN.md section 5.

---

This is the first working session of the DataClarity project.

Before doing anything, read in this order and follow them strictly:
1. `CLAUDE.md` - the rules of this repo
2. `PROJECT_PLAN.md`, especially section 5 (phases) and section 12 (current status)
3. `docs/SPECS.md` sections 1 to 4
4. `docs/CONTRACTS.md` section 1

Key rules you must respect: one sub-phase per session and nothing more; stage
packages never import each other; pandas computes and AI only interprets; every
new function gets a test in the same session; AI is always mocked in tests.

SCOPE OF THIS SESSION - Phase 0A only, do not exceed it

1. Initialize the git repo and create the folder skeleton from CLAUDE.md
   section 4. Create empty package directories with `__init__.py` for
   `contracts/`, `stages/ingest`, `stages/analyze`, `stages/diagnose`,
   `stages/predict`, `stages/report`, and `shared/`. Do not write any stage
   logic yet - those belong to later phases.
2. Backend skeleton:
   - `backend/app/main.py` with a FastAPI app factory and a `GET /health`
     endpoint returning `{"status": "ok"}`
   - `backend/app/config.py` using pydantic-settings, reading from `.env`
   - `.env.example` documenting: ANTHROPIC_API_KEY, DATABASE_URL,
     ALLOWED_ORIGINS, MODEL_REASONING, MODEL_BULK, MAX_UPLOAD_MB,
     RUNS_DIR, RETENTION_HOURS
   - CORS configured from ALLOWED_ORIGINS, never hardcoded
   - `backend/requirements.txt`: fastapi, uvicorn, pandas, sqlalchemy, alembic,
     psycopg2-binary, pydantic-settings, anthropic, python-multipart,
     statsmodels, plotly, pytest, httpx
3. Wire pytest with one passing test: `GET /health` returns 200 and the expected
   body, using FastAPI TestClient.
4. Root `.gitignore` covering: `.env`, `venv/`, `__pycache__/`, `.pytest_cache/`,
   `node_modules/`, `dist/`, `runs/`, `design/mockups/*.png` is NOT ignored
   (mockups are committed on purpose).

WORKING STYLE - mandatory

- Before writing code, state briefly what you will do and why.
- After writing, explain the key decisions to me in Vietnamese in chat. All
  files, code, comments and commit messages stay in English.
- Guide me to run the server and the test myself. Do not declare success before
  I confirm both work on my machine (Windows, VS Code).
- Ask me 2 short comprehension-check questions about this session's code and
  wait for my answers.
- Before ending your turn, update `PROJECT_PLAN.md` with the file-editing tool:
  tick the 0A items actually completed and rewrite section 12 (phase in
  progress, next step = Phase 0B, notes for the next session).
- Then guide me through `git add` and `git commit` myself with the message:
  `feat: backend skeleton with health endpoint and config`.
