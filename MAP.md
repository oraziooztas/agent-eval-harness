# MAP — agent-eval-harness

**Stato**: v0.2.0 (17/07/2026) — 61 test, coverage 95%, 4 fixture validate, sandbox di rete al grading, costo-per-task-risolto, matrice cross-solver.

```
agent-eval-harness/
├── README.md                  perché esiste, anatomia fixture, uso, sandbox, costi, limiti
├── MAP.md                     questo file
├── DEVLOG.md                  log cronologico
├── docs/
│   └── adr-001-aeh-e-afb.md   decisione: rapporto tra aeh (runner) e AFB (bench pubblico)
├── pyproject.toml             PEP 621, runtime stdlib-only, dev: pytest/pytest-cov/ruff
├── .github/workflows/ci.yml   ruff + pytest (gate 80%) + aeh validate fixtures/fx-*
├── src/aeh/
│   ├── fixture.py             modello fixture + validazione layout/naming + hash SHA-256
│   ├── runner.py              workspace agente, solver subprocess (+sandbox opt-in), usage
│   ├── grader.py              grading dir pulita (tamper-proof), rete NEGATA di default
│   ├── sandbox.py             backend net-sandbox: seatbelt (macOS) / unshare-net (Linux)
│   ├── report.py              results.json + run_card.md (verdetto, sandbox, usage)
│   ├── matrix.py              aggregazione N run → matrice per-solver con €/task-risolto
│   └── cli.py                 aeh validate | run (--label/--price-*/--sandbox-solver) | report | matrix
├── fixtures/
│   ├── fx-001-csv-dedup/      bug: last-wins + case-sensitive
│   ├── fx-002-slugify/        bug: solo caso banale
│   ├── fx-003-retry-backoff/  bug: niente cap né validazione (overflow, ValueError)
│   └── fx-004-markdown-toc/   bug: fence ignorate, slug sporchi, duplicati, #senza-spazio
├── tests/                     separation, tamper, contratto, sandbox reale, usage, matrix, CLI
└── runs/                      output dei run (gitignored)
```

**Invarianti**: (1) hidden mai nel workspace agente; (2) grading su copie intatte, solo gli entry file dell'agente attraversano il confine; (3) SHA-256 del set nascosto in ogni result; (4) il grading esegue codice dell'agente → rete negata quando un backend esiste, e lo stato reale è registrato in `results.json`.

**Prossimi passi naturali**: adapter/import batch delle fixture AFB (vedi ADR-001), solver preset per claude/codex CLI, run parallele.
