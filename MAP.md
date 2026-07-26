# MAP — agent-eval-harness

**Stato**: v0.3.0 (20/07/2026) — 70 test, coverage 94%, ponte AFB attivo (ADR-001 accettato): 4 fixture pubbliche + 3 importate da AFB (gitignored, materiale privato), sandbox di rete al grading, costo-per-task-risolto, matrice cross-solver. Pubblico su `github.com/oraziooztas/agent-eval-harness`.

```
agent-eval-harness/
├── README.md                  perché esiste, anatomia fixture, uso, sandbox, costi, limiti
├── MAP.md                     questo file
├── DEVLOG.md                  log cronologico
├── docs/
│   └── adr-001-aeh-e-afb.md   ACCETTATO 19/07: aeh runner, AFB bench, ponte a senso unico
├── pyproject.toml             PEP 621, runtime stdlib-only, dev: pytest/pytest-cov/ruff
├── .github/workflows/ci.yml   ruff + pytest (gate 80%) + aeh validate fixtures/fx-*
├── scripts/
│   └── estimate_cost.py       stima costo a spesa zero: misura il contesto fixture, isola le ipotesi sul loop
├── src/aeh/
│   ├── fixture.py             modello fixture + validazione layout/naming + hash SHA-256
│   ├── runner.py              workspace agente, solver subprocess (+sandbox opt-in), usage, credenziale API
│   ├── grader.py              grading dir pulita (tamper-proof), rete NEGATA di default
│   ├── sandbox.py             backend net-sandbox: seatbelt (macOS) / unshare-net (Linux)
│   ├── importer.py            ponte ADR-001: task eseguibili AFB → fixture aeh (holdout, stub, provenance)
│   ├── report.py              results.json + run_card.md (verdetto, sandbox, usage)
│   ├── matrix.py              aggregazione N run → matrice per-solver con €/task-risolto
│   └── cli.py                 aeh validate | run (--label/--price-*/--sandbox-solver/--require-api-key) | report | matrix | import-afb
├── fixtures/
│   ├── fx-001-csv-dedup/      bug: last-wins + case-sensitive
│   ├── fx-002-slugify/        bug: solo caso banale
│   ├── fx-003-retry-backoff/  bug: niente cap né validazione (overflow, ValueError)
│   ├── fx-004-markdown-toc/   bug: fence ignorate, slug sporchi, duplicati, #senza-spazio
│   └── afb-v0-{002,006,009}/  importate da AFB (gitignored: contengono holdout privato del bench)
├── tests/                     separation, tamper, contratto, sandbox reale, usage, matrix, CLI
└── runs/                      output dei run (gitignored)
```

**Invarianti**: (1) hidden mai nel workspace agente; (2) grading su copie intatte, solo gli entry file dell'agente attraversano il confine; (3) SHA-256 del set nascosto in ogni result; (4) il grading esegue codice dell'agente → rete negata quando un backend esiste, e lo stato reale è registrato in `results.json`; (5) un run a pagamento usa una API key esplicita (`--require-api-key`), mai un fallback silenzioso sull'abbonamento; la chiave non compare in nessun artefatto, solo il suo fingerprint.

**Prossimi passi naturali**: la matrice cross-model AFB con modelli reali (path credenziale cablato e validato a costo zero il 26/07 — manca solo la chiave), output → `evidence/` di AFB citando la versione aeh come da ADR-001, solver preset per claude/codex CLI, run parallele.
