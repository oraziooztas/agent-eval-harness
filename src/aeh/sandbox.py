"""Network sandbox for subprocesses.

Grading executes agent-written code (the entry files get imported by the test
suite) and never needs the network: on hosts with a sandbox facility the
grading subprocess runs with network access denied. The solver can opt in to
the same treatment (useful for local/offline solvers; API-based agent CLIs
need the network to exist at all).

Backends:
- macOS: ``sandbox-exec`` (seatbelt) with a deny-network profile. Deprecated
  in the headers but present and maintained on every macOS; blocking is
  observable: a connect that would be refused (ECONNREFUSED) becomes EPERM.
- Linux: ``unshare`` with a fresh user+network namespace (loopback down).
"""

from __future__ import annotations

import shlex
import shutil
import sys

SEATBELT_PROFILE = "(version 1)(allow default)(deny network*)"


def backend() -> str | None:
    """Name of the net-sandbox backend available on this host, or None."""
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if sys.platform.startswith("linux") and shutil.which("unshare"):
        return "unshare-net"
    return None


def wrap_argv(argv: list[str], backend_name: str) -> list[str]:
    """Wrap an argv so the process runs with network access denied."""
    if backend_name == "seatbelt":
        return ["sandbox-exec", "-p", SEATBELT_PROFILE, *argv]
    if backend_name == "unshare-net":
        return ["unshare", "--map-root-user", "--net", *argv]
    raise ValueError(f"backend sandbox sconosciuto: {backend_name}")


def wrap_shell(command: str, backend_name: str) -> str:
    """Wrap a shell command string so it runs with network access denied."""
    wrapped = wrap_argv(["/bin/sh", "-c", command], backend_name)
    return " ".join(shlex.quote(part) for part in wrapped)
