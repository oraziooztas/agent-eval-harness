"""Test della CLI: exit codes e artefatti su disco."""

import json
import os
import shutil
from pathlib import Path

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


# --- credenziale API: esplicita, mai l'abbonamento -------------------------


def test_require_api_key_missing_fails_loudly(tmp_path, capsys, monkeypatch):
    """Chiave assente → exit 1 con messaggio azionabile, PRIMA di creare il workspace."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = tmp_path / "run"
    code = main(["run", str(FX_DEDUP), "--solver", "true", "--out", str(out), "--require-api-key"])
    assert code == 1
    err = capsys.readouterr().err
    assert "credenziale assente" in err
    assert "ANTHROPIC_API_KEY" in err
    assert "abbonamento" in err  # la distinzione col piano Claude Code è nel messaggio
    assert not (out / "workspace").exists()  # fallito a costo zero


def test_require_api_key_rejects_empty_value(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    code = main(
        ["run", str(FX_DEDUP), "--solver", "true", "--out", str(tmp_path / "r"), "--require-api-key"]
    )
    assert code == 1
    assert "credenziale assente" in capsys.readouterr().err


def test_api_key_injected_into_solver_only(tmp_path, monkeypatch):
    """La chiave arriva al sottoprocesso; nei report resta solo il fingerprint."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AEH_ANTHROPIC_API_KEY", "sk-ant-test-secret")
    out = tmp_path / "run"
    leak = tmp_path / "seen.txt"
    code = main(
        [
            "run", str(FX_DEDUP),
            "--solver", f'printf "%s" "$ANTHROPIC_API_KEY" > {leak}',
            "--out", str(out),
            "--require-api-key", "AEH_ANTHROPIC_API_KEY",
        ]
    )
    assert code == 2  # il solver non risolve la fixture: qui conta solo l'env
    assert leak.read_text() == "sk-ant-test-secret"  # iniettata come ANTHROPIC_API_KEY

    data = json.loads((out / "results.json").read_text())
    cred = data["solver"]["credential"]
    assert cred["env_var"] == "AEH_ANTHROPIC_API_KEY"
    assert cred["injected_as"] == "ANTHROPIC_API_KEY"
    assert cred["fingerprint"].startswith("sha256:")
    assert "sk-ant-test-secret" not in (out / "results.json").read_text()
    assert "sk-ant-test-secret" not in (out / "run_card.md").read_text()
    assert "ANTHROPIC_API_KEY" not in os.environ  # la shell chiamante non è stata toccata


def test_no_credential_recorded_for_builtin_runs(tmp_path):
    out = tmp_path / "run"
    main(["run", str(FX_DEDUP), "--ref", "--out", str(out)])
    assert json.loads((out / "results.json").read_text())["solver"]["credential"] is None


def test_agent_cli_solver_without_key_warns(tmp_path, capsys):
    """Guardia anti-abbonamento: un solver che sembra un agent CLI senza chiave avvisa."""
    main(["run", str(FX_DEDUP), "--solver", "claude -p x || true", "--out", str(tmp_path / "r")])
    err = capsys.readouterr().err
    assert "--require-api-key" in err and "quota di sessione" in err


def test_plain_solver_does_not_warn(tmp_path, capsys):
    main(["run", str(FX_DEDUP), "--solver", "true", "--out", str(tmp_path / "r")])
    assert "quota di sessione" not in capsys.readouterr().err
