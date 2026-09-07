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


def test_load_bad_json(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FixtureError, match="JSON"):
        Fixture.load(broken)


def test_load_entry_files_empty(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    meta = json.loads((broken / "task.json").read_text())
    meta["entry_files"] = []
    (broken / "task.json").write_text(json.dumps(meta))
    with pytest.raises(FixtureError, match="entry_files"):
        Fixture.load(broken)


def test_load_missing_entry_file(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "reference" / "dedup.py").unlink()
    with pytest.raises(FixtureError, match="entry file"):
        Fixture.load(broken)


def test_load_test_dir_without_py_files(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    for f in (broken / "tests_hidden").glob("*.py"):
        f.unlink()
    with pytest.raises(FixtureError, match="tests_hidden"):
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


def test_grade_can_be_rerun_on_the_same_run_dir(tmp_path):
    """`aeh report`/una rivalutazione possono richiamare grade() sullo stesso run_dir."""
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    first = grade(fx, ws, tmp_path)
    second = grade(fx, ws, tmp_path)
    assert second.hidden_sha256 == first.hidden_sha256
    assert second.public_passed == first.public_passed


# ---------- Fixture contract (validate semantics) ----------

def test_seed_passes_public_fails_hidden(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)  # noop solver: seed as-is
    result = grade(fixture, ws, tmp_path)
    assert result.public_passed == len(result.public) > 0
    assert result.hidden_passed < len(result.hidden)
    assert result.verdict == "PARTIAL"
    assert not result.solved


def test_unsolved_verdict_when_entry_file_breaks_every_test(tmp_path):
    """Un entry file che non importa nemmeno (0 public, 0 hidden) è UNSOLVED, non PARTIAL."""
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    (ws / "dedup.py").write_text("def(:\n", encoding="utf-8")  # SyntaxError all'import
    result = grade(fx, ws, tmp_path)
    assert result.public_passed == 0
    assert result.hidden_passed == 0
    assert result.verdict == "UNSOLVED"
    assert not result.solved


def test_reference_solves(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)
    apply_reference_solver(fixture, ws)
    result = grade(fixture, ws, tmp_path)
    assert result.solved, [t for t in result.public + result.hidden if t["outcome"] != "pass"]
    assert result.verdict == "SOLVED"


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


def test_prepare_workspace_skips_pycache_in_seed(tmp_path):
    """Un __pycache__ residuo nel seed della fixture non deve finire nel workspace."""
    broken = tmp_path / "fx"
    shutil.copytree(FX_DEDUP, broken)
    cache = broken / "seed" / "__pycache__"
    cache.mkdir()
    (cache / "dedup.cpython-311.pyc").write_text("junk", encoding="utf-8")
    fx = Fixture.load(broken)
    ws = prepare_workspace(fx, tmp_path / "run")
    assert not (ws / "__pycache__").exists()


def test_prepare_workspace_rejects_hidden_named_file_leaking_from_seed(tmp_path):
    """Invariante di separazione: un file già nel seed con nome da hidden test blocca la prep."""
    broken = tmp_path / "fx"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "seed" / "test_hidden_sneaky.py").write_text("# non dovrebbe mai uscire dal seed\n")
    fx = Fixture.load(broken)
    with pytest.raises(RuntimeError, match="invariante violata"):
        prepare_workspace(fx, tmp_path / "run")


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


def test_solver_timeout_keeps_partial_output(tmp_path):
    """subprocess.run(text=True) consegna comunque bytes su TimeoutExpired: va decodificato.

    Regressione reale: senza il decode esplicito questo caso alza un AttributeError
    invece di un timeout onesto, perdendo l'output parziale del solver.
    """
    fx = Fixture.load(FX_SLUG)
    ws = prepare_workspace(fx, tmp_path)
    cmd = (
        "python3 -c \"import sys,time; sys.stdout.write('partial-out'); sys.stdout.flush(); "
        "sys.stderr.write('partial-err'); sys.stderr.flush(); time.sleep(5)\""
    )
    res = run_solver(ws, cmd, 1, tmp_path / "transcript.txt")
    assert res.status == "timeout"
    text = res.transcript_path.read_text()
    assert "partial-out" in text
    assert "partial-err" in text


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


def test_run_card_surfaces_unparsable_usage(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    apply_reference_solver(fx, ws)
    result = grade(fx, ws, tmp_path)
    usage = {"error": "usage file non parsabile: boom", "source": "solver-reported"}
    write_results(tmp_path, fx, "builtin:ref", None, result, usage)
    card = write_run_card(tmp_path).read_text()
    assert "usage file non parsabile" in card
