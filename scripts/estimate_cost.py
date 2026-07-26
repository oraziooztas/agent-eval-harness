#!/usr/bin/env python3
"""Stima MISURATA del costo di una matrice cross-model, senza spendere un centesimo.

Separa nettamente due metà:

* **misurata** — il contesto iniziale che l'agente può leggere: `PROMPT.md` più
  ogni file del workspace preparato da ``prepare_workspace`` (seed + test
  pubblici). È il pavimento dell'input: sotto questo numero non si va.
* **assunta** — il loop dell'agente (quanti turni, quanto output per turno).
  È la metà che fa davvero il costo, e qui NON è misurata: è un parametro
  esplicito (``--turns``, ``--out-per-turn``) che chiunque può cambiare.

Conteggio token, metodo dichiarato in output:

* default stdlib: euristica ``chars/4`` (nessuna dipendenza);
* cross-check con ``tiktoken`` (o200k_base) **se già installato** — non è una
  dipendenza del pacchetto e non viene mai installato da qui. È comunque un
  tokenizer OpenAI: il tokenizer di Claude non è pubblico, quindi resta una
  approssimazione, utile solo per stimare l'errore dell'euristica.

Uso::

    python3 scripts/estimate_cost.py fixtures/afb-v0-002 fixtures/afb-v0-006 …

Non esegue solver, non tocca la rete, non usa credenziali.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aeh.fixture import Fixture  # noqa: E402
from aeh.runner import prepare_workspace  # noqa: E402

#: USD per Mtok (input, output). Verificati alla fonte il 25/07/2026 su
#: platform.claude.com/docs/en/about-claude/pricing — non a memoria.
PRICES_USD: dict[str, tuple[float, float]] = {
    "Haiku 4.5": (1.0, 5.0),
    "Sonnet 5 (promo→31/08)": (2.0, 10.0),
    "Sonnet 5 (post-promo)": (3.0, 15.0),
    "Opus 5": (5.0, 25.0),
    "Fable 5": (10.0, 50.0),
}

CHARS_PER_TOKEN = 4.0


def _tiktoken_counter():
    """Ritorna un contatore BPE se tiktoken è già presente, altrimenti None."""
    try:
        import tiktoken  # noqa: PLC0415
    except ImportError:
        return None
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception:  # pragma: no cover - rete assente o cache mancante
        return None
    return lambda text: len(enc.encode(text, disallowed_special=()))


@dataclass(frozen=True)
class Measured:
    fixture_id: str
    prompt_chars: int
    context_chars: int
    files: int
    prompt_tokens_bpe: int | None
    context_tokens_bpe: int | None

    @property
    def prompt_tokens_heur(self) -> int:
        return round(self.prompt_chars / CHARS_PER_TOKEN)

    @property
    def context_tokens_heur(self) -> int:
        return round(self.context_chars / CHARS_PER_TOKEN)

    def context_tokens(self) -> int:
        """Il numero da usare: il più alto fra euristica e BPE (conservativo)."""
        return max(self.context_tokens_heur, self.context_tokens_bpe or 0)


def measure(fixture_path: str | Path, counter=None) -> Measured:
    """Prepara il workspace reale (gratis) e misura quanto testo vede l'agente."""
    fixture = Fixture.load(fixture_path)
    with tempfile.TemporaryDirectory(prefix="aeh-estimate-") as tmp:
        workspace = prepare_workspace(fixture, Path(tmp) / "run")
        prompt_text = (workspace / "PROMPT.md").read_text(encoding="utf-8")
        texts: list[str] = []
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:  # binari: contati a 0 token, dichiarato
                continue
    blob = "".join(texts)
    return Measured(
        fixture_id=fixture.id,
        prompt_chars=len(prompt_text),
        context_chars=len(blob),
        files=len(texts),
        prompt_tokens_bpe=counter(prompt_text) if counter else None,
        context_tokens_bpe=counter(blob) if counter else None,
    )


def cost_usd(tokens_in: int, tokens_out: int, price_in: float, price_out: float) -> float:
    return tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out


@dataclass(frozen=True)
class Scenario:
    """Ipotesi sul loop dell'agente. Nessuno di questi numeri è misurato."""

    name: str
    turns: int
    scaffold: int  # system prompt + schemi dei tool, rispediti a ogni turno
    growth: int  # tool result accumulati per turno
    out_per_turn: int
    caching: bool

    def tokens(self, ctx: int) -> tuple[int, int]:
        """(input, output) per UNA fixture con contesto misurato ``ctx``."""
        variable = self.turns * ctx + self.growth * self.turns * (self.turns - 1) // 2
        if self.caching:  # scaffold scritto una volta, riletto a 0,1×
            scaffold_in = round(self.scaffold * (1.25 + (self.turns - 1) * 0.1))
        else:
            scaffold_in = self.scaffold * self.turns
        return scaffold_in + variable, self.out_per_turn * self.turns


SCENARIOS = (
    Scenario("lean", turns=5, scaffold=8_000, growth=500, out_per_turn=500, caching=True),
    Scenario("base", turns=8, scaffold=12_000, growth=800, out_per_turn=700, caching=True),
    Scenario("heavy", turns=15, scaffold=18_000, growth=1_200, out_per_turn=900, caching=False),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fixtures", nargs="+")
    ap.add_argument(
        "--assumed-per-task",
        type=int,
        default=50_000,
        help="ipotesi di riferimento da confrontare col misurato (default 50k, DEVLOG 25/07)",
    )
    args = ap.parse_args(argv)

    counter = _tiktoken_counter()
    method = "chars/4 (stdlib)" + (", cross-check tiktoken o200k_base" if counter else "")
    measurements = [measure(f, counter) for f in args.fixtures]
    n = len(measurements)

    print(f"# Stima costo matrice — conteggio token: {method}\n")
    print("## Parte MISURATA — contesto iniziale che l'agente può leggere\n")
    print("| fixture | file | char | tok (chars/4) | tok (BPE) | scarto |")
    print("|---|---:|---:|---:|---:|---:|")
    for m in measurements:
        if m.context_tokens_bpe:
            delta = f"{(m.context_tokens_heur / m.context_tokens_bpe - 1) * 100:+.1f}%"
            bpe = f"{m.context_tokens_bpe:,}"
        else:
            delta, bpe = "n/a", "n/a"
        print(
            f"| `{m.fixture_id}` | {m.files} | {m.context_chars:,} | "
            f"{m.context_tokens_heur:,} | {bpe} | {delta} |"
        )
    total_ctx = sum(m.context_tokens() for m in measurements)
    mean_ctx = total_ctx // n
    print(
        f"\nTotale {n} fixture: **{total_ctx:,} tok** (media {mean_ctx:,}/task; per ogni fixture si prende "
        "il massimo fra euristica e BPE). Solo PROMPT.md: "
        f"{sum(m.prompt_tokens_heur for m in measurements):,} tok, cioè ciò che il solver riceve al turno 1."
    )
    share = mean_ctx / args.assumed_per_task * 100
    print(
        f"\n> **Il misurato falsifica la premessa dell'ipotesi.** {mean_ctx:,} tok/task sono il "
        f"**{share:.1f}%** dei {args.assumed_per_task:,} tok assunti: le fixture non fanno il costo. "
        "Lo fanno lo scaffold dell'agente (system prompt + schemi dei tool, rispediti a ogni turno) "
        "e il numero di turni — due cose che stanno nell'agent CLI, non in questo repo, e che nessuna "
        "misura statica può stabilire. Solo un run strumentato le chiude.\n"
    )

    print("## Parte ASSUNTA — il loop dell'agente (parametri, non misure)\n")
    print("| scenario | turni | scaffold/turno | crescita/turno | out/turno | caching | tok in | tok out |")
    print("|---|---:|---:|---:|---:|:-:|---:|---:|")
    totals: dict[str, tuple[int, int]] = {}
    for sc in SCENARIOS:
        per_fixture = [sc.tokens(m.context_tokens()) for m in measurements]
        tin, tout = sum(a for a, _ in per_fixture), sum(b for _, b in per_fixture)
        totals[sc.name] = (tin, tout)
        print(
            f"| {sc.name} | {sc.turns} | {sc.scaffold:,} | {sc.growth:,} | {sc.out_per_turn:,} | "
            f"{'sì' if sc.caching else 'no'} | {tin:,} | {tout:,} |"
        )

    print(f"\n## Costo della matrice completa ({n} fixture) — colonna in **USD**, non EUR\n")
    header = " | ".join(f"USD {s.name}" for s in SCENARIOS)
    print(f"| modello | {header} | USD heavy in batch (-50%) |")
    print("|---|" + "---:|" * (len(SCENARIOS) + 1))
    for name, (p_in, p_out) in PRICES_USD.items():
        cells = [cost_usd(*totals[s.name], p_in, p_out) for s in SCENARIOS]
        batch = cells[-1] / 2
        print(f"| {name} | " + " | ".join(f"{c:.2f}" for c in cells) + f" | {batch:.2f} |")

    matrix_models = ("Haiku 4.5", "Sonnet 5 (promo→31/08)", "Opus 5")
    print(f"\n### Matrice a 3 modelli ({' + '.join(matrix_models)}) × {n} fixture\n")
    print("| scenario | USD totali |")
    print("|---|---:|")
    for sc in SCENARIOS:
        tot = sum(cost_usd(*totals[sc.name], *PRICES_USD[m]) for m in matrix_models)
        print(f"| {sc.name} | **{tot:.2f}** |")
    lo = sum(cost_usd(*totals["lean"], *PRICES_USD[m]) for m in matrix_models)
    hi = sum(cost_usd(*totals["heavy"], *PRICES_USD[m]) for m in matrix_models)
    print(
        f"\n**Lettura decisionale**: fra lo scenario più magro e il più grasso il costo cambia di un "
        f"ordine di grandezza — **{lo:.2f} → {hi:.2f} USD** — e anche il tetto resta a due cifre "
        "basse. L'incertezza sull'ipotesi non cambia il sì/no: non serve una stima migliore per "
        "decidere, serve il primo run strumentato per sostituirla con una misura. Il rischio vero "
        "non è l'importo, è lanciare 9 run e scoprire dopo che pagava l'abbonamento."
    )
    print(
        "\n⚠️ La colonna è in USD. `aeh run --price-in/--price-out` sono moltiplicatori puri: "
        "passando prezzi in USD il campo `cost_eur` dei report contiene dollari."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
