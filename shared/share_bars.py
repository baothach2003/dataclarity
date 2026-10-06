"""The share bars a hypothesis's verdict is decided by (docs/AI_PIPELINE.md
7.8) - one copy for every stage that reads them: stage 3 decides the
verdicts with them; stage 5 groups its checklist and stage 4 selects its
claims by the same bars (the report redesign, steps 3 and 4: CLAUDE.md 3.1,
a definition two stages use lives here). Moved unchanged from
stages/diagnose/thresholds.py, which re-exports them.

A cause must explain a fifth of its lens's movement to be called supported,
and a twentieth to be worth mentioning at all. Below that it is noise.
"""

SUPPORTED_MIN_SHARE = 0.20
PARTIAL_MIN_SHARE = 0.05
