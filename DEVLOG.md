# DEVLOG — agent-eval-harness

## 2026-07-10 — v0.1.0: harness con hidden-check separation vera
- Nato dal backlog "Fable 5 intensivo" (task #3 della sessione Saraev-videos): eval pipeline = milestone tecnico primario CAREER + next action AFB ("hidden-check separation vera") in forma standalone riusabile.
- Core: `fixture.py` (layout + naming enforcement + SHA-256 del set nascosto), `runner.py` (workspace = seed + public + PROMPT.md, invariante no-hidden verificata), `grader.py` (grading dir fresca: seed intatto + soli entry file dell'agente + test intatti; runner unittest→JSON embedded, zero deps), `report.py`, `cli.py` (validate/run/report, exit 0/1/2).
- 2 fixture esempio (csv-dedup, slugify) col contratto "seed passa public, fallisce hidden; reference passa tutto" — stesso pattern di validazione usato in AFB.
- Verifica: 29 pytest PASS, coverage 96% (gate 80), ruff clean, `aeh validate` VALID su entrambe le fixture. CI workflow pronto per il primo push.
- Decisioni: fixture tests in unittest (grading a zero dipendenze), tamper-proof by construction (i test dell'agente non attraversano mai il confine di grading), niente sandbox rete in v0 (documentato).
