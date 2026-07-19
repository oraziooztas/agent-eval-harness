# DEVLOG — agent-eval-harness

## 2026-07-20 — v0.3.0: ponte AFB attivo (ADR-001 ratificato 19/07) + primo push pubblico
- Backlog AFK-queue "ratifica ADR-001": Orazio ha ratificato (19/07, sessione Fable 5 max effort) e il ponte è stato implementato subito. `importer.py` + `aeh import-afb`: task eseguibili AFB → fixture aeh. agent_visible→seed (TASK.md→prompt), test pubblici rinominati `test_public_*` (asset non-.py preservati nel workspace, ignorati al grading), holdout risolto in-repo o via `--holdout-dir`; senza holdout import PARTIAL (exit 2) con MISSING.md costruito dagli hidden_checks pubblicati.
- entry_files rilevati per diff reference↔visibile: 002 `src/metrics.py`, 009 `src/logging_utils.py`, 006 `src/path_utils.py` + `attempt_log.json` (artefatto solo-in-reference → stub JSON nel seed con le stesse chiavi vuote, tracciato in `provenance.seed_stubs`).
- Import reale delle 3 disclosed dal repo di lavoro (`~/Vault/Progetti/Agent-Failure-Eval-Bench`): 3/3 complete, `aeh validate` **7/7 VALID**, smoke afb-v0-002 `--noop` PARTIAL 4/4+3/4 exit 2 (fallisce esattamente il check off-by-one) e `--ref` SOLVED exit 0.
- **Finding reale al primo validate**: drift in afb-v0-006 — l'hidden test aspettava `…notes.\n\n`, la nota pubblicata finisce con `\n`; confermato indipendentemente da `scripts/validate_fixtures.py` di AFB (stessa assertion). Fix 1-riga lato holdout privato (il file pubblico è frozen dal MANIFEST.sha256; il manifest non copre gli hidden → nessun impatto sul bundle), backup pre-fix in scratchpad. Ora il validator AFB torna OK 3/3.
- Policy pubblicazione: le fixture importate contengono materiale privato del bench → `.gitignore fixtures/afb-*` e `.pipeline/`; pubblici importer, test hermetici (fake-AFB in tmp_path), docs. 70 pytest (9 nuovi), coverage 94%, ruff clean.
- Primo remote: `gh repo create oraziooztas/agent-eval-harness --public` + push (gh auth verificato live: la nota 17/07 "token da riattivare" era stale — 4° flip-flop del pattern, verify-first ha pagato).

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
