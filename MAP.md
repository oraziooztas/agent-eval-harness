# MAP — agent-eval-harness

**Stato**: v0.3.0 (01/08/2026) — 77 test, coverage 95%, ponte AFB attivo (ADR-001 accettato): 4 fixture pubbliche + 3 importate da AFB (gitignored, materiale privato), sandbox di rete al grading, costo-per-task-risolto, matrice cross-solver. Pubblico su `github.com/oraziooztas/agent-eval-harness`.

```
agent-eval-harness/
├── README.md                  perché esiste, anatomia fixture, uso, sandbox, costi, limiti
├── MAP.md                     questo file
├── DEVLOG.md                  log cronologico
├── docs/
│   ├── adr-001-aeh-e-afb.md   ACCETTATO 19/07: aeh runner, AFB bench, ponte a senso unico
│   └── METRICS.md             come si leggono i numeri: solve rate = segnale, public = regression guard, hidden gap solo contro il floor
├── pyproject.toml             PEP 621, runtime stdlib-only, dev: pytest/pytest-cov/ruff
├── .github/workflows/ci.yml   ruff + pytest (gate 80%) + aeh validate fixtures/fx-*
├── src/aeh/
│   ├── fixture.py             modello fixture + validazione layout/naming + hash SHA-256
│   ├── runner.py              workspace agente, solver subprocess (+sandbox opt-in), usage
│   ├── grader.py              grading dir pulita (tamper-proof), rete NEGATA di default
│   ├── sandbox.py             backend net-sandbox: seatbelt (macOS) / unshare-net (Linux)
│   ├── importer.py            ponte ADR-001: task eseguibili AFB → fixture aeh (holdout, stub, provenance)
│   ├── report.py              results.json + run_card.md (verdetto, sandbox, usage)
│   ├── matrix.py              aggregazione N run → matrice per-solver con €/task-risolto + floor/ceiling derivati dai run builtin
│   └── cli.py                 aeh validate | run (--label/--price-*/--sandbox-solver) | report | matrix | import-afb
├── fixtures/
│   ├── fx-001-csv-dedup/      bug: last-wins + case-sensitive
│   ├── fx-002-slugify/        bug: solo caso banale
│   ├── fx-003-retry-backoff/  bug: niente cap né validazione (overflow, ValueError)
│   ├── fx-004-markdown-toc/   bug: fence ignorate, slug sporchi, duplicati, #senza-spazio
│   └── afb-v0-{002,006,009}/  importate da AFB (gitignored: contengono holdout privato del bench)
├── tests/                     separation, tamper, contratto, sandbox reale, usage, matrix, CLI
└── runs/                      output dei run (gitignored)
```

**Invarianti**: (1) hidden mai nel workspace agente; (2) grading su copie intatte, solo gli entry file dell'agente attraversano il confine; (3) SHA-256 del set nascosto in ogni result; (4) il grading esegue codice dell'agente → rete negata quando un backend esiste, e lo stato reale è registrato in `results.json`; (5) **il public pass rate non guida mai un summary, una run card o una riga di matrice** — è verde sul seed intatto per costruzione (lo impone `aeh validate`), quindi in testa sarebbe un segnale falso; e un hidden gap senza floor non viene stampato come se avesse una scala. Le (5) sono asserite dai test, non affidate alla disciplina di chi scrive.

**Prossimi passi naturali**: prima matrice cross-model AFB eseguita con `aeh run --label` + `aeh matrix` (output → `evidence/` di AFB citando la versione aeh, come da ADR-001), solver preset per claude/codex CLI, run parallele.
