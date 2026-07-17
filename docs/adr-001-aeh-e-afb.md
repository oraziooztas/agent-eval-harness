# ADR-001 — aeh è il runner, AFB resta il bench: paralleli con ponte

**Stato**: proposto (decisione finale di Orazio) · **Data**: 2026-07-17
**Domanda aperta dal 10/07**: "AFB adotta `aeh` come runner o restano paralleli?"

## Contesto (verificato alla fonte, 17/07)

- **AFB** (`github.com/oraziooztas/agent-failure-eval-bench`, pubblico, v0.1.0-rc1):
  10 task spec, 3 fixture eseguibili *disclosed*, taxonomy F01-F12, rubriche,
  `evidence/` con run card redatte, `scripts/validate_tasks.py`, manifest SHA-256 e
  disclosure/holdout policy. **Non ha un runner**: le due matrici OpenCode sono
  run procedurali documentate come evidence.
- **aeh** (questo repo, v0.2.0, locale): runner con hidden-check separation
  strutturale, grading net-sandboxed, usage/costo solver-reported, `aeh matrix`
  (€/task-risolto). Le fixture hanno la stessa forma AFB
  (seed / public / hidden / reference, taxonomy F01-F12).

## Decisione proposta

**Restano due repo separati. aeh diventa il motore di esecuzione delle prossime
matrici AFB; AFB resta l'artefatto-bench (spec, taxonomy, policy, evidence).**

Il ponte è a senso unico e leggero:

1. importer lato aeh (prossimo passo in MAP) che converte task+fixture AFB in
   fixture aeh (aggiunge `task.json`, rinomina i prefissi dei test);
2. le prossime matrici cross-model girano con `aeh run --label <modello>` +
   `usage.json` per run e si aggregano con `aeh matrix`;
3. in AFB entrano solo gli OUTPUT (run card / matrici redatte in `evidence/`),
   citando la versione di aeh usata ("eseguito con agent-eval-harness vX.Y").

## Perché non fondere

- AFB è pubblico con manifest SHA-256 e holdout policy: vendorare dentro un
  runner che evolve in fretta (v0.2.0 oggi) significherebbe re-release del bench
  a ogni miglioria del tool, senza valore per il bench stesso.
- Separazione delle claim: AFB = evidenza di eval design (mai ranking, vincolo
  EVAL_CARD); aeh = strumento. Mischiarli invita esattamente gli overclaim che
  il CV-safe framing vieta.
- È lo standard del campo: il bench (dataset+rubrica+card) e l'harness di
  esecuzione vivono separati.

## Cosa farebbe cambiare idea

Se AFB v0.2 volesse la **riproducibilità turnkey da parte di terzi**, allora si
pinna aeh come dipendenza versionata dichiarata nel README del bench (riferimento,
non vendoring). Rivalutare a quel punto, non prima.
