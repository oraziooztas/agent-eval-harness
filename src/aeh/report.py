"""Run artifacts: results.json (machine) + run_card.md (human)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from aeh.fixture import Fixture
from aeh.grader import GradeResult
from aeh.runner import SolverResult


def write_results(
    run_dir: str | Path,
    fixture: Fixture,
    solver_label: str,
    solver_result: SolverResult | None,
    grade_result: GradeResult,
    usage: dict | None = None,
    credential: dict | None = None,
) -> Path:
    run_path = Path(run_dir).resolve()
    payload = {
        "fixture": {
            "id": fixture.id,
            "title": fixture.title,
            "taxonomy": list(fixture.taxonomy),
            "root": str(fixture.root),
        },
        "solver": {
            "label": solver_label,
            "status": solver_result.status if solver_result else "builtin",
            "returncode": solver_result.returncode if solver_result else None,
            "duration_seconds": round(solver_result.duration_seconds, 2) if solver_result else 0.0,
            "sandbox": solver_result.sandbox if solver_result else "off",
            "usage": usage,
            # Provenienza della credenziale: quale chiave ha pagato il run (fingerprint,
            # mai il valore). None = nessuna API key esplicita → run builtin, oppure
            # solver che gira su credenziali proprie/abbonamento: costo non attribuibile.
            "credential": credential,
        },
        "graded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "grade": grade_result.to_dict(),
    }
    out = run_path / "results.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def write_run_card(run_dir: str | Path) -> Path:
    """Render run_card.md from an existing results.json."""
    run_path = Path(run_dir).resolve()
    data = json.loads((run_path / "results.json").read_text(encoding="utf-8"))
    g = data["grade"]

    def table(bucket: dict) -> str:
        rows = ["| test | esito |", "|---|---|"]
        for t in bucket["tests"]:
            short = t["id"].split(".", 1)[-1]
            mark = {"pass": "✅ pass", "fail": "❌ fail", "error": "💥 error"}[t["outcome"]]
            rows.append(f"| `{short}` | {mark} |")
        return "\n".join(rows)

    tamper = (
        "\n> ⚠️ **Tamper suspect**: trovati nel workspace file con nome da hidden test: "
        + ", ".join(f"`{p}`" for p in g["tamper_suspect"])
        + ". Il grading resta valido (usa copie intatte), ma il run va rivisto.\n"
        if g["tamper_suspect"]
        else ""
    )

    usage = data["solver"].get("usage")
    if usage and usage.get("error"):
        usage_line = f"\n- Usage: ⚠️ {usage['error']}"
    elif usage:
        cost = f"{usage['cost_eur']} €" if usage.get("cost_eur") is not None else "n/a"
        usage_line = (
            f"\n- Usage (solver-reported): {usage.get('tokens_in') or 'n/a'} tok in / "
            f"{usage.get('tokens_out') or 'n/a'} tok out · costo {cost}"
        )
    else:
        usage_line = ""

    cred = data["solver"].get("credential")
    cred_line = (
        f"\n- Credenziale: `${cred['env_var']}` → `{cred['injected_as']}` ({cred['fingerprint']}) "
        "— API key esplicita, non abbonamento"
        if cred
        else ""
    )

    card = f"""# Run card — {data['fixture']['id']}

**Verdetto: {g['verdict']}** · public {g['public']['passed']}/{g['public']['total']} · hidden {g['hidden']['passed']}/{g['hidden']['total']}

- Fixture: {data['fixture']['title']} (taxonomy: {', '.join(data['fixture']['taxonomy']) or 'n/a'})
- Solver: `{data['solver']['label']}` (status: {data['solver']['status']}, {data['solver']['duration_seconds']}s)
- Sandbox rete: grading `{g.get('grading_sandbox', 'n/a')}` · solver `{data['solver'].get('sandbox', 'off')}`{usage_line}{cred_line}
- Graded at: {data['graded_at']}
- Hidden set SHA-256: `{g['hidden_sha256'][:16]}…` (prova di quali check hanno valutato il run)
{tamper}
## Test pubblici (visti dall'agente)

{table(g['public'])}

## Test nascosti (mai visti dall'agente)

{table(g['hidden'])}

## Riproduzione

```bash
aeh run {data['fixture']['root']} --solver "<comando>"
```
"""
    out = run_path / "run_card.md"
    out.write_text(card, encoding="utf-8")
    return out
