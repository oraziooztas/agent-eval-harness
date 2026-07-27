"""Ponte ADR-001: importa i task eseguibili di AFB come fixture aeh.

AFB (agent-failure-eval-bench) è il bench pubblico: spec in ``tasks/<suite>/tasks.json``,
fixture con ``agent_visible/`` (seed + test pubblici + TASK.md). I materiali privati
(``hidden_tests/``, ``reference_solution/``) NON stanno nel bundle pubblico
(disclosure policy del bench): vivono nel repo di lavoro del maintainer oppure
vengono passati con ``--holdout-dir``. Le fixture importate li contengono, quindi
NON vanno committate in un repo pubblico.

Mappatura per ogni task con ``runnable_fixture``:

    agent_visible/ (meno tests/ e TASK.md)  →  seed/
    agent_visible/tests/*.py                →  tests_public/test_public_*.py
    agent_visible/tests/* (non .py)         →  tests_public/ as-is (fedeltà workspace)
    holdout hidden_tests/*.py               →  tests_hidden/test_hidden_*.py
    holdout reference_solution/             →  reference/
    TASK.md                                 →  prompt in task.json

``entry_files`` = file della reference che differiscono dal materiale visibile, più
i file solo-in-reference (artefatti che l'agente deve produrre, es. un attempt log):
per questi il seed riceve uno stub, perché la validazione aeh richiede ogni entry
file presente sia in seed/ sia in reference/. Gli stub sono registrati in provenance.

I check di processo/rubrica di AFB (trace, comunicazione) non diventano test aeh:
qui passa solo la parte meccanicamente eseguibile. Senza holdout l'import è PARTIAL.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aeh.fixture import HIDDEN_PREFIX, PUBLIC_PREFIX, Fixture

JUNK_DIRS = frozenset({"__pycache__", ".git"})
JUNK_FILES = frozenset({".DS_Store"})


class AfbImportError(Exception):
    """Raised when the AFB source material cannot be imported."""


@dataclass(frozen=True)
class ImportOutcome:
    task_id: str
    fixture_dir: Path
    status: str  # "complete" | "partial"
    entry_files: tuple[str, ...] = ()
    seed_stubs: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    hidden_origin: str = "missing"  # "afb-repo" | "holdout-dir" | "missing"


def load_runnable_tasks(afb_root: str | Path) -> list[dict]:
    """Legge tasks/<suite>/tasks.json e ritorna i soli task con runnable_fixture."""
    rootp = Path(afb_root).resolve()
    task_files = sorted(rootp.glob("tasks/*/tasks.json"))
    if not task_files:
        raise AfbImportError(f"nessun tasks/<suite>/tasks.json trovato in {rootp}")
    runnable: list[dict] = []
    for tf in task_files:
        try:
            data = json.loads(tf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AfbImportError(f"{tf} non è JSON valido: {exc}") from exc
        if not isinstance(data, list):
            raise AfbImportError(f"{tf}: atteso un array di task")
        runnable.extend(t for t in data if isinstance(t, dict) and t.get("runnable_fixture"))
    return runnable


def import_tasks(
    afb_root: str | Path,
    out_dir: str | Path,
    *,
    task_ids: list[str] | None = None,
    holdout_dir: str | Path | None = None,
    force: bool = False,
) -> list[ImportOutcome]:
    """Importa tutti i task eseguibili (o il sottoinsieme richiesto) in out_dir."""
    tasks = load_runnable_tasks(afb_root)
    if task_ids:
        wanted = set(task_ids)
        tasks = [t for t in tasks if str(t.get("id")) in wanted]
        unknown = wanted - {str(t.get("id")) for t in tasks}
        if unknown:
            raise AfbImportError(f"task id inesistenti o senza runnable_fixture: {sorted(unknown)}")
    if not tasks:
        raise AfbImportError("nessun task eseguibile (runnable_fixture) da importare")
    return [
        import_task(afb_root, t, out_dir, holdout_dir=holdout_dir, force=force) for t in tasks
    ]


def import_task(
    afb_root: str | Path,
    task: dict,
    out_dir: str | Path,
    *,
    holdout_dir: str | Path | None = None,
    force: bool = False,
) -> ImportOutcome:
    """Converte un singolo task AFB in una fixture aeh sotto out_dir/<task-id>/."""
    rootp = Path(afb_root).resolve()
    rf = task["runnable_fixture"]
    task_id = str(task["id"])
    fixture_src = rootp / str(rf["path"])
    public_tests_src = fixture_src / str(rf.get("public_tests", "agent_visible/tests"))
    if not public_tests_src.is_dir():
        raise AfbImportError(f"{task_id}: test pubblici non trovati: {public_tests_src}")
    visible_root = public_tests_src.parent
    tests_dirname = public_tests_src.name

    dest = Path(out_dir).resolve() / task_id
    if dest.exists():
        if not force:
            raise AfbImportError(f"{task_id}: destinazione già esistente (usa --force): {dest}")
        shutil.rmtree(dest)

    hidden_src, reference_src, hidden_origin = _resolve_holdout(fixture_src, task, holdout_dir)

    seed_dir = dest / "seed"
    _copy_tree(visible_root, seed_dir, exclude_top=frozenset({tests_dirname, "TASK.md"}))
    _copy_tests(public_tests_src, dest / "tests_public", PUBLIC_PREFIX)

    prompt_path = visible_root / "TASK.md"
    if prompt_path.is_file():
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    else:
        prompt = str(task.get("agent_prompt", ""))

    entry_files: list[str] = []
    stubs: list[str] = []
    if hidden_src is None or reference_src is None:
        status = "partial"
        missing = ("tests_hidden/", "reference/")
        entry_files = [
            str(sf["path"])
            for sf in task.get("seed_files", [])
            if Path(str(sf["path"])).parts[:1] != (tests_dirname,)
        ]
    else:
        status = "complete"
        missing = ()
        _copy_tests(hidden_src, dest / "tests_hidden", HIDDEN_PREFIX)
        _copy_tree(reference_src, dest / "reference")
        entry_files, only_in_reference = _detect_entry_files(
            visible_root, reference_src, tests_dirname
        )
        if not entry_files:
            raise AfbImportError(f"{task_id}: nessun entry file rilevato (reference uguale al seed?)")
        for rel in only_in_reference:
            _write_seed_stub(seed_dir, rel, reference_src / rel)
            stubs.append(rel)

    meta = {
        "id": task_id,
        "title": str(task.get("title", task_id)),
        "prompt": prompt,
        "entry_files": entry_files,
        "timeout_seconds": 60 * int(task.get("estimated_minutes", 5)),
        "taxonomy": [str(f) for f in task.get("primary_failure_modes", [])],
        "provenance": {
            "source": "agent-failure-eval-bench",
            "suite_version": str(task.get("suite_version", "")),
            "afb_task_id": task_id,
            "imported_with": f"aeh {_aeh_version()}",
            "imported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "disclosed_example": True,
            "hidden_tests_origin": hidden_origin,
            "seed_stubs": stubs,
            "notes": (
                "hidden tests e reference provengono dal materiale privato AFB: non pubblicarli "
                "(disclosure policy del bench). I check di processo/rubrica AFB non sono test aeh."
            ),
        },
    }
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "task.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if status == "partial":
        _write_missing_md(dest, task)
    else:
        Fixture.load(dest)  # sanity immediata sul layout; il contratto pieno è `aeh validate`

    return ImportOutcome(
        task_id=task_id,
        fixture_dir=dest,
        status=status,
        entry_files=tuple(entry_files),
        seed_stubs=tuple(stubs),
        missing=missing,
        hidden_origin=hidden_origin,
    )


def _resolve_holdout(
    fixture_src: Path, task: dict, holdout_dir: str | Path | None
) -> tuple[Path | None, Path | None, str]:
    """Cerca hidden_tests/ e reference_solution/: prima nel repo AFB, poi in --holdout-dir."""
    rf = task["runnable_fixture"]
    hidden_rel = str(rf.get("hidden_tests", "hidden_tests"))
    reference_rel = str(rf.get("reference_solution", "reference_solution"))
    candidates = [(fixture_src, "afb-repo")]
    if holdout_dir is not None:
        candidates.append((Path(holdout_dir).resolve() / str(task["id"]), "holdout-dir"))
    for base, origin in candidates:
        hidden, reference = base / hidden_rel, base / reference_rel
        if hidden.is_dir() and reference.is_dir():
            return hidden, reference, origin
    return None, None, "missing"


def _detect_entry_files(
    visible: Path, reference: Path, tests_dirname: str
) -> tuple[list[str], list[str]]:
    """Ritorna (entry_files, solo-in-reference) confrontando reference e materiale visibile.

    Entry = file della reference diverso byte-a-byte dal visibile, oppure assente
    dal visibile (artefatto che l'agente deve produrre). I file di contesto
    identici (es. git_status.txt) non sono entry.
    """
    entries: list[str] = []
    only_in_reference: list[str] = []
    for item in sorted(reference.rglob("*")):
        if item.is_dir() or _is_junk(item):
            continue
        rel = item.relative_to(reference)
        if any(part in JUNK_DIRS for part in rel.parts):
            continue
        if rel.parts[0] == tests_dirname or str(rel) == "TASK.md":
            continue
        visible_file = visible / rel
        if not visible_file.is_file():
            entries.append(str(rel))
            only_in_reference.append(str(rel))
        elif visible_file.read_bytes() != item.read_bytes():
            entries.append(str(rel))
    return entries, only_in_reference


def _write_seed_stub(seed_dir: Path, rel: str, reference_file: Path) -> None:
    """Stub nel seed per un entry file che esiste solo nella reference.

    Per i JSON a oggetto: stesse chiavi top-level con valori vuoti dello stesso tipo
    (l'agente vede la forma attesa); altrimenti file vuoto.
    """
    target = seed_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if reference_file.suffix == ".json":
        try:
            data = json.loads(reference_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            stub = {key: _empty_like(value) for key, value in data.items()}
            target.write_text(json.dumps(stub, indent=2) + "\n", encoding="utf-8")
            return
    target.write_text("", encoding="utf-8")


def _empty_like(value: object) -> object:
    if isinstance(value, bool):
        return False
    if isinstance(value, str):
        return ""
    if isinstance(value, (int, float)):
        return 0
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return None


def _write_missing_md(dest: Path, task: dict) -> None:
    checks = "".join(f"- {c}\n" for c in task.get("hidden_checks", []))
    (dest / "MISSING.md").write_text(
        "# Import parziale — materiale holdout assente\n\n"
        "Mancano `tests_hidden/` e `reference/`: il bundle pubblico AFB li esclude\n"
        "(disclosure policy). Fornisci il materiale privato con `--holdout-dir` e\n"
        "rilancia con `--force`, oppure scrivi i test dai check pubblicati:\n\n"
        f"{checks}",
        encoding="utf-8",
    )


def _copy_tree(src: Path, dst: Path, exclude_top: frozenset[str] = frozenset()) -> None:
    """Copia ricorsiva di soli file, saltando junk e i nomi top-level esclusi."""
    for item in sorted(src.rglob("*")):
        if item.is_dir() or _is_junk(item):
            continue
        rel = item.relative_to(src)
        if rel.parts[0] in exclude_top or any(part in JUNK_DIRS for part in rel.parts):
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _copy_tests(src: Path, dst: Path, prefix: str) -> list[str]:
    """Copia i test (layout AFB piatto): i .py col prefisso aeh, il resto as-is."""
    dst.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for item in sorted(src.iterdir()):
        if item.is_dir() or _is_junk(item) or item.name == "__init__.py":
            continue
        name = _prefixed_name(item.name, prefix) if item.suffix == ".py" else item.name
        shutil.copy2(item, dst / name)
        copied.append(name)
    return copied


def _prefixed_name(name: str, prefix: str) -> str:
    """test_metrics.py → test_public_metrics.py (idempotente se già prefissato)."""
    if name.startswith(prefix):
        return name
    if name.startswith("test_"):
        return f"{prefix}_{name[len('test_'):]}"
    stem = name.removesuffix(".py")
    return f"{prefix}_{stem}.py"


def _is_junk(path: Path) -> bool:
    return path.name in JUNK_DIRS or path.name in JUNK_FILES or path.suffix == ".pyc"


def _aeh_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("agent-eval-harness")
    except PackageNotFoundError:  # pragma: no cover - solo fuori da un install
        return "dev"
