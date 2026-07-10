# MAP — agent-eval-harness

**Stato**: v0.1.0 (10/07/2026) — funzionante, 29 test, coverage 96%, 2 fixture d'esempio validate.

```
agent-eval-harness/
├── README.md                  perché esiste, anatomia fixture, uso, limiti, compat AFB
├── MAP.md                     questo file
├── DEVLOG.md                  log cronologico
├── pyproject.toml             PEP 621, runtime stdlib-only, dev: pytest/pytest-cov/ruff
├── .github/workflows/ci.yml   ruff + pytest (gate 80%) + aeh validate, py 3.11/3.12
├── src/aeh/
│   ├── fixture.py             modello fixture + validazione layout/naming + hash SHA-256
│   ├── runner.py              workspace agente (seed+public+PROMPT.md), solver subprocess, leak check
│   ├── grader.py              grading dir pulita (tamper-proof), test runner unittest→JSON embedded
│   ├── report.py              results.json + run_card.md
│   └── cli.py                 aeh validate | run (--solver/--ref/--noop) | report
├── fixtures/
│   ├── fx-001-csv-dedup/      bug: last-wins + case-sensitive (public passa, hidden no)
│   └── fx-002-slugify/        bug: solo caso banale (accenti/punteggiatura/collasso nei hidden)
├── tests/                     suite: separation, tamper, contratto, timeout, CLI
└── runs/                      output dei run (gitignored)
```

**Invarianti**: (1) hidden mai nel workspace agente; (2) grading su copie intatte, solo gli entry file dell'agente attraversano il confine; (3) SHA-256 del set nascosto in ogni result.

**Prossimi passi naturali**: adapter per le fixture AFB del vault (stessa forma), solver preset per claude/codex CLI, run parallele.
