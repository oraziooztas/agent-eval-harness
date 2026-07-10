"""Workspace preparation and solver execution.

The agent workspace contains ONLY: seed files, public tests (tests/), PROMPT.md.
Hidden tests never touch this directory — invariant checked at the end of prep
and re-checked at grading time.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from aeh.fixture import HIDDEN_PREFIX, Fixture

PROMPT_FILE = "PROMPT.md"

_PROMPT_TEMPLATE = """# {title}

{prompt}

## Regole

- Modifica SOLO questi file: {entry_files}
- I test pubblici sono in `tests/`. Eseguili con: `python3 -m unittest discover -s tests -t .`
- Esiste anche un set di test nascosti che verrà eseguito a valutazione:
  superare i test pubblici è necessario ma non sufficiente. Ragiona sui casi limite.
- Non modificare i file di test: la valutazione usa comunque copie intatte.
"""


@dataclass(frozen=True)
class SolverResult:
    status: str  # "ok" | "timeout" | "error"
    returncode: int | None
    duration_seconds: float
    transcript_path: Path


def prepare_workspace(fixture: Fixture, run_dir: str | Path) -> Path:
    """Create run_dir/workspace with seed + public tests + PROMPT.md. No hidden tests."""
    run_path = Path(run_dir).resolve()
    workspace = run_path / "workspace"
    if workspace.exists():
        raise FileExistsError(f"workspace già esistente: {workspace}")
    workspace.mkdir(parents=True)

    _copy_tree_contents(fixture.root / "seed", workspace)
    tests_dir = workspace / "tests"
    tests_dir.mkdir(exist_ok=True)
    _copy_tree_contents(fixture.root / "tests_public", tests_dir)
    (tests_dir / "__init__.py").touch()

    prompt = _PROMPT_TEMPLATE.format(
        title=fixture.title,
        prompt=fixture.prompt,
        entry_files=", ".join(f"`{n}`" for n in fixture.entry_files),
    )
    (workspace / PROMPT_FILE).write_text(prompt, encoding="utf-8")

    leaked = find_hidden_leaks(workspace)
    if leaked:
        raise RuntimeError(f"invariante violata: file hidden nel workspace: {leaked}")
    return workspace


def find_hidden_leaks(workspace: Path) -> list[str]:
    """Any file whose name starts with the hidden prefix, anywhere in the workspace."""
    return sorted(
        str(p.relative_to(workspace))
        for p in workspace.rglob(f"{HIDDEN_PREFIX}*")
        if p.is_file()
    )


def run_solver(
    workspace: Path,
    command: str,
    timeout_seconds: int,
    transcript_path: str | Path,
) -> SolverResult:
    """Run the solver shell command with cwd=workspace, capturing a transcript."""
    tpath = Path(transcript_path).resolve()
    tpath.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        status = "ok" if proc.returncode == 0 else "error"
        returncode: int | None = proc.returncode
        out, err = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        status, returncode = "timeout", None
        out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    duration = time.monotonic() - start

    tpath.write_text(
        f"$ {command}\n(status: {status}, rc: {returncode}, {duration:.1f}s)\n"
        f"\n--- stdout ---\n{out}\n--- stderr ---\n{err}\n",
        encoding="utf-8",
    )
    return SolverResult(status, returncode, duration, tpath)


def apply_reference_solver(fixture: Fixture, workspace: Path) -> None:
    """Built-in 'ref' solver: copy the reference entry files into the workspace."""
    for name in fixture.entry_files:
        shutil.copy2(fixture.root / "reference" / name, workspace / name)


def _copy_tree_contents(src: Path, dst: Path) -> None:
    for item in sorted(src.iterdir()):
        if item.name.startswith("__pycache__"):
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)
