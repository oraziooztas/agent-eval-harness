"""Sandbox di rete: costruzione wrapper + semantica di negazione verificata dal vivo.

La proprietà critica: una connect che SENZA sandbox viene rifiutata dal peer
(ECONNREFUSED: lo stack di rete è raggiungibile) sotto sandbox deve fallire
PRIMA di raggiungere lo stack (EPERM su seatbelt, unreachable su unshare).
Test ermetico: porta 9 su loopback, nessun bisogno di internet.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from aeh import sandbox
from aeh.fixture import Fixture
from aeh.grader import grade
from aeh.runner import prepare_workspace, run_solver

FIXTURES = Path(__file__).parent.parent / "fixtures"
FX_DEDUP = FIXTURES / "fx-001-csv-dedup"
FX_SLUG = FIXTURES / "fx-002-slugify"

PROBE = "import socket; s=socket.socket(); print(s.connect_ex(('127.0.0.1', 9)))"
CONN_REFUSED = {61, 111}  # ECONNREFUSED su macOS / Linux


# ---------- Costruzione wrapper ----------

def test_wrap_argv_seatbelt():
    argv = sandbox.wrap_argv(["python3", "-c", "pass"], "seatbelt")
    assert argv[0] == "sandbox-exec"
    assert sandbox.SEATBELT_PROFILE in argv
    assert argv[-3:] == ["python3", "-c", "pass"]


def test_wrap_argv_unshare():
    argv = sandbox.wrap_argv(["python3"], "unshare-net")
    assert argv[:3] == ["unshare", "--map-root-user", "--net"]


def test_wrap_argv_unknown_backend():
    with pytest.raises(ValueError, match="sconosciuto"):
        sandbox.wrap_argv(["true"], "jail")


def test_wrap_shell_quotes():
    cmd = sandbox.wrap_shell("echo 'ciao mondo'", "seatbelt")
    assert cmd.startswith("sandbox-exec")
    assert "/bin/sh" in cmd


def test_backend_detection(monkeypatch):
    monkeypatch.setattr(sandbox.sys, "platform", "darwin")
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: "/usr/bin/tool")
    assert sandbox.backend() == "seatbelt"
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    assert sandbox.backend() == "unshare-net"
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)
    assert sandbox.backend() is None


# ---------- Negazione di rete reale ----------

@pytest.mark.skipif(sandbox.backend() is None, reason="nessun backend sandbox su questo host")
def test_network_denied_for_real():
    plain = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, timeout=30
    )
    assert plain.returncode == 0
    rc_plain = int(plain.stdout.strip())
    if rc_plain not in CONN_REFUSED:
        pytest.skip(f"loopback anomalo su questo host (rc={rc_plain})")

    backend = sandbox.backend()
    wrapped = subprocess.run(
        sandbox.wrap_argv([sys.executable, "-c", PROBE], backend),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if wrapped.returncode != 0:
        pytest.skip(f"backend {backend} non eseguibile qui: {wrapped.stderr[:200]}")
    rc_sandboxed = int(wrapped.stdout.strip())
    assert rc_sandboxed != 0
    assert rc_sandboxed not in CONN_REFUSED


@pytest.mark.skipif(sandbox.backend() is None, reason="nessun backend sandbox su questo host")
def test_solver_sandboxed_probe(tmp_path):
    fx = Fixture.load(FX_SLUG)
    ws = prepare_workspace(fx, tmp_path)
    res = run_solver(
        ws,
        f"'{sys.executable}' -c \"{PROBE}\"",
        30,
        tmp_path / "transcript.txt",
        net_sandbox_backend=sandbox.backend(),
    )
    if res.status != "ok":
        pytest.skip(f"backend {res.sandbox} non eseguibile qui")
    assert res.sandbox == sandbox.backend()
    match = re.search(r"--- stdout ---\s*(\d+)", res.transcript_path.read_text())
    assert match, "rc della probe non trovato nel transcript"
    assert int(match.group(1)) not in CONN_REFUSED | {0}


# ---------- Grading sandboxed ----------

def test_grading_records_sandbox(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    result = grade(fx, ws, tmp_path)
    assert result.grading_sandbox == (sandbox.backend() or "unavailable")


def test_grading_sandbox_disabled(tmp_path):
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    result = grade(fx, ws, tmp_path, net_sandbox=False)
    assert result.grading_sandbox == "disabled"


def test_grading_falls_back_when_backend_broken(tmp_path, monkeypatch):
    """Backend presente ma rotto: il grading resta valido e lo dichiara."""
    monkeypatch.setattr(sandbox, "backend", lambda: "seatbelt")
    monkeypatch.setattr(
        sandbox, "wrap_argv", lambda argv, b: ["/nonexistent-sandbox-tool", *argv]
    )
    fx = Fixture.load(FX_DEDUP)
    ws = prepare_workspace(fx, tmp_path)
    result = grade(fx, ws, tmp_path)
    assert result.grading_sandbox == "fallback-off:seatbelt"
    assert result.public  # il grading è comunque avvenuto
