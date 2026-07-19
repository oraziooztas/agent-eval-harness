# agent-eval-harness

Harness minimale per valutare coding agent con **hidden-check separation vera**: l'agente lavora su un repo seed con i soli test pubblici; la valutazione avviene in una directory pulita con test pubblici E nascosti intatti, presi dalla fixture. Runtime 100% stdlib.

## Perché esiste

Valutare un agente sui test che l'agente stesso può vedere (o modificare) non misura niente. Questo harness rende la separazione un invariante strutturale, non una convenzione:

1. **Il workspace dell'agente non contiene mai gli hidden test** (verificato a fine preparazione e ri-verificato al grading).
2. **Il grading non si fida del workspace**: directory fresca = seed intatto + SOLO gli entry file dell'agente + test pubblici e nascosti presi dalla fixture. Un agente che riscrive i test cambia il proprio grade di zero.
3. **Ogni run registra lo SHA-256 del set nascosto**: prova crittografica di quali check hanno valutato il run.

## Anatomia di una fixture

```
fx-001-csv-dedup/
├── task.json          id, title, prompt, entry_files, timeout_seconds, taxonomy
├── seed/              il repo buggy/incompleto da cui parte l'agente
├── tests_public/      test_public*.py — visibili all'agente (happy path)
├── tests_hidden/      test_hidden*.py — MAI visti dall'agente (edge case)
└── reference/         soluzione corretta degli entry file
```

Contratto di design (verificato da `aeh validate`): il seed **passa i public** ma **fallisce ≥1 hidden** (il bug vive negli edge case); la reference passa tutto. Così "passa i test pubblici" e "ha risolto il task" restano misure distinte.

## Uso

```bash
# installazione (dev)
uv venv .venv && uv pip install -e ".[dev]" --python .venv/bin/python

# 1. verifica il contratto delle fixture
aeh validate fixtures/fx-001-csv-dedup fixtures/fx-002-slugify

# 2. baseline: cosa succede senza agente (seed as-is)
aeh run fixtures/fx-001-csv-dedup --noop      # exit 2, PARTIAL

# 3. sanity: la reference risolve
aeh run fixtures/fx-001-csv-dedup --ref       # exit 0, SOLVED

# 4. un agente vero: qualsiasi comando shell, cwd = workspace
aeh run fixtures/fx-001-csv-dedup \
  --solver 'claude -p "$(cat PROMPT.md)" --permission-mode acceptEdits' \
  --label claude-sonnet --price-in 2.5 --price-out 12.0

# 5. matrice cross-solver da N run (solve rate, hidden gap, €/task risolto)
aeh matrix runs/* --out runs/matrix
```

Ogni run produce `runs/{id}-{ts}/` con `workspace/` (ciò che l'agente ha visto e toccato), `grading/` (la valutazione pulita), `transcript.txt`, `results.json` e `run_card.md` (verdetto, tabella public/hidden, hash del set nascosto, riproduzione).

Exit code: `0` solved · `1` errore harness/contratto · `2` run valido ma non risolto.

## Cosa misura (e cosa no)

- Misura: capacità dell'agente di risolvere il contratto REALE del task, non solo i test che vede. Il gap public-pass vs hidden-pass è il segnale interessante (overfitting ai test visibili).
- `tamper_suspect`: file con nome da hidden test creati dall'agente nel workspace vengono flaggati nel run card (il grading resta comunque valido).
- Non fa (ancora): confinamento filesystem del solver (gira col tuo utente: usa agent CLI di cui ti fidi), multi-linguaggio (i test fixture sono `unittest` Python), parallelismo di run.

## Sandbox di rete

Il codice scritto dall'agente VIENE ESEGUITO al grading (i test importano gli entry
file): per questo il grading gira con la rete negata quando esiste un backend —
`sandbox-exec` su macOS (seatbelt: deprecato negli header ma presente e mantenuto;
una connect rifiutata diventa EPERM), `unshare --net` su Linux. Ogni run registra in
`results.json` cosa è successo davvero (`grading_sandbox`: backend, `unavailable`,
`disabled` o `fallback-off:*` se il backend non partiva). Escape: `--no-grading-sandbox`.
Il solver invece ha la rete per default (gli agent CLI ne hanno bisogno per l'API);
`--sandbox-solver` la nega esplicitamente ai solver locali/offline.

## Costo per task risolto

Il solver può riportare il proprio consumo scrivendo JSON nel file indicato da
`$AEH_USAGE_FILE` (`{"tokens_in": …, "tokens_out": …, "cost_eur": …}`); con
`--price-in/--price-out` (EUR per Mtok) il costo viene calcolato dai token. La
provenienza è sempre marcata `solver-reported`: è un dato del processo sotto
valutazione, non una prova. `aeh matrix` aggrega N run per label (`--label`) e
riporta per ciascun solver solve rate, hidden gap, latenza mediana e
**€/task-risolto** (solo se TUTTI i run del solver hanno un costo: niente medie
inventate su dati parziali).

## Ponte AFB (`aeh import-afb`)

aeh è il runner delle prossime matrici dell'[Agent Failure Eval Bench](https://github.com/oraziooztas/agent-failure-eval-bench): due repo separati con ponte a senso unico (ADR-001 in `docs/`) — AFB resta l'artefatto-bench (spec, taxonomy, policy, evidence), aeh esegue. L'importer converte i task eseguibili di AFB in fixture aeh:

```bash
aeh import-afb path/al/repo/afb --out fixtures             # holdout dentro il repo di lavoro
aeh import-afb path/al/clone/pubblico --holdout-dir DIR    # materiali privati esterni
```

- `agent_visible/` → `seed/` (senza `tests/` e TASK.md, che diventa il prompt); test pubblici rinominati `test_public_*`; gli asset non-.py dei test restano visibili nel workspace ma il grading li ignora.
- `entry_files` rilevati per diff reference↔visibile; gli artefatti solo-in-reference che l'agente deve produrre (es. `attempt_log.json`) ottengono uno stub nel seed, registrato in `provenance.seed_stubs` insieme a origine del holdout e timestamp.
- Il bundle pubblico AFB **esclude** hidden test e reference (disclosure policy): senza materiali privati l'import è `PARTIAL` (exit 2) con un `MISSING.md` che elenca gli hidden check pubblicati come guida d'autore. Le fixture importate complete contengono materiale privato del bench: NON vanno committate in un repo pubblico (qui: `.gitignore fixtures/afb-*`).
- I check di processo/rubrica di AFB (trace, comunicazione) non diventano test aeh: passa solo la parte meccanicamente eseguibile. I risultati delle matrici tornano in AFB come evidence, citando la versione di aeh usata.

Al primo import reale (v0.3.0) `aeh validate` ha scovato un drift reale nel bench: l'hidden test di `afb-v0-006` aspettava un trailing newline che la nota pubblicata non ha — confermato dal validator interno di AFB e corretto lato holdout privato (il file pubblico è frozen dal manifest SHA-256).

## Qualità

- 70 test pytest, coverage 94% (gate CI: 80%), ruff clean.
- La suite prova esplicitamente: separation (nessun hidden nel workspace), tamper-proofing (edit ai test → grading invariato), contratto fixture (4 fixture), timeout solver, exit code CLI, negazione di rete REALE (probe su loopback: refused senza sandbox, EPERM/unreachable sotto), fallback onesto del backend, ingestione usage, matrice, e import AFB (mappatura, rename, stub, holdout esterno, partial, contratto pieno della fixture importata).
