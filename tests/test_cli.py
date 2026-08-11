"""Test della CLI: exit codes e artefatti su disco."""

import json
import shutil
from pathlib import Path

from aeh import sandbox
from aeh.cli import main

FIXTURES = Path(__file__).parent.parent / "fixtures"
FX_DEDUP = FIXTURES / "fx-001-csv-dedup"
FX_SLUG = FIXTURES / "fx-002-slugify"


def test_run_ref_exit_0_and_artifacts(tmp_path, capsys):
    out = tmp_path / "run"
    code = main(["run", str(FX_DEDUP), "--ref", "--out", str(out)])
    assert code == 0
    assert (out / "results.json").is_file()
    assert (out / "run_card.md").is_file()
    assert "SOLVED" in capsys.readouterr().out


def test_run_noop_exit_2(tmp_path, capsys):
    out = tmp_path / "run"
    code = main(["run", str(FX_SLUG), "--noop", "--out", str(out)])
    assert code == 2
    data = json.loads((out / "results.json").read_text())
    assert data["grade"]["verdict"] == "PARTIAL"
    assert data["solver"]["label"] == "builtin:noop"


def test_summary_leads_with_hidden_and_labels_public(tmp_path, capsys):
    """Il public non è un segnale di soluzione: non può stare in testa (docs/METRICS.md).

    Regressione reale: un `--noop` passa tutti i public e nel vecchio summary
    apriva con quel numero verde su una run che non ha risolto niente.
    """
    code = main(["run", str(FX_SLUG), "--noop", "--out", str(tmp_path / "run")])
    assert code == 2
    first_line = capsys.readouterr().out.splitlines()[0]
    assert "hidden" in first_line
    assert "public" not in first_line


def test_run_card_leads_with_hidden_and_frames_public(tmp_path):
    out = tmp_path / "run"
    main(["run", str(FX_SLUG), "--noop", "--out", str(out)])
    card = (out / "run_card.md").read_text()
    headline = next(ln for ln in card.splitlines() if ln.startswith("**Verdetto"))
    assert headline.index("hidden") < headline.index("public")
    assert "regression guard" in card


def test_run_shell_solver(tmp_path):
    out = tmp_path / "run"
    ref = FX_SLUG / "reference" / "slugify.py"
    code = main(["run", str(FX_SLUG), "--solver", f"cp '{ref}' slugify.py", "--out", str(out)])
    assert code == 0
    assert (out / "transcript.txt").is_file()


def test_run_custom_label(tmp_path):
    out = tmp_path / "run"
    code = main(["run", str(FX_DEDUP), "--ref", "--label", "agent-x", "--out", str(out)])
    assert code == 0
    data = json.loads((out / "results.json").read_text())
    assert data["solver"]["label"] == "agent-x"


def test_validate_good_fixtures(capsys):
    code = main(["validate", str(FX_DEDUP), str(FX_SLUG)])
    assert code == 0
    out = capsys.readouterr().out
    assert out.count("VALID") == 2
    assert "INVALID" not in out


def test_validate_broken_contract(tmp_path, capsys):
    """Fixture col seed che fallisce anche i public → contratto violato → exit 1."""
    broken = tmp_path / "fx-broken"
    shutil.copytree(FX_SLUG, broken)
    (broken / "seed" / "slugify.py").write_text("def slugify(text):\n    return None\n")
    code = main(["validate", str(broken)])
    assert code == 1
    assert "INVALID" in capsys.readouterr().out


def test_report_regenerates_card(tmp_path):
    out = tmp_path / "run"
    main(["run", str(FX_DEDUP), "--ref", "--out", str(out)])
    (out / "run_card.md").unlink()
    code = main(["report", str(out)])
    assert code == 0
    assert (out / "run_card.md").is_file()


def test_error_on_missing_fixture(capsys):
    code = main(["run", "/nonexistent/fixture", "--noop"])
    assert code == 1
    assert "errore" in capsys.readouterr().err


def test_sandbox_solver_without_backend_is_clean_error(tmp_path, capsys, monkeypatch):
    """--sandbox-solver su un host senza backend è un errore di harness (exit 1), non un crash."""
    monkeypatch.setattr(sandbox, "backend", lambda: None)
    code = main(
        ["run", str(FX_SLUG), "--noop", "--sandbox-solver", "--out", str(tmp_path / "run")]
    )
    assert code == 1
    assert "sandbox" in capsys.readouterr().err
