# Cost model — quanto costa una riga di `aeh matrix`

Scritto 2026-08-07. Nasce dalla riga del DEVLOG *"Non eseguito: righe con modelli
reali. Servono quota/API e la decisione è di Orazio"*: la decisione era ferma
senza un numero accanto. Questo file mette il numero, non esegue nulla.

**Nessun prezzo è hardcoded qui.** Stessa scelta di `llm_as_judge.py` in
`sae-early-warning`: una tabella prezzi stale sotto-riporta la spesa in silenzio,
ed è peggio di nessuna tabella. Sotto ci sono i token; i prezzi li metti tu dalla
pricing page al momento in cui lanci.

## Il pavimento, misurato

Superficie che l'agente vede all'avvio, cioè `PROMPT.md` (dal campo prompt di
`task.json`) + `seed/` + `tests_public/`, per fixture:

| fixture | char | ~token input |
|---|---:|---:|
| afb-v0-002 | 1589 | 397 |
| afb-v0-006 | 2677 | 669 |
| afb-v0-009 | 1956 | 489 |
| fx-001-csv-dedup | 1176 | 294 |
| fx-002-slugify | 955 | 238 |
| fx-003-retry-backoff | 1226 | 306 |
| fx-004-markdown-toc | 1742 | 435 |
| **7 fixture** | | **~2 828** |

Convenzione ~4 caratteri/token, la stessa che usa `llm_as_judge.estimate_input_tokens`.
Media ~404 token per task.

## Perché quel pavimento non è il costo

2 828 token è quello che costerebbe una **singola chiamata per task**. Un solver
agentico non lavora così: rilegge file, scrive codice, lancia i test, legge il
fallimento e itera, e a ogni turno rimanda il prefisso della conversazione. Il
costo è dominato dal loop, non dal workspace.

Modello con le assunzioni scoperte, da correggere quando avrai un run vero:

```
input_per_task  ≈ W × T × (T+1)/2      # W=workspace, T=turni, history ri-inviata
output_per_task ≈ O × T                # O=output medio per turno
```

Con W≈404, T=10 turni, O≈400 token:

| | per task | × 7 fixture | × 4 modelli |
|---|---:|---:|---:|
| input | ~22 200 | ~155 000 | ~622 000 |
| output | ~4 000 | ~28 000 | ~112 000 |

⚠️ **T=10 e O=400 sono assunzioni, non misure.** Sono la parte fragile: il costo
è quadratico in T, quindi un agente che itera 30 volte invece di 10 costa ~9×,
non 3×. Il primo run vero va fatto con `--label` su **una** fixture, poi si
rilegge `$AEH_USAGE_FILE` e si sostituiscono W, T, O con i valori osservati.

## Il conto in euro

`aeh matrix` calcola già €/task-risolto da `--price-in` / `--price-out`. Formula:

```
costo = (input_totale / 1e6) × price_in + (output_totale / 1e6) × price_out
```

Sostituisci `price_in` e `price_out` dalla pricing page del provider al momento
del run e moltiplica per le righe della tabella sopra.

## La conclusione che conta

Anche con l'assunzione pessimistica (T=30 → input ~5,6M token su 4 modelli), gli
ordini di grandezza restano quelli di **una matrice piccola**, non di un training
run. Il fattore che decide non è il prezzo: è che **7 fixture sono poche perché
una matrice cross-model distingua modelli vicini**, e su `afb-v0-002` il DEVLOG
registra già il problema — fra noop e reference ballano 3/4 → 4/4, cioè **un solo
hidden check** di dinamica.

Detto altrimenti: spendere sulla matrice adesso compra una tabella che non
separa. Il collo di bottiglia è il numero di fixture, e va risolto prima.

**Nessuna spesa effettuata per produrre questo documento.**
