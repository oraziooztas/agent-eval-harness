"""Matrice cross-solver: aggregazione, cost-per-solved-task, CLI, usage."""

import json
from pathlib import Path

import pytest

from aeh.cli import main
from aeh.matrix import build_matrix, write_matrix
from aeh.runner import load_usage

FIXTURES = Path(__file__).parent.parent / "fixtures"
FX_SLUG = FIXTURES / "fx-002-slugify"


def _fake_run(
    run_dir: Path,
    label: str,
    solved: bool,
    cost: float | None = None,
    latency: float = 2.0,
    hidden_passed: int = 1,
) -> None:
    run_dir.mkdir(parents=True)
    usage = {"cost_eur": cost, "source": "solver-reported"} if cost is not None else None
    (run_dir / "results.json").write_text(
        json.dumps(
            {
                "fixture": {"id": "fx-fake", "title": "fake", "taxonomy": [], "root": "x"},
                "solver": {
                    "label": label,
                    "status": "ok",
                    "duration_seconds": latency,
                    "sandbox": "off",
                    "usage": usage,
                },
                "grade": {
                    "verdict": "SOLVED" if solved else "PARTIAL",
                    "solved": solved,
                    "public": {"passed": 2, "total": 2, "tests": []},
                    "hidden": {"passed": hidden_passed, "total": 2, "tests": []},
                },
            }
        ),
        encoding="utf-8",
    )


# ---------- Aggregazione ----------

def test_build_matrix_cost_per_solved(tmp_path):
    _fake_run(tmp_path / "r1", "agent-a", solved=True, cost=0.30, latency=10.0)
    _fake_run(tmp_path / "r2", "agent-a", solved=False, cost=0.10, latency=20.0)
    _fake_run(tmp_path / "r3", "agent-b", solved=False)
    data = build_matrix([tmp_path / "r1", tmp_path / "r2", tmp_path / "r3"])

    assert data["runs_total"] == 3
    a, b = data["solvers"][0], data["solvers"][1]
    assert a["solver"] == "agent-a"  # solve rate più alto → prima riga
    assert a["solved"] == 1 and a["runs"] == 2
    assert a["total_cost_eur"] == 0.4
    assert a["cost_per_solved_eur"] == 0.4  # tutto il costo speso / 1 risolto
    assert a["median_latency_s"] == 15.0
    assert b["cost_per_solved_eur"] is None  # nessun usage → niente €/solved


def test_build_matrix_partial_cost_coverage(tmp_path):
    """Se solo alcuni run hanno usage, €/solved non viene inventato."""
    _fake_run(tmp_path / "r1", "agent-c", solved=True, cost=0.2)
    _fake_run(tmp_path / "r2", "agent-c", solved=True)  # senza usage
    row = build_matrix([tmp_path / "r1", tmp_path / "r2"])["solvers"][0]
    assert row["runs_with_cost"] == 1
    assert row["total_cost_eur"] == 0.2
    assert row["cost_per_solved_eur"] is None


def test_build_matrix_hidden_gap(tmp_path):
    _fake_run(tmp_path / "r1", "agent-d", solved=False, hidden_passed=0)
    row = build_matrix([tmp_path / "r1"])["solvers"][0]
    assert row["hidden_gap_pp"] == 100.0  # public 2/2, hidden 0/2


def test_matrix_missing_results(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_matrix([tmp_path / "vuota"])


# ---------- Calibrazione: floor e ceiling (docs/METRICS.md) ----------

def test_calibration_tags_builtin_rows_and_measures_distance(tmp_path):
    """Il floor esce dai run della matrice, non da una costante."""
    _fake_run(tmp_path / "floor", "builtin:noop", solved=False, hidden_passed=0)
    _fake_run(tmp_path / "ceil", "builtin:ref", solved=True, hidden_passed=2)
    _fake_run(tmp_path / "a", "agent-a", solved=False, hidden_passed=1)
    data = build_matrix([tmp_path / "floor", tmp_path / "ceil", tmp_path / "a"])

    cal = data["calibration"]
    assert cal["floor"]["solver"] == "builtin:noop"
    assert cal["floor"]["hidden_gap_pp"] == 100.0  # public 2/2, hidden 0/2
    assert cal["ceiling"]["hidden_gap_pp"] == 0.0
    assert cal["warnings"] == []

    rows = {r["solver"]: r for r in data["solvers"]}
    assert rows["builtin:noop"]["role"] == "floor"
    assert rows["builtin:ref"]["role"] == "ceiling"
    assert rows["agent-a"]["role"] is None
    # hidden 1/2 → gap 50pp, cioè 50pp meglio del pavimento
    assert rows["agent-a"]["gap_vs_floor_pp"] == -50.0
    assert rows["builtin:noop"]["gap_vs_floor_pp"] == 0.0


def test_solver_at_the_floor_is_visible_as_such(tmp_path):
    """Un solver che non risolve nulla ha i public verdi ma gap_vs_floor ≈ 0."""
    _fake_run(tmp_path / "floor", "builtin:noop", solved=False, hidden_passed=0)
    _fake_run(tmp_path / "a", "agent-inutile", solved=False, hidden_passed=0)
    rows = {r["solver"]: r for r in build_matrix([tmp_path / "floor", tmp_path / "a"])["solvers"]}
    assert rows["agent-inutile"]["gap_vs_floor_pp"] == 0.0


def test_missing_floor_warns_instead_of_printing_a_bare_gap(tmp_path):
    _fake_run(tmp_path / "a", "agent-a", solved=False, hidden_passed=1)
    data = build_matrix([tmp_path / "a"])

    assert data["calibration"]["floor"] is None
    assert data["solvers"][0]["hidden_gap_pp"] == 50.0
    assert data["solvers"][0]["gap_vs_floor_pp"] is None  # nessuna scala → nessun numero
    assert any("builtin:noop" in w for w in data["calibration"]["warnings"])
    assert any("builtin:ref" in w for w in data["calibration"]["warnings"])


def test_matrix_md_reports_floor_and_never_leads_with_public(tmp_path):
    _fake_run(tmp_path / "floor", "builtin:noop", solved=False, hidden_passed=0)
    _fake_run(tmp_path / "a", "agent-a", solved=True, hidden_passed=2)
    text = write_matrix([tmp_path / "floor", tmp_path / "a"], tmp_path / "out").read_text()

    assert "Floor misurato" in text and "floor" in text
    header = next(ln for ln in text.splitlines() if ln.startswith("| solver |"))
    assert "vs floor" in header
    assert "public" not in header.lower()  # regressione: il public non torna in tabella


def test_matrix_md_carries_the_warning_when_uncalibrated(tmp_path):
    _fake_run(tmp_path / "a", "agent-a", solved=True)
    text = write_matrix([tmp_path / "a"], tmp_path / "out").read_text()
    assert "⚠️" in text and "--noop" in text


def test_write_matrix_files(tmp_path):
    _fake_run(tmp_path / "r1", "agent-a", solved=True, cost=0.5)
    md = write_matrix([tmp_path / "r1"], tmp_path / "out")
    assert md.is_file()
    assert (tmp_path / "out" / "matrix.json").is_file()
    text = md.read_text()
    assert "agent-a" in text and "€/task risolto" in text


def test_cli_matrix(tmp_path, capsys):
    _fake_run(tmp_path / "r1", "agent-a", solved=True)
    _fake_run(tmp_path / "r2", "agent-b", solved=False)
    code = main(
        ["matrix", str(tmp_path / "r1"), str(tmp_path / "r2"), "--out", str(tmp_path / "m")]
    )
    assert code == 0
    assert (tmp_path / "m" / "matrix.md").is_file()
    assert "matrix" in capsys.readouterr().out


# ---------- Usage ingestion ----------

def test_load_usage_missing(tmp_path):
    assert load_usage(tmp_path / "nope.json") is None


def test_load_usage_cost_from_prices(tmp_path):
    f = tmp_path / "u.json"
    f.write_text('{"tokens_in": 2000000, "tokens_out": 1000000}', encoding="utf-8")
    usage = load_usage(f, price_in_eur_mtok=3.0, price_out_eur_mtok=15.0)
    assert usage["cost_eur"] == 21.0
    assert usage["source"] == "solver-reported"


def test_load_usage_explicit_cost_wins(tmp_path):
    f = tmp_path / "u.json"
    f.write_text('{"tokens_in": 10, "tokens_out": 10, "cost_eur": 0.1234}', encoding="utf-8")
    usage = load_usage(f, 1.0, 1.0)
    assert usage["cost_eur"] == 0.1234


def test_load_usage_broken_json(tmp_path):
    f = tmp_path / "u.json"
    f.write_text("{non-json", encoding="utf-8")
    usage = load_usage(f)
    assert "error" in usage


def test_cli_run_ingests_usage_with_prices(tmp_path):
    """E2E: il solver scrive AEH_USAGE_FILE, i prezzi CLI producono il costo."""
    out = tmp_path / "run"
    ref = FX_SLUG / "reference" / "slugify.py"
    solver = (
        f"cp '{ref}' slugify.py && "
        "printf '{\"tokens_in\": 1000000, \"tokens_out\": 500000}' > \"$AEH_USAGE_FILE\""
    )
    code = main(
        [
            "run", str(FX_SLUG), "--solver", solver, "--out", str(out),
            "--price-in", "2.0", "--price-out", "10.0",
        ]
    )
    assert code == 0
    data = json.loads((out / "results.json").read_text())
    assert data["solver"]["usage"]["cost_eur"] == 7.0  # 1M*2 + 0.5M*10 per Mtok
    card = (out / "run_card.md").read_text()
    assert "solver-reported" in card and "7.0 €" in card
