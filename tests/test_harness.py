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
    load_usage,
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
    (broken / "task.json").write_text("{not json")
    with pytest.raises(FixtureError, match="JSON valido"):
        Fixture.load(broken)


def test_load_entry_files_not_a_list(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    meta = json.loads((broken / "task.json").read_text())
    meta["entry_files"] = "dedup.py"
    (broken / "task.json").write_text(json.dumps(meta))
    with pytest.raises(FixtureError, match="entry_files"):
        Fixture.load(broken)


def test_load_missing_entry_file(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "reference" / "dedup.py").unlink()
    with pytest.raises(FixtureError, match="entry file 'dedup.py' mancante in reference"):
        Fixture.load(broken)


def test_load_tests_dir_without_py_files(tmp_path):
    broken = tmp_path / "broken"
    shutil.copytree(FX_DEDUP, broken)
    for f in (broken / "tests_public").glob("*.py"):
        f.unlink()
    with pytest.raises(FixtureError, match="tests_public"):
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


def test_grading_dir_skips_stale_pycache_like_workspace_does(tmp_path):
    """Il grading copia il seed con la stessa regola d'igiene del workspace.

    Regressione reale: un __pycache__ residuo nel seed (comune dopo un run
    locale) veniva escluso dal workspace ma copiato pari pari nella grading
    dir, rompendo l'invarianza "stessa base pristina" fra le due copie.
    """
    broken = tmp_path / "fx-broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "seed" / "__pycache__").mkdir()
    (broken / "seed" / "__pycache__" / "stale.pyc").write_text("junk", encoding="utf-8")
    fx = Fixture.load(broken)
    ws = prepare_workspace(fx, tmp_path / "run")
    grade(fx, ws, tmp_path / "run")
    assert not (tmp_path / "run" / "grading" / "__pycache__").exists()


# ---------- Fixture contract (validate semantics) ----------

def test_seed_passes_public_fails_hidden(fixture, tmp_path):
    ws = prepare_workspace(fixture, tmp_path)  # noop solver: seed as-is
    result = grade(fixture, ws, tmp_path)
    assert result.public_passed == len(result.public) > 0
    assert result.hidden_passed < len(result.hidden)
    assert result.verdict == "PARTIAL"
    assert not result.solved


def test_grade_is_idempotent_across_reruns(tmp_path):
    """Rigradare nello stesso run_dir ricostruisce la grading dir da zero (no residui)."""
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    grade(fx, ws, tmp_path)
    (tmp_path / "grading" / "leftover.txt").write_text("residuo del run precedente\n")
    result = grade(fx, ws, tmp_path)
    assert not (tmp_path / "grading" / "leftover.txt").exists()
    assert result.public_passed == len(result.public) > 0


def test_verdict_unsolved_when_agent_breaks_everything(tmp_path):
    """Un agente che rompe anche i public (0 pass ovunque) è UNSOLVED, non PARTIAL."""
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    (ws / "dedup.py").write_text("def dedup_rows(rows, key):\n    raise RuntimeError('boom')\n")
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


def test_prepare_refuses_hidden_named_file_leaked_from_seed(tmp_path):
    """Se il seed stesso porta un file col nome da hidden test, l'invariante lo blocca in prep."""
    broken = tmp_path / "fx-broken"
    shutil.copytree(FX_DEDUP, broken)
    (broken / "seed" / "test_hidden_leftover.py").write_text("# leftover nel seed\n")
    fx = Fixture.load(broken)
    with pytest.raises(RuntimeError, match="test_hidden_leftover.py"):
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


def test_load_usage_rejects_non_object_json(tmp_path):
    """Un usage file che non è un oggetto JSON (es. una lista) è un errore soft, non un crash."""
    usage_file = tmp_path / "usage.json"
    usage_file.write_text("[1, 2, 3]", encoding="utf-8")
    usage = load_usage(usage_file)
    assert usage["error"]
    assert usage["source"] == "solver-reported"


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

def test_run_card_flags_unparsable_usage(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    apply_reference_solver(fx, ws)
    result = grade(fx, ws, tmp_path)
    bad_usage = {"error": "usage file non parsabile: boom", "source": "solver-reported"}
    write_results(tmp_path, fx, "builtin:ref", None, result, bad_usage)
    card = write_run_card(tmp_path).read_text()
    assert "⚠️ usage file non parsabile: boom" in card


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
