# DEVLOG — agent-eval-harness

## 2026-07-27 — `uv.lock` deciso (ignorato) + 🔴 `main` divergente da `origin/main`

**`uv.lock` → gitignorato, e la ragione è specifica di questo repo.** Era
untracked da giorni, quindi né tracciato né ignorato: limbo. Il gemello
`sae-early-warning` **lo traccia**, e fa bene: la sua CI gira `uv sync --dev`, il
lock la rende riproducibile. Qui la CI fa `pip install -e ".[dev]"` e **non usa
uv**, e il runtime dichiara `dependencies = []` → il lock fisserebbe solo il
toolchain di dev locale, con **zero** effetto sulla riproducibilità del progetto,
aggiungendo churn su un repo pubblico. I due repo divergono perché divergono le
CI, non per incoerenza.

**🔴 Il problema vero, che non era nel backlog.** `main` locale e `origin/main`
sono **divergenti**: 1 commit per parte, base comune `811e3ee`.
- remoto: `e101681` *docs: translate README to English (**#1**)* — 20/07, merged
  **via PR su GitHub** e mai tirato in locale;
- locale: `279bceb` *docs: record the AFB calibration matrix* — 25/07, committato
  sulla base vecchia.

Il branch `feat/api-credential-and-cost-estimate` (1 commit, `30cf865`) **non ha
upstream** e parte da quel `main` stantio. Un `git push` naïf viene rifiutato; il
rischio serio è "risolverlo" con un force-push che seppellisce la PR #1 già
merged.

**Predetto senza toccare nulla** (`git merge-tree --write-tree`, dry-run):
- `main` → `origin/main`: **CLEAN** (il locale toccava solo `DEVLOG.md`, il
  remoto solo `README.md`);
- `feat/…` → `origin/main`: **CONFLITTO su `README.md`**, atteso — il remoto ha
  riscritto tutto il README in inglese (56+/55-) e il branch ci aggiunge 37 righe
  sopra la versione precedente.

**✅ Risolto nella stessa sessione, su conferma esplicita di Orazio.** Ref di
backup creati prima di toccare qualsiasi cosa
(`backup/main-pre-rebase-2026-07-27`, `backup/feat-pre-rebase-2026-07-27`), poi:
1. `main` rebasato su `origin/main` — clean come previsto, `279bceb` → `6864d23`;
   70 pytest verdi; pushato. **La PR #1 non è stata seppellita**: nessun
   force-push, `e101681` resta nella storia.
2. Branch feature rebasato su `main` — conflitto su `README.md`, previsto.
   **Risolto tenendo l'inglese e traducendo le aggiunte**: il branch scriveva le
   due sezioni nuove (`Credential: API key, not subscription` + revisione di
   `Cost per solved task`) in italiano, sopra il README pre-traduzione. Mergiarle
   così avrebbe reso bilingue il README pubblico, vanificando la PR #1.
   Verificato a posteriori: 0 marker di conflitto, 0 residui italiani.

Storia ora lineare: `e101681` → `6864d23` → `b4ff49b` → `4fa379d`.

**🔴 Il push ha scoperto una CI rossa pre-esistente, e la causa è un linter non
pinnato.** Dopo il push la CI falliva su **entrambi** i branch — incluso `main`,
su un commit **solo-docs**. Non l'ha rotta il rebase: `ruff>=0.5` senza upper
bound fa installare alla CI sempre l'ultima, e la **0.16.0 (uscita di recente) ha
allargato il set di regole di default** (`PLW1510`, `UP017`, `BLE001`, `ISC004`,
`TRY004`, `FURB188`). In locale il venv aveva la **0.15.21** → `ruff check src
tests` diceva "All checks passed", la CI trovava **11 errori** sullo stesso
codice. I file colpiti (`tests/test_sandbox.py`, `report.py`, `importer.py`) sono
del 17-20/07: il guasto era latente e `279bceb`, mai pushato, non aveva mai
girato in CI.

Sistemato in due mosse, non una:
- **Causa**: `ruff>=0.16,<0.17` nell'extra `dev`. Un linter non vincolato rende il
  lint non riproducibile e può far diventare rosso un repo senza toccare una riga
  — inaccettabile qui, dove la riproducibilità è il prodotto. Alzare il bound ora
  è una scelta esplicita.
- **Sintomi**: 11 → 0. `check=False` esplicito sui 4 `subprocess.run` (era già il
  default: comportamento **identico**, ora dichiarato, e il commento dice perché —
  un exit code non-zero *è* il risultato, non un errore); `datetime.UTC`;
  `PackageNotFoundError` al posto di `except Exception`; concatenazione di stringhe
  parentesizzata in `matrix.py`.
- **Su `TRY004` ruff ha torto e l'ho tenuto zittito con motivazione**: quel
  `ValueError` in `runner.py` è deliberatamente dentro la tupla dell'`except` due
  righe sotto, che lo converte in un dict di errore soft. Alzare `TypeError` come
  suggerito lo farebbe **sfuggire e crashare**. `# noqa: TRY004` con il perché
  scritto accanto.

Verificato con la **0.16.0 installata in locale** (cioè la stessa della CI, non
quella che avevo): `ruff check src tests` pulito, 76 pytest, coverage 94,74%
contro il gate 80%.

**Lezione di metodo, costata un push rosso**: avevo verificato con `ruff check .`,
la CI gira `ruff check src tests` — e soprattutto con una **versione diversa**.
Verificare "il progetto è pulito" non è verificare "la CI passerà": vale il
comando esatto della CI, con le versioni della CI. Il pin di ruff è ciò che rende
questa frase vera anche domani.

## 2026-07-26 — credenziale cablata, catena costi validata a spesa zero, stima misurata

Chiusa la preparazione lasciata aperta ieri sera. **Nessun modello reale eseguito, zero speso**: la riga con modelli reali ora è a un comando di distanza, e l'ipotesi da 50k token è stata verificata invece che ereditata.

**Stato credenziale: ASSENTE, e non per caso.** Accertato, non assunto: `ANTHROPIC_API_KEY` non è nell'ambiente, e `~/.zshrc:80` fa `unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN` a ogni shell interattiva, con tanto di commento — *"Claude Code — safety: prevent API overage fallback"*. Non è una dimenticanza: è un guardrail deliberato perché Claude Code non sconfini sui crediti API. Conseguenza pratica che vale la pena scrivere: **un `export ANTHROPIC_API_KEY` fatto in un'altra tab non sopravvive**, ogni nuova shell lo cancella.

Quindi il path è stato cablato **rispettando** quel guardrail invece di combatterlo. Nuovo flag `--require-api-key [VAR]` (default `ANTHROPIC_API_KEY`):
- legge la chiave da `VAR` e la inietta come `ANTHROPIC_API_KEY` **solo nell'env del sottoprocesso solver** — la shell chiamante non viene toccata, il guardrail resta in piedi se la chiave sta in `AEH_ANTHROPIC_API_KEY`;
- se manca, **exit 1 prima di preparare il workspace**, con un messaggio che dice dove prendere la chiave e perché l'abbonamento non va bene. Mai un fallback silenzioso;
- `results.json` registra `solver.credential`: variabile d'origine + `sha256` troncato della chiave (**mai il valore**), così si sa quale credenziale ha pagato quale run;
- guardia aggiuntiva: se il solver *sembra* un agent CLI (`claude`, `codex`, `aider`, …) e `--require-api-key` non c'è, `aeh` avvisa su stderr. Era il modo esatto in cui si sarebbe bruciata quota di sessione credendo di spendere dollari.

**Validato a costo zero (9 run, nessuna API contattata):**
- floor/ceiling builtin riprodotti identici al 25/07 — `builtin-noop` 0/3 solved, hidden gap **58.3pp**; `builtin-ref` 3/3, **0.0pp**. Il refactor non ha mosso nulla;
- gate negativo: senza chiave → exit 1, messaggio pieno, `workspace/` **non creato**;
- catena contabile completa con un **mock solver** (solo `cp` + `printf`, zero rete): credenziale iniettata e vista dal sottoprocesso → `$AEH_USAGE_FILE` → moltiplicatori prezzo → `results.json` → `aeh matrix`. Costo calcolato **0.1557** contro 0.1557 atteso a mano su 49.840 in / 5.600 out a 2/10 per Mtok. Matrice a 9 run: riga mock 3/3 solved, **0.473 costo totale**, **0.1577 per task risolto**;
- chiave finta cercata in `results.json`, `run_card.md`, `transcript.txt`: **non trapela in nessuno dei tre**;
- 76 pytest (6 nuovi sulla credenziale), ruff clean.

**La stima ora è misurata — e il misurato ribalta la composizione dell'ipotesi.** `scripts/estimate_cost.py` (stdlib-only, cross-check `tiktoken` o200k_base se già installato, mai come dipendenza) prepara i workspace veri e conta il contesto che l'agente può leggere:

| fixture | file | char | tok (chars/4) | tok (BPE) | scarto |
|---|---:|---:|---:|---:|---:|
| `afb-v0-002` | 5 | 2.019 | 505 | 500 | +1,0% |
| `afb-v0-006` | 9 | 3.123 | 781 | 709 | +10,2% |
| `afb-v0-009` | 5 | 2.393 | 598 | 553 | +8,1% |

**628 token/task di media: l'1,3% dei 50k assunti.** Le fixture non fanno il costo. Lo fanno lo scaffold dell'agente (system prompt + schemi dei tool, rispediti a ogni turno) e il numero di turni — roba che vive nell'agent CLI, non in questo repo, e che **nessuna misura statica può chiudere**. Il metodo di conteggio è dichiarato: `chars/4`, che sul nostro materiale sovrastima il BPE dell'1-10%.

Il costo quindi resta un'ipotesi *parametrica*, ma esplicita. Tre scenari sul loop (turni · scaffold · crescita · output, caching sì/no), matrice a 3 modelli × 3 fixture, **colonna in USD** (Haiku 4.5 `1/5` + Sonnet 5 promo `2/10` + Opus 5 `5/25`):

| scenario | ipotesi | USD totali |
|---|---|---:|
| lean | 5 turni, scaffold 8k, caching | **0,81** |
| base | 8 turni, scaffold 12k, caching | **1,89** |
| heavy | 15 turni, scaffold 18k, no caching | **11,35** |

Nota di onestà sull'ipotesi di ieri: allo scenario *base* il modello dà ~50k input/task, cioè **l'ipotesi 50k era ben calibrata** — sbagliata era solo la sua composizione (non le fixture, lo scaffold). E la lettura decisionale non cambia: fra magro e grasso ballano 14×, ma il tetto è ~11 USD. **Non serve una stima migliore per decidere**; serve il primo run strumentato per sostituirla con una misura. Il rischio vero non è mai stato l'importo: era lanciare 9 run e scoprire dopo che pagava l'abbonamento — ed è esattamente ciò che ora il codice impedisce.

**Comando pronto** (una fixture, Haiku, il più economico: serve a *misurare*, non a valutare):

```bash
AEH_ANTHROPIC_API_KEY='sk-ant-…' aeh run fixtures/afb-v0-002 \
  --solver 'claude -p "$(cat PROMPT.md)" --permission-mode acceptEdits --model haiku' \
  --require-api-key AEH_ANTHROPIC_API_KEY \
  --label 'haiku-4.5' --price-in 1 --price-out 5
```

(`--model haiku` è l'alias: `claude --help` documenta il meccanismo con esempi `opus`/`sonnet`/`fable` e nomi pieni tipo `claude-fable-5`, senza elencare l'alias Haiku — non l'ho verificato a fonte, e un ID sbagliato fallisce a costo zero. Il modello va scelto lì e **non** va cambiato senza cambiare anche `--price-in/--price-out`, che non lo sanno da soli.)

Poi si legge `runs/…/results.json` → `solver.usage`: se `tokens_in` è nell'ordine dei 50k l'ipotesi tiene e si lanciano le 8 righe restanti; se è 5k o 500k, si ricalcola prima di spendere. `aeh matrix` va poi chiamato includendo **anche** i 6 run builtin, o i numeri dei modelli restano senza scala.

📌 Restano validi i due finding del 25/07, riconfermati oggi dai run: **mai riportare il public pass rate** su queste 3 fixture (costante 100%, anche con `--noop`), e su `afb-v0-002` fra noop e ref balla **un solo hidden check** (3/4 → 4/4), range troppo stretto per separare modelli vicini.
📌 `--price-in/--price-out` restano moltiplicatori puri: passando USD, il campo si chiama `cost_eur` ma contiene dollari. Ora è scritto anche nel README e nell'help della CLI.

## 2026-07-25 (sera) — la riga con modelli reali: il gate non è il denaro, è la credenziale

Preparazione della decisione di spesa lasciata aperta stamattina. **Nessun modello reale eseguito**, nessun euro speso: qui c'è solo il conto fatto prima, così la decisione è un sì/no e non una ricerca.

**Prezzi verificati alla fonte oggi** (`platform.claude.com/docs/en/about-claude/pricing`, non a memoria), USD per Mtok, input/output:
Haiku 4.5 `1 / 5` · Sonnet 5 `2 / 10` (promo fino al **31/08/2026**, poi `3 / 15`) · Opus 5 `5 / 25` · Fable 5 `10 / 50`. Batch API = **-50%** su entrambi.

**Stima per una matrice a 3 modelli × 3 fixture AFB.** Ipotesi dichiarata, non misurata: ~50k token di input e ~8k di output per task risolto da un agente di coding (le fixture sono piccole, il costo lo fa il loop di iterazione).

| Solver | USD/task | 3 fixture | Cosa compra |
|---|---|---|---|
| Haiku 4.5 | ~0,09 | ~**0,27** | il floor realistico: se sta vicino a noop (58,3pp) sai che la fixture discrimina |
| Sonnet 5 | ~0,18 | ~**0,55** | il caso d'uso vero, e la promo scade il 31/08 |
| Opus 5 | ~0,45 | ~**1,35** | il ceiling di mercato contro `builtin-ref` (0,0pp) |
| **totale** | | **~2,2 USD** | matrice completa a 5 righe con floor e ceiling builtin |

⚠️ **Il numero sopra ribalta la premessa.** Questa riga è stata trattata per settimane come una spesa da decidere: costa **circa due dollari**. Il vero gate è un altro.

**Il gate vero: quale credenziale usa il solver.** Il comando d'esempio del README è `claude -p "$(cat PROMPT.md)" --permission-mode acceptEdits`. Se `claude` gira sull'abbonamento, quei run **non costano dollari, consumano la tua quota di sessione** — che è la risorsa scarsa davvero (due session limit colpiti il 10/07). Con `ANTHROPIC_API_KEY` invece paghi i ~2 USD sopra e la quota resta intatta.
👉 Decisione da prendere: **API key dedicata per i run di eval**. È anche l'unica strada in cui `$AEH_USAGE_FILE` produce un €/task-risolto onesto, perché sotto abbonamento il costo per token semplicemente non esiste.

**Sequenza consigliata (non eseguita, aspetta il tuo via):**
1. **Una riga sola, Haiku, una fixture** — non per il risultato ma per *misurare* i token veri e sostituire la mia ipotesi da 50k/8k con un numero.
2. Ricalcolare la tabella con i token misurati. Se l'ordine di grandezza tiene, lanciare le 8 righe restanti in un colpo.
3. `aeh matrix` includendo **anche** i due run builtin: senza floor e ceiling nella stessa tabella i numeri dei modelli non hanno scala.

```bash
export ANTHROPIC_API_KEY=…                       # NON l'abbonamento
aeh run fixtures/afb-v0-002 \
  --solver 'claude -p "$(cat PROMPT.md)" --permission-mode acceptEdits' \
  --label 'haiku-4.5' --price-in 1 --price-out 5
# ripetere su afb-v0-006 e afb-v0-009, poi per ogni modello, poi:
aeh matrix runs/ --out runs/matrix-afb-models
```
📌 `--price-in/--price-out` sono moltiplicatori puri: passando i prezzi in USD la colonna dice "EUR" ma i numeri sono dollari. O converti tu al cambio del giorno, o leggi quella colonna come USD.
📌 Ricorda il finding di stamattina: su queste 3 fixture **non riportare mai il public pass rate** (costante al 100%), e su `afb-v0-002` fra noop e ref ballano 3/4 → 4/4, cioè un solo hidden check: troppo stretta per separare modelli vicini.

## 2026-07-25 — prima matrice AFB: calibrata sui builtin, non sui modelli (AFK)

- Backlog AFK-queue "prima matrice cross-model AFB eseguita con aeh": eseguita, ma **deliberatamente senza solver a pagamento**. Prima di misurare un modello serve sapere dove stanno pavimento e soffitto dello strumento, e quelli costano zero: `--ref` e `--noop` su tutte e 3 le fixture AFB, 6 run, poi `aeh matrix`.
- Matrice in `runs/matrix-afb-calibration/` (gitignored come tutti i `runs/`): **`builtin-ref` 3/3 solved, solve rate 100%, hidden gap 0.0pp** · **`builtin-noop` 0/3 solved, solve rate 0%, hidden gap 58.3pp**. Sono i due estremi entro cui dovrà cadere qualunque run di un modello reale.
- **Finding: i test pubblici delle 3 fixture AFB non discriminano.** Con `--noop` — un solver che non tocca nulla — il pubblico passa comunque **4/4 (002), 2/2 (006), 3/3 (009)**. Il segnale sta interamente nei nascosti: noop fa hidden 3/4, 1/4, 1/4. Verificato alla fonte sulla run card 006: i due test pubblici coprono `simple_child_is_joined` e `spaces_are_preserved`, entrambi già soddisfatti dal seed; il contratto vero (path escape, attempt log, segmenti annidati, byte-preservation) vive solo negli hidden.
- Conseguenza operativa: **"public pass rate" non va mai riportato come segnale su queste fixture** — è costante a 100% per costruzione. L'unica metrica informativa è solve rate, e il `hidden gap` va letto contro il floor di 58.3pp: un modello che ci finisce vicino non ha fatto nulla di utile, anche se la sua run "passa i test".
- Nota di design, non difetto: è la separazione hidden-check che funziona come previsto. Ma significa che l'eval misura se l'agente **legge la spec**, non se fa passare i test che vede — un agente che si ferma al verde visibile ha zero gradiente per accorgersi che manca tutto.
- Dinamica ristretta su **afb-v0-002**: fra noop e ref ballano 3/4 → 4/4, cioè **un solo hidden check**. Range troppo stretto per distinguere modelli vicini; da tenere presente prima di leggere differenze su quella fixture.
- **Non eseguito**: righe con modelli reali. Servono quota/API e la decisione è di Orazio. Comando pronto: `aeh run fixtures/afb-v0-002 --solver '<cmd>' --label '<modello>' --price-in X --price-out Y`, poi `aeh matrix` includendo anche i due run builtin per conservare floor e ceiling nella stessa tabella.

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
