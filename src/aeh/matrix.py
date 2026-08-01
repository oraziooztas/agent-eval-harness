"""Cross-solver matrix: aggregate N run dirs into per-solver rows.

Answers the cost question ("what does a solved task cost with THIS agent?"),
not just the accuracy one. Reads the results.json of each run; runs without
usage data still count for solve rate but not for cost.

Hidden gap is NOT self-interpreting. On fixtures with a real hidden-check
separation the public suites are a regression guard that a do-nothing solver
also passes, so a high gap alone says nothing: it has to be read against the
floor that the same fixture set produces under `--noop`. The floor is therefore
derived from the matrix itself (a `builtin:noop` run), never hardcoded — a
constant measured on one fixture set would silently travel to another. When no
floor run is present the matrix says so instead of printing a bare number.
See docs/METRICS.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median

#: Labels written by `aeh run --noop` / `--ref` when the caller passes no --label.
FLOOR_LABEL = "builtin:noop"
CEILING_LABEL = "builtin:ref"


def load_run(run_dir: str | Path) -> dict:
    path = Path(run_dir).resolve() / "results.json"
    if not path.is_file():
        raise FileNotFoundError(f"results.json non trovato in {path.parent}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_matrix(run_dirs: list[str | Path]) -> dict:
    """Aggregate runs grouped by solver label."""
    groups: dict[str, list[dict]] = {}
    for rd in run_dirs:
        data = load_run(rd)
        groups.setdefault(data["solver"]["label"], []).append(data)

    rows = []
    for label, runs in sorted(groups.items()):
        solved = sum(1 for r in runs if r["grade"]["solved"])
        latencies = [
            r["solver"]["duration_seconds"]
            for r in runs
            if r["solver"].get("duration_seconds")
        ]
        gaps = []
        for r in runs:
            pub, hid = r["grade"]["public"], r["grade"]["hidden"]
            if pub["total"] and hid["total"]:
                gaps.append(100 * (pub["passed"] / pub["total"] - hid["passed"] / hid["total"]))
        costed = [
            r["solver"]["usage"]["cost_eur"]
            for r in runs
            if r["solver"].get("usage") and r["solver"]["usage"].get("cost_eur") is not None
        ]
        total_cost = round(sum(costed), 4) if costed else None
        cost_per_solved = (
            round(sum(costed) / solved, 4) if costed and solved and len(costed) == len(runs) else None
        )
        rows.append(
            {
                "solver": label,
                "role": _role(label),
                "runs": len(runs),
                "solved": solved,
                "solve_rate": round(solved / len(runs), 3),
                "hidden_gap_pp": round(sum(gaps) / len(gaps), 1) if gaps else None,
                "gap_vs_floor_pp": None,  # filled below, once the floor is known
                "median_latency_s": round(median(latencies), 1) if latencies else None,
                "runs_with_cost": len(costed),
                "total_cost_eur": total_cost,
                "cost_per_solved_eur": cost_per_solved,
            }
        )
    rows.sort(key=lambda r: (-r["solve_rate"], r["solver"]))
    calibration = _calibrate(rows)
    return {
        "runs_total": sum(r["runs"] for r in rows),
        "calibration": calibration,
        "solvers": rows,
    }


def _role(label: str) -> str | None:
    if label == FLOOR_LABEL:
        return "floor"
    if label == CEILING_LABEL:
        return "ceiling"
    return None


def _calibrate(rows: list[dict]) -> dict:
    """Locate floor/ceiling rows and express every other row against the floor.

    Mutates `rows` in place to fill `gap_vs_floor_pp`. Returns the calibration
    block, including the warnings that make a missing floor loud instead of
    silent: without it a hidden gap is a number with no scale.
    """
    def _find(role: str) -> dict | None:
        for r in rows:
            if r["role"] == role:
                return {
                    "solver": r["solver"],
                    "hidden_gap_pp": r["hidden_gap_pp"],
                    "solve_rate": r["solve_rate"],
                }
        return None

    floor, ceiling = _find("floor"), _find("ceiling")
    warnings = []
    if floor is None:
        warnings.append(
            f"Nessun run `{FLOOR_LABEL}` in questa matrice: l'hidden gap non ha un pavimento di "
            "riferimento e da solo non è interpretabile (un solver che non tocca nulla passa "
            "comunque i public). Aggiungi un `aeh run <fixture> --noop` sulle stesse fixture."
        )
    if ceiling is None:
        warnings.append(
            f"Nessun run `{CEILING_LABEL}`: manca il soffitto, quindi non è dimostrato che le "
            "fixture di questa matrice siano risolvibili al 100%."
        )

    floor_gap = floor["hidden_gap_pp"] if floor else None
    if floor_gap is not None:
        for r in rows:
            if r["hidden_gap_pp"] is not None:
                r["gap_vs_floor_pp"] = round(r["hidden_gap_pp"] - floor_gap, 1)

    return {"floor": floor, "ceiling": ceiling, "warnings": warnings}


def write_matrix(run_dirs: list[str | Path], out_dir: str | Path) -> Path:
    """Write matrix.json + matrix.md into out_dir; returns the .md path."""
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    data = build_matrix(run_dirs)
    (out / "matrix.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    def cell(value: object, suffix: str = "") -> str:
        return "n/a" if value is None else f"{value}{suffix}"

    cal = data["calibration"]
    badge = {"floor": " ⬇︎ floor", "ceiling": " ⬆︎ ceiling"}

    lines = [
        "# Matrice cross-solver",
        "",
        (
            f"Run aggregati: {data['runs_total']}. Il costo è solver-reported "
            "(vedi README): righe senza usage completa non hanno €/solved."
        ),
        "",
        (
            "**Come si legge**: il segnale primario è `solve rate`. L'`hidden gap` va letto "
            "contro il floor, non in assoluto — `vs floor` ≈ 0 significa che il solver non ha "
            "fatto nulla di utile, anche se i test pubblici sono verdi. Il *public pass rate* "
            "non compare: è un regression guard, costante per costruzione (docs/METRICS.md)."
        ),
        "",
    ]
    if cal["floor"]:
        lines += [
            (
                f"Floor misurato su questi run: `{cal['floor']['solver']}` a "
                f"**{cell(cal['floor']['hidden_gap_pp'])} pp** di hidden gap."
            ),
            "",
        ]
    for w in cal["warnings"]:
        lines += [f"> ⚠️ {w}", ""]

    lines += [
        "| solver | run | solved | solve rate | hidden gap (pp) | vs floor (pp) | latenza mediana | costo tot | €/task risolto |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in data["solvers"]:
        lines.append(
            f"| `{r['solver']}`{badge.get(r['role'], '')} | {r['runs']} | {r['solved']} "
            f"| {r['solve_rate']:.0%} | {cell(r['hidden_gap_pp'])} "
            f"| {cell(r['gap_vs_floor_pp'])} | {cell(r['median_latency_s'], 's')} "
            f"| {cell(r['total_cost_eur'], ' €')} | {cell(r['cost_per_solved_eur'], ' €')} |"
        )
    md = out / "matrix.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md
