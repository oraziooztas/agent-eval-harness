"""Test dell'importer AFB: mappatura, entry detection, stub, holdout, CLI (ADR-001)."""

import json
from pathlib import Path

import pytest

from aeh.cli import main
from aeh.fixture import Fixture
from aeh.importer import AfbImportError, _prefixed_name, import_tasks

TASK_ID = "afb-v0-042"


def _make_afb(root: Path, *, with_holdout: bool = True, holdout_at: Path | None = None) -> Path:
    """Repo AFB finto ma fedele: 1 task eseguibile + 1 solo-spec.

    Il task eseguibile ha: un file di contesto identico (non entry), un sorgente
    buggato (entry per diff), un artefatto solo-in-reference (entry con stub),
    un file non-.py dentro tests/ (asset di workspace).
    """
    visible = root / "fixtures/v0" / TASK_ID / "agent_visible"
    (visible / "src").mkdir(parents=True)
    (visible / "src/__init__.py").write_text("", encoding="utf-8")
    (visible / "src/mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (visible / "context.txt").write_text("contesto identico\n", encoding="utf-8")
    (visible / "TASK.md").write_text("# Task 42\n\nFix `f`, poi crea `out.json`.\n", encoding="utf-8")
    tests = visible / "tests"
    tests.mkdir()
    (tests / "__init__.py").write_text("", encoding="utf-8")
    (tests / "test_mod.py").write_text(
        "import unittest\n\nfrom src.mod import f\n\n\n"
        "class PublicTests(unittest.TestCase):\n"
        "    def test_f_returns_int(self):\n"
        "        self.assertIsInstance(f(), int)\n",
        encoding="utf-8",
    )
    (tests / "failing_output.txt").write_text("captured failure\n", encoding="utf-8")

    if with_holdout:
        base = (holdout_at / TASK_ID) if holdout_at else root / "fixtures/v0" / TASK_ID
        hidden = base / "hidden_tests"
        hidden.mkdir(parents=True)
        (hidden / "__pycache__").mkdir()
        (hidden / "__pycache__/junk.pyc").write_text("x", encoding="utf-8")
        (hidden / "test_hidden_mod.py").write_text(
            "import json\nimport unittest\nfrom pathlib import Path\n\nfrom src.mod import f\n\n\n"
            "class HiddenTests(unittest.TestCase):\n"
            "    def test_f_fixed(self):\n"
            "        self.assertEqual(f(), 2)\n\n"
            "    def test_out_written(self):\n"
            "        data = json.loads(Path('out.json').read_text(encoding='utf-8'))\n"
            "        self.assertTrue(data['done'])\n",
            encoding="utf-8",
        )
        reference = base / "reference_solution"
        (reference / "src").mkdir(parents=True)
        (reference / "src/__init__.py").write_text("", encoding="utf-8")
        (reference / "src/mod.py").write_text("def f():\n    return 2\n", encoding="utf-8")
        (reference / "out.json").write_text(
            '{"done": true, "note": "fatto", "steps": ["fix"]}\n', encoding="utf-8"
        )

    tasks = [
        {
            "id": TASK_ID,
            "suite_version": "v0",
            "title": "Fake Runnable Task",
            "estimated_minutes": 10,
            "agent_prompt": "Fix it (fallback prompt).",
            "primary_failure_modes": ["F03", "F07"],
            "seed_files": [
                {"path": "src/mod.py", "purpose": "bug"},
                {"path": "tests/test_mod.py", "purpose": "test visibili"},
            ],
            "hidden_checks": ["f ritorna 2", "out.json scritto e valido"],
            "runnable_fixture": {
                "path": f"fixtures/v0/{TASK_ID}",
                "public_tests": "agent_visible/tests",
                "hidden_tests": "hidden_tests",
                "reference_solution": "reference_solution",
            },
        },
        {
            "id": "afb-v0-041",
            "suite_version": "v0",
            "title": "Spec Only Task",
            "agent_prompt": "niente fixture",
        },
    ]
    tasks_dir = root / "tasks/v0"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "tasks.json").write_text(json.dumps(tasks), encoding="utf-8")
    return root


def test_import_complete_layout_and_metadata(tmp_path):
    afb = _make_afb(tmp_path / "afb")
    out = tmp_path / "fixtures"
    outcomes = import_tasks(afb, out)

    assert [o.task_id for o in outcomes] == [TASK_ID]  # il task solo-spec è escluso
    outcome = outcomes[0]
    assert outcome.status == "complete"
    assert outcome.hidden_origin == "afb-repo"
    dest = out / TASK_ID

    # seed: visibile meno tests/ e TASK.md, più lo stub dell'artefatto
    assert (dest / "seed/src/mod.py").is_file()
    assert (dest / "seed/context.txt").is_file()
    assert not (dest / "seed/TASK.md").exists()
    assert not (dest / "seed/tests").exists()
    stub = json.loads((dest / "seed/out.json").read_text(encoding="utf-8"))
    assert stub == {"done": False, "note": "", "steps": []}

    # test rinominati coi prefissi aeh; asset non-.py preservato; __init__/__pycache__ esclusi
    assert (dest / "tests_public/test_public_mod.py").is_file()
    assert (dest / "tests_public/failing_output.txt").is_file()
    assert not (dest / "tests_public/__init__.py").exists()
    assert (dest / "tests_hidden/test_hidden_mod.py").is_file()
    assert not (dest / "tests_hidden/__pycache__").exists()

    meta = json.loads((dest / "task.json").read_text(encoding="utf-8"))
    assert meta["id"] == TASK_ID
    assert meta["entry_files"] == ["out.json", "src/mod.py"]
    assert meta["timeout_seconds"] == 600
    assert meta["taxonomy"] == ["F03", "F07"]
    assert "Task 42" in meta["prompt"]  # prompt dal TASK.md, non dal fallback
    prov = meta["provenance"]
    assert prov["hidden_tests_origin"] == "afb-repo"
    assert prov["seed_stubs"] == ["out.json"]
    assert prov["disclosed_example"] is True

    # la fixture importata è caricabile subito dal modello aeh
    fixture = Fixture.load(dest)
    assert fixture.entry_files == ("out.json", "src/mod.py")


def test_imported_fixture_passes_full_validate(tmp_path, capsys):
    afb = _make_afb(tmp_path / "afb")
    out = tmp_path / "fixtures"
    import_tasks(afb, out)
    code = main(["validate", str(out / TASK_ID)])
    assert code == 0
    assert "VALID" in capsys.readouterr().out


def test_import_with_external_holdout_dir(tmp_path):
    holdout = tmp_path / "holdout"
    afb = _make_afb(tmp_path / "afb", holdout_at=holdout)
    out = tmp_path / "fixtures"
    outcomes = import_tasks(afb, out, holdout_dir=holdout)
    assert outcomes[0].status == "complete"
    assert outcomes[0].hidden_origin == "holdout-dir"
    assert main(["validate", str(out / TASK_ID)]) == 0


def test_import_partial_without_holdout(tmp_path):
    afb = _make_afb(tmp_path / "afb", with_holdout=False)
    out = tmp_path / "fixtures"
    outcomes = import_tasks(afb, out)
    outcome = outcomes[0]
    assert outcome.status == "partial"
    assert outcome.hidden_origin == "missing"
    dest = out / TASK_ID
    assert not (dest / "tests_hidden").exists()
    missing_md = (dest / "MISSING.md").read_text(encoding="utf-8")
    assert "out.json scritto e valido" in missing_md  # gli hidden_checks pubblicati guidano l'autore
    # entry best-effort dagli spec: i path sotto tests/ sono esclusi
    meta = json.loads((dest / "task.json").read_text(encoding="utf-8"))
    assert meta["entry_files"] == ["src/mod.py"]


def test_cli_import_afb_exit_codes(tmp_path, capsys):
    afb = _make_afb(tmp_path / "afb")
    out = tmp_path / "fixtures"
    assert main(["import-afb", str(afb), "--out", str(out)]) == 0
    assert "[complete, holdout: afb-repo]" in capsys.readouterr().out

    # senza --force la destinazione esistente è un errore (exit 1)
    assert main(["import-afb", str(afb), "--out", str(out)]) == 1
    assert main(["import-afb", str(afb), "--out", str(out), "--force"]) == 0

    partial_afb = _make_afb(tmp_path / "afb2", with_holdout=False)
    assert main(["import-afb", str(partial_afb), "--out", str(tmp_path / "fx2")]) == 2


def test_task_id_filter_and_unknown_id(tmp_path):
    afb = _make_afb(tmp_path / "afb")
    out = tmp_path / "fixtures"
    outcomes = import_tasks(afb, out, task_ids=[TASK_ID])
    assert len(outcomes) == 1
    with pytest.raises(AfbImportError, match="inesistenti"):
        import_tasks(afb, tmp_path / "fx2", task_ids=["afb-v0-041"])  # solo-spec: non eseguibile


def test_force_overwrites_previous_import(tmp_path):
    afb = _make_afb(tmp_path / "afb")
    out = tmp_path / "fixtures"
    import_tasks(afb, out)
    leftover = out / TASK_ID / "leftover.txt"
    leftover.write_text("vecchio", encoding="utf-8")
    with pytest.raises(AfbImportError, match="force"):
        import_tasks(afb, out)
    import_tasks(afb, out, force=True)
    assert not leftover.exists()


def test_prefixed_name_rules():
    assert _prefixed_name("test_mod.py", "test_public") == "test_public_mod.py"
    assert _prefixed_name("test_hidden_mod.py", "test_hidden") == "test_hidden_mod.py"
    assert _prefixed_name("checks.py", "test_hidden") == "test_hidden_checks.py"


def test_missing_afb_root_is_clean_error(tmp_path):
    with pytest.raises(AfbImportError, match="tasks"):
        import_tasks(tmp_path / "nowhere", tmp_path / "out")
