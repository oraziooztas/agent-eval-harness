"""Cross-solver matrix: aggregate N run dirs into per-solver rows.

Answers the cost question ("what does a solved task cost with THIS agent?"),
not just the accuracy one. Reads the results.json of each run; runs without
usage data still count for solve rate but not for cost.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median


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
                "runs": len(runs),
                "solved": solved,
                "solve_rate": round(solved / len(runs), 3),
                "hidden_gap_pp": round(sum(gaps) / len(gaps), 1) if gaps else None,
                "median_latency_s": round(median(latencies), 1) if latencies else None,
                "runs_with_cost": len(costed),
                "total_cost_eur": total_cost,
                "cost_per_solved_eur": cost_per_solved,
            }
        )
    rows.sort(key=lambda r: (-r["solve_rate"], r["solver"]))
    return {"runs_total": sum(r["runs"] for r in rows), "solvers": rows}


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

    lines = [
        "# Matrice cross-solver",
        "",
        f"Run aggregati: {data['runs_total']}. Il costo è solver-reported "
        "(vedi README): righe senza usage completa non hanno €/solved.",
        "",
        "| solver | run | solved | solve rate | hidden gap (pp) | latenza mediana | costo tot | €/task risolto |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in data["solvers"]:
        lines.append(
            f"| `{r['solver']}` | {r['runs']} | {r['solved']} | {r['solve_rate']:.0%} "
            f"| {cell(r['hidden_gap_pp'])} | {cell(r['median_latency_s'], 's')} "
            f"| {cell(r['total_cost_eur'], ' €')} | {cell(r['cost_per_solved_eur'], ' €')} |"
        )
    md = out / "matrix.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md
