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
  --solver 'claude -p "$(cat PROMPT.md)" --permission-mode acceptEdits'
```

Ogni run produce `runs/{id}-{ts}/` con `workspace/` (ciò che l'agente ha visto e toccato), `grading/` (la valutazione pulita), `transcript.txt`, `results.json` e `run_card.md` (verdetto, tabella public/hidden, hash del set nascosto, riproduzione).

Exit code: `0` solved · `1` errore harness/contratto · `2` run valido ma non risolto.

## Cosa misura (e cosa no)

- Misura: capacità dell'agente di risolvere il contratto REALE del task, non solo i test che vede. Il gap public-pass vs hidden-pass è il segnale interessante (overfitting ai test visibili).
- `tamper_suspect`: file con nome da hidden test creati dall'agente nel workspace vengono flaggati nel run card (il grading resta comunque valido).
- Non fa (ancora): sandboxing di rete/filesystem del solver (il solver gira col tuo utente: usa agent CLI di cui ti fidi), multi-linguaggio (i test fixture sono `unittest` Python), parallelismo di run.

## Compatibilità AFB

Le fixture usano la stessa forma dell'Agent Failure Eval Bench (seed / public / hidden / reference): un task AFB diventa una fixture aggiungendo `task.json` con i campi sopra e rinominando i file di test secondo i prefissi `test_public*` / `test_hidden*`. Il campo `taxonomy` accetta i codici F01-F12.

## Qualità

- 29 test pytest, coverage 96% (gate CI: 80%), ruff clean.
- La suite prova esplicitamente: separation (nessun hidden nel workspace), tamper-proofing (edit ai test → grading invariato), contratto fixture, timeout solver, exit code CLI.
