"""Workspace preparation and solver execution.

The agent workspace contains ONLY: seed files, public tests (tests/), PROMPT.md.
Hidden tests never touch this directory — invariant checked at the end of prep
and re-checked at grading time.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from aeh.fixture import HIDDEN_PREFIX, Fixture
from aeh.sandbox import wrap_shell

PROMPT_FILE = "PROMPT.md"
USAGE_ENV = "AEH_USAGE_FILE"
API_KEY_ENV = "ANTHROPIC_API_KEY"

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


@dataclass(frozen=True)
class Credential:
    """API key risolta per il solver. Il valore non compare mai nei report né nel repr."""

    env_var: str  # variabile da cui è stata letta
    value: str = field(repr=False)

    @property
    def fingerprint(self) -> str:
        """sha256 troncato: identifica QUALE chiave, senza rivelarla."""
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "env_var": self.env_var,
            "injected_as": API_KEY_ENV,
            "fingerprint": f"sha256:{self.fingerprint}",
            "source": "env",
        }

    def as_env(self) -> dict[str, str]:
        return {API_KEY_ENV: self.value}


def resolve_api_credential(env_var: str = API_KEY_ENV) -> Credential:
    """Legge la API key da ``env_var``, o fallisce con un messaggio azionabile.

    Esplicito per costruzione: una run con modello reale deve pagare in dollari
    tramite una API key, MAI consumare la quota dell'abbonamento Claude Code —
    sotto abbonamento il costo per token non esiste e ``$AEH_USAGE_FILE`` non
    può produrre un €/task-risolto onesto.
    """
    value = (os.environ.get(env_var) or "").strip()
    if not value:
        raise RuntimeError(
            f"credenziale assente: ${env_var} non è impostata (o è vuota).\n"
            f"  La API key è cosa diversa dall'abbonamento Claude Code: l'abbonamento NON\n"
            f"  va usato per gli eval (consuma quota di sessione e non ha costo per token).\n"
            f"  Chiave su console.anthropic.com → Settings → API keys, poi nella STESSA shell:\n"
            f"    {env_var}='sk-ant-…' aeh run … --require-api-key {env_var}\n"
            f"  Nota: ~/.zshrc fa `unset ANTHROPIC_API_KEY` a ogni shell interattiva (guardrail\n"
            f"  anti-overage di Claude Code): un `export` in un'altra tab non sopravvive.\n"
            f"  Per non toccare quel guardrail, tieni la chiave in AEH_ANTHROPIC_API_KEY e passa\n"
            f"  `--require-api-key AEH_ANTHROPIC_API_KEY`: aeh la inietta come {API_KEY_ENV}\n"
            f"  SOLO nel sottoprocesso del solver."
        )
    return Credential(env_var, value)


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
    extra_env: Mapping[str, str] | None = None,
) -> SolverResult:
    """Run the solver shell command with cwd=workspace, capturing a transcript.

    With ``net_sandbox_backend`` the command runs with network access denied
    (only for solvers that don't need the network: local models, script bots).
    With ``usage_file`` the solver sees ``AEH_USAGE_FILE`` in the environment
    and can report its own token/cost usage there (see load_usage).
    With ``extra_env`` (tipicamente ``Credential.as_env()``) le variabili sono
    iniettate SOLO nel sottoprocesso del solver, senza toccare la shell chiamante.
    """
    tpath = Path(transcript_path).resolve()
    tpath.parent.mkdir(parents=True, exist_ok=True)
    exec_command = command
    if net_sandbox_backend:
        exec_command = wrap_shell(command, net_sandbox_backend)
    overrides: dict[str, str] = {}
    if usage_file is not None:
        overrides[USAGE_ENV] = str(Path(usage_file).resolve())
    if extra_env:
        overrides |= dict(extra_env)
    env = os.environ | overrides if overrides else None
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
