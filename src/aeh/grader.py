"""Grading with true hidden-check separation.

The grading directory is built fresh from PRISTINE fixture material:
seed files, then the agent's entry files copied over, then pristine public
AND hidden tests. Nothing else from the agent workspace propagates — an agent
that edits its test files changes nothing about its grade.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from aeh import sandbox
from aeh.fixture import HIDDEN_PREFIX, PUBLIC_PREFIX, Fixture
from aeh.runner import find_hidden_leaks

_TESTRUN_SCRIPT = '''\
import io
import json
import sys
import unittest

def main() -> None:
    tests_dir, out_path = sys.argv[1], sys.argv[2]
    sys.path.insert(0, ".")
    results = []

    class Collect(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            results.append({"id": test.id(), "outcome": "pass", "message": ""})

        def addFailure(self, test, err):
            super().addFailure(test, err)
            results.append({"id": test.id(), "outcome": "fail",
                            "message": self._exc_info_to_string(err, test)[-800:]})

        def addError(self, test, err):
            super().addError(test, err)
            results.append({"id": test.id(), "outcome": "error",
                            "message": self._exc_info_to_string(err, test)[-800:]})

    suite = unittest.TestLoader().discover(tests_dir, top_level_dir=".")
    unittest.TextTestRunner(resultclass=Collect, verbosity=0, stream=io.StringIO()).run(suite)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh)

main()
'''


@dataclass(frozen=True)
class GradeResult:
    public: list[dict] = field(default_factory=list)
    hidden: list[dict] = field(default_factory=list)
    tamper_suspect: list[str] = field(default_factory=list)
    hidden_sha256: str = ""
    public_sha256: str = ""
    # Il codice dell'agente gira durante il grading: qui è registrato se la
    # rete era negata ("seatbelt"/"unshare-net") oppure no e perché.
    grading_sandbox: str = "disabled"

    @property
    def public_passed(self) -> int:
        return sum(1 for t in self.public if t["outcome"] == "pass")

    @property
    def hidden_passed(self) -> int:
        return sum(1 for t in self.hidden if t["outcome"] == "pass")

    @property
    def solved(self) -> bool:
        return (
            bool(self.public)
            and bool(self.hidden)
            and all(t["outcome"] == "pass" for t in self.public + self.hidden)
        )

    @property
    def verdict(self) -> str:
        if self.solved:
            return "SOLVED"
        if self.hidden_passed or self.public_passed:
            return "PARTIAL"
        return "UNSOLVED"

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "solved": self.solved,
            "public": {
                "passed": self.public_passed,
                "total": len(self.public),
                "tests": self.public,
            },
            "hidden": {
                "passed": self.hidden_passed,
                "total": len(self.hidden),
                "tests": self.hidden,
            },
            "tamper_suspect": self.tamper_suspect,
            "hidden_sha256": self.hidden_sha256,
            "public_sha256": self.public_sha256,
            "grading_sandbox": self.grading_sandbox,
        }


def grade(
    fixture: Fixture,
    workspace: str | Path,
    run_dir: str | Path,
    *,
    net_sandbox: bool = True,
) -> GradeResult:
    """Grade the agent's solution in a fresh directory. Never trusts workspace tests.

    With ``net_sandbox`` (default) the grading subprocess runs with network
    access denied when a backend exists: grading never needs the network, and
    the agent's entry files DO execute here. If the sandboxed run cannot even
    produce results (backend broken on this host), it falls back to an
    unsandboxed run and records that honestly.
    """
    ws = Path(workspace).resolve()
    grading = Path(run_dir).resolve() / "grading"
    if grading.exists():
        shutil.rmtree(grading)
    grading.mkdir(parents=True)

    # Pristine seed as base, agent entry files on top (missing file = seed stays).
    for item in sorted((fixture.root / "seed").iterdir()):
        if item.is_dir():
            shutil.copytree(item, grading / item.name)
        else:
            shutil.copy2(item, grading / item.name)
    for name in fixture.entry_files:
        candidate = ws / name
        if candidate.is_file():
            (grading / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, grading / name)

    # Pristine tests, public + hidden, straight from the fixture.
    tests_dir = grading / "tests"
    tests_dir.mkdir()
    for src_dir in ("tests_public", "tests_hidden"):
        for f in sorted((fixture.root / src_dir).glob("*.py")):
            shutil.copy2(f, tests_dir / f.name)
    (tests_dir / "__init__.py").touch()

    runner_path = grading / "_aeh_testrun.py"
    runner_path.write_text(_TESTRUN_SCRIPT, encoding="utf-8")
    raw_path = grading / "_results_raw.json"
    argv = ["python3", "_aeh_testrun.py", "tests", raw_path.name]
    backend = sandbox.backend() if net_sandbox else None
    if net_sandbox and backend is None:
        sandbox_label = "unavailable"
    else:
        sandbox_label = backend or "disabled"

    def _run_tests(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=grading,
            capture_output=True,
            text=True,
            timeout=max(60, fixture.timeout_seconds),
            env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin:/usr/local/bin"},
            check=False,  # the exit code IS the result: a failing test suite is not an error here
        )

    try:
        proc = _run_tests(sandbox.wrap_argv(argv, backend) if backend else argv)
    except OSError:
        if not backend:
            raise
        proc = None
    if backend and not raw_path.is_file():
        # Il backend stesso non è partito (es. unshare senza userns): meglio un
        # grading valido e dichiarato non-sandboxed che nessun grading.
        proc = _run_tests(argv)
        sandbox_label = f"fallback-off:{backend}"
    if not raw_path.is_file():
        detail = f"rc={proc.returncode}: {proc.stderr[-500:]}" if proc else "exec fallita"
        raise RuntimeError(f"test runner non ha prodotto risultati ({detail})")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    public = [t for t in raw if PUBLIC_PREFIX in t["id"]]
    hidden = [t for t in raw if HIDDEN_PREFIX in t["id"]]

    return GradeResult(
        public=public,
        hidden=hidden,
        tamper_suspect=find_hidden_leaks(ws),
        hidden_sha256=fixture.hidden_sha256(),
        public_sha256=fixture.public_sha256(),
        grading_sandbox=sandbox_label,
    )
