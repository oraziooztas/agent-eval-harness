# DEVLOG — agent-eval-harness

## 2026-07-17 — v0.2.0: sandbox di rete, €/task-risolto, matrice, 2 fixture reali
- AFK Fable 5 (backlog item 5 + AFK-queue "sandbox"): chiuso il "NON fatto" dichiarato della v0.
- `sandbox.py`: backend seatbelt (macOS) / unshare-net (Linux); semantica verificata dal vivo (connect refused 61 → EPERM 1). Grading ora net-denied DI DEFAULT (il codice dell'agente gira lì), con fallback onesto registrato in results (`grading_sandbox`); solver opt-in `--sandbox-solver` (gli agent CLI hanno bisogno dell'API).
- Usage/costo: il solver riporta token/costo via `$AEH_USAGE_FILE`, `--price-in/--price-out` calcolano gli EUR; provenienza sempre `solver-reported`. `aeh matrix` aggrega N run per `--label`: solve rate, hidden gap pp, latenza mediana, €/task-risolto (mai calcolato su coperture parziali).
- 2 fixture reali: fx-003-retry-backoff (cap+validazione), fx-004-markdown-toc (fence/slug/duplicati); `aeh validate` VALID 4/4 al primo colpo; CI validate → glob `fixtures/fx-*`.
- Verifica: 61 pytest (0 skip su macOS: la probe di negazione gira davvero), coverage 95%, ruff clean, E2E CLI reale (run ref + run con usage → matrice con 4.4 € corretti). Bug trovato nel test, non nella lib: path con spazio non quotato nel comando solver.
- ADR-001 (docs/): rapporto aeh ↔ AFB deciso — dettagli nel file; nessun push (repo senza remote, gh token da riattivare).

## 2026-07-10 — v0.1.0: harness con hidden-check separation vera
- Nato dal backlog "Fable 5 intensivo" (task #3 della sessione Saraev-videos): eval pipeline = milestone tecnico primario CAREER + next action AFB ("hidden-check separation vera") in forma standalone riusabile.
- Core: `fixture.py` (layout + naming enforcement + SHA-256 del set nascosto), `runner.py` (workspace = seed + public + PROMPT.md, invariante no-hidden verificata), `grader.py` (grading dir fresca: seed intatto + soli entry file dell'agente + test intatti; runner unittest→JSON embedded, zero deps), `report.py`, `cli.py` (validate/run/report, exit 0/1/2).
- 2 fixture esempio (csv-dedup, slugify) col contratto "seed passa public, fallisce hidden; reference passa tutto" — stesso pattern di validazione usato in AFB.
- Verifica: 29 pytest PASS, coverage 96% (gate 80), ruff clean, `aeh validate` VALID su entrambe le fixture. CI workflow pronto per il primo push.
- Decisioni: fixture tests in unittest (grading a zero dipendenze), tamper-proof by construction (i test dell'agente non attraversano mai il confine di grading), niente sandbox rete in v0 (documentato).
