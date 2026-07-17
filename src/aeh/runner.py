"""Workspace preparation and solver execution.

The agent workspace contains ONLY: seed files, public tests (tests/), PROMPT.md.
Hidden tests never touch this directory — invariant checked at the end of prep
and re-checked at grading time.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from aeh.fixture import HIDDEN_PREFIX, Fixture
from aeh.sandbox import wrap_shell

PROMPT_FILE = "PROMPT.md"
USAGE_ENV = "AEH_USAGE_FILE"

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
    sandbox: str = "off"  # "off" | backend name (rete negata al solver)


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
    *,
    net_sandbox_backend: str | None = None,
    usage_file: str | Path | None = None,
) -> SolverResult:
    """Run the solver shell command with cwd=workspace, capturing a transcript.

    With ``net_sandbox_backend`` the command runs with network access denied
    (only for solvers that don't need the network: local models, script bots).
    With ``usage_file`` the solver sees ``AEH_USAGE_FILE`` in the environment
    and can report its own token/cost usage there (see load_usage).
    """
    tpath = Path(transcript_path).resolve()
    tpath.parent.mkdir(parents=True, exist_ok=True)
    exec_command = command
    if net_sandbox_backend:
        exec_command = wrap_shell(command, net_sandbox_backend)
    env = None
    if usage_file is not None:
        env = os.environ | {USAGE_ENV: str(Path(usage_file).resolve())}
    start = time.monotonic()
    try:
        proc = subprocess.run(
            exec_command,
            shell=True,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
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
        f"$ {exec_command}\n(status: {status}, rc: {returncode}, {duration:.1f}s)\n"
        f"\n--- stdout ---\n{out}\n--- stderr ---\n{err}\n",
        encoding="utf-8",
    )
    return SolverResult(status, returncode, duration, tpath, net_sandbox_backend or "off")


def load_usage(
    usage_file: str | Path,
    price_in_eur_mtok: float | None = None,
    price_out_eur_mtok: float | None = None,
) -> dict | None:
    """Read the solver-reported usage file, if any.

    Expected JSON: ``{"tokens_in": int, "tokens_out": int, "cost_eur": float}``
    (all optional). A missing cost is computed from tokens when both prices
    (EUR per Mtok) are given. Provenance is always "solver-reported": the value
    comes from the process under evaluation, it is data, not proof.
    """
    path = Path(usage_file)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("usage non è un oggetto JSON")
    except (json.JSONDecodeError, ValueError) as exc:
        return {"error": f"usage file non parsabile: {exc}", "source": "solver-reported"}

    def _num(key: str) -> float | None:
        value = raw.get(key)
        return float(value) if isinstance(value, (int, float)) else None

    tokens_in, tokens_out, cost = _num("tokens_in"), _num("tokens_out"), _num("cost_eur")
    if (
        cost is None
        and tokens_in is not None
        and tokens_out is not None
        and price_in_eur_mtok is not None
        and price_out_eur_mtok is not None
    ):
        cost = tokens_in / 1e6 * price_in_eur_mtok + tokens_out / 1e6 * price_out_eur_mtok
    return {
        "tokens_in": int(tokens_in) if tokens_in is not None else None,
        "tokens_out": int(tokens_out) if tokens_out is not None else None,
        "cost_eur": round(cost, 4) if cost is not None else None,
        "source": "solver-reported",
    }


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
