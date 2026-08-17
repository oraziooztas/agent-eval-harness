"""Suite del harness. Le proprietà critiche sotto test:

1. SEPARATION: il workspace dell'agente non contiene mai gli hidden test.
2. TAMPER-PROOF: modifiche dell'agente ai file di test non toccano il grading.
3. CONTRATTO FIXTURE: seed passa i public e fallisce ≥1 hidden; reference passa tutto.
"""

import json
import shutil
from pathlib import Path

import pytest

from aeh.fixture import Fixture, FixtureError
from aeh.grader import grade
from aeh.report import write_results, write_run_card
from aeh.runner import (
    apply_reference_solver,
    find_hidden_leaks,
    prepare_workspace,
    run_solver,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
FX_DEDUP = FIXTURES / "fx-001-csv-dedup"
FX_SLUG = FIXTURES / "fx-002-slugify"
FX_BACKOFF = FIXTURES / "fx-003-retry-backoff"
FX_TOC = FIXTURES / "fx-004-markdown-toc"


@pytest.fixture(
    params=[FX_DEDUP, FX_SLUG, FX_BACKOFF, FX_TOC],
    ids=["dedup", "slugify", "backoff", "toc"],
)
def fixture(request) -> Fixture:
    return Fixture.load(request.param)


# ---------- Fixture loading ----------

def test_load_ok():
    fx = Fixture.load(FX_DEDUP)
    assert fx.id == "fx-001-csv-dedup"
    assert fx.entry_files == ("dedup.py",)
    assert len(fx.hidden_sha256()) == 64


def test_load_missing_dir(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    shutil.rmtree(broken / "tests_hidden")
    with pytest.raises(FixtureError, match="tests_hidden"):
        Fixture.load(broken)


def test_load_bad_test_naming(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "tests_hidden" / "test_hidden.py").rename(broken / "tests_hidden" / "test_x.py")
    with pytest.raises(FixtureError, match="test_hidden"):
        Fixture.load(broken)


def test_load_missing_meta_field(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    meta = json.loads((broken / "task.json").read_text())
    del meta["prompt"]
    (broken / "task.json").write_text(json.dumps(meta))
    with pytest.raises(FixtureError, match="prompt"):
        Fixture.load(broken)


def test_load_invalid_json(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "task.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(FixtureError, match="JSON valido"):
        Fixture.load(broken)


def test_load_empty_entry_files(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    meta = json.loads((broken / "task.json").read_text())
    meta["entry_files"] = []
    (broken / "task.json").write_text(json.dumps(meta))
    with pytest.raises(FixtureError, match="lista non vuota"):
        Fixture.load(broken)


def test_load_entry_file_missing_in_seed(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "seed" / "dedup.py").unlink()
    with pytest.raises(FixtureError, match="mancante in seed/"):
        Fixture.load(broken)


def test_load_tests_dir_with_no_py_files(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    for f in (broken / "tests_public").glob("*.py"):
        f.unlink()
    with pytest.raises(FixtureError, match="tests_public/ non contiene file .py"):
        Fixture.load(broken)


# ---------- Separation ----------

def test_workspace_has_no_hidden_tests(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)
    assert find_hidden_leaks(ws) == []
    names = {p.name for p in ws.rglob("*") if p.is_file()}
    assert "PROMPT.md" in names
    assert any(n.startswith("test_public") for n in names)
    assert not any(n.startswith("test_hidden") for n in names)


def test_grading_dir_has_pristine_hidden_tests(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)
    grade(fixture, ws, tmp_path)
    grading_tests = {p.name for p in (tmp_path / "grading" / "tests").glob("*.py")}
    assert any(n.startswith("test_hidden") for n in grading_tests)
    assert any(n.startswith("test_public") for n in grading_tests)


def test_grade_records_hidden_hash(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)
    result = grade(fixture, ws, tmp_path)
    assert result.hidden_sha256 == fixture.hidden_sha256()


def test_prepare_workspace_refuses_hidden_named_file_in_seed(tmp_path):
    """La struttura invariante non si fida nemmeno del seed: se un file col nome
    da hidden test finisse nel seed (bug d'autore fixture), il prep deve fallire
    prima di consegnare un workspace all'agente, non scoprirlo dopo al grading."""
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "seed" / "test_hidden_leak.py").write_text("# non dovrebbe uscire dal seed\n")
    fx = Fixture.load(broken)
    with pytest.raises(RuntimeError, match="invariante violata"):
        prepare_workspace(fx, tmp_path / "run")


def test_prepare_workspace_skips_pycache(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    pycache = broken / "seed" / "__pycache__"
    pycache.mkdir()
    (pycache / "dedup.cpython-311.pyc").write_bytes(b"junk")
    fx = Fixture.load(broken)
    ws = prepare_workspace(fx, tmp_path / "run")
    assert not (ws / "__pycache__").exists()


# ---------- Fixture contract (validate semantics) ----------

def test_seed_passes_public_fails_hidden(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)  # noop solver: seed as-is
    result = grade(fixture, ws, tmp_path)
    assert result.public_passed == len(result.public) > 0
    assert result.hidden_passed < len(result.hidden)
    assert result.verdict == "PARTIAL"
    assert not result.solved


def test_reference_solves(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)
    apply_reference_solver(fixture, ws)
    result = grade(fixture, ws, tmp_path)
    assert result.solved, [t for t in result.public + result.hidden if t["outcome"] != "pass"]
    assert result.verdict == "SOLVED"


def test_verdict_unsolved_when_everything_fails(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    (ws / "dedup.py").write_text(
        "def dedup_rows(rows, key):\n    raise RuntimeError('broken on purpose')\n"
    )
    result = grade(fx, ws, tmp_path)
    assert result.public_passed == 0
    assert result.hidden_passed == 0
    assert result.verdict == "UNSOLVED"
    assert not result.solved


def test_grade_can_run_twice_into_the_same_run_dir(tmp_path):
    """Il grading rigenera grading/ da zero: rigradare uno stesso run_dir non deve
    fallire né lasciare residui della run precedente."""
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    apply_reference_solver(fx, ws)
    first = grade(fx, ws, tmp_path)
    (tmp_path / "grading" / "stale_marker.txt").write_text("dovrebbe sparire")
    second = grade(fx, ws, tmp_path)
    assert first.solved and second.solved
    assert not (tmp_path / "grading" / "stale_marker.txt").exists()


# ---------- Tamper resistance ----------

def test_agent_test_edits_do_not_reach_grading(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    # L'agente "bara": svuota i test pubblici e rompe la soluzione.
    (ws / "tests" / "test_public.py").write_text(
        "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
    )
    (ws / "dedup.py").write_text("def dedup_rows(rows, key):\n    return []\n")
    result = grade(fx, ws, tmp_path)
    # Il grading usa i test intatti: la soluzione rotta DEVE fallire i public originali.
    assert result.public_passed < len(result.public)
    assert not result.solved


def test_hidden_named_file_in_workspace_flagged(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    (ws / "test_hidden_guess.py").write_text("# tentativo di indovinare gli hidden\n")
    result = grade(fx, ws, tmp_path)
    assert result.tamper_suspect == ["test_hidden_guess.py"]


def test_prepare_refuses_existing_workspace(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    prepare_workspace(fx, tmp_path)
    with pytest.raises(FileExistsError):
        prepare_workspace(fx, tmp_path)


# ---------- Solver execution ----------

def test_solver_transcript_and_status(tmp_path):
    fx = Fixture.load(FX_SLUG)
    ws = prepare_workspace(fx, tmp_path)
    res = run_solver(ws, "echo ciao-dal-solver && ls PROMPT.md", 30, tmp_path / "transcript.txt")
    assert res.status == "ok"
    text = res.transcript_path.read_text()
    assert "ciao-dal-solver" in text
    assert "PROMPT.md" in text


def test_solver_nonzero_exit_is_error(tmp_path):
    fx = Fixture.load(FX_SLUG)
    ws = prepare_workspace(fx, tmp_path)
    res = run_solver(ws, "exit 3", 30, tmp_path / "transcript.txt")
    assert res.status == "error"
    assert res.returncode == 3


def test_solver_timeout(tmp_path):
    fx = Fixture.load(FX_SLUG)
    ws = prepare_workspace(fx, tmp_path)
    res = run_solver(ws, "sleep 5", 1, tmp_path / "transcript.txt")
    assert res.status == "timeout"
    assert res.returncode is None


def test_shell_solver_can_solve(tmp_path):
    """Un solver reale (shell) che scrive la soluzione corretta viene valutato SOLVED."""
    fx = Fixture.load(FX_SLUG)
    ws = prepare_workspace(fx, tmp_path)
    solution = (FX_SLUG / "reference" / "slugify.py").read_text()
    (tmp_path / "sol.py").write_text(solution)
    res = run_solver(ws, f"cp {tmp_path}/sol.py slugify.py", 30, tmp_path / "transcript.txt")
    assert res.status == "ok"
    result = grade(fx, ws, tmp_path)
    assert result.solved


# ---------- Report ----------

def test_results_and_run_card(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    apply_reference_solver(fx, ws)
    result = grade(fx, ws, tmp_path)
    res_path = write_results(tmp_path, fx, "builtin:ref", None, result)
    data = json.loads(res_path.read_text())
    assert data["grade"]["verdict"] == "SOLVED"
    assert data["grade"]["hidden"]["total"] == 5
    card = write_run_card(tmp_path)
    text = card.read_text()
    assert "SOLVED" in text
    assert "mai visti dall'agente" in text
    assert fx.hidden_sha256()[:16] in text


def test_run_card_flags_unparsable_usage(tmp_path):
    """Un usage file non parsabile arriva a to_dict come {"error": ...}: la run
    card deve renderlo visibile invece di stamparlo come se fosse un costo."""
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    apply_reference_solver(fx, ws)
    result = grade(fx, ws, tmp_path)
    usage = {"error": "usage file non parsabile: boom", "source": "solver-reported"}
    write_results(tmp_path, fx, "agent-x", None, result, usage)
    card = write_run_card(tmp_path)
    text = card.read_text()
    assert "⚠️" in text
    assert "usage file non parsabile" in text
