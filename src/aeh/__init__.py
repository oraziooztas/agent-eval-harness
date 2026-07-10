"""agent-eval-harness: run coding agents against fixtures with true hidden-check separation.

Invariants the harness enforces:
1. The agent workspace NEVER contains hidden tests (only seed + public tests + PROMPT.md).
2. Grading happens in a fresh directory: pristine seed + the agent's entry files
   + pristine public AND hidden tests from the fixture. Agent edits to test files
   never reach grading (tamper-proof by construction).
3. Results record the SHA-256 of the hidden test set, proving which checks graded the run.
"""

from aeh.fixture import Fixture, FixtureError
from aeh.grader import GradeResult, grade
from aeh.runner import SolverResult, prepare_workspace, run_solver

__all__ = [
    "Fixture",
    "FixtureError",
    "GradeResult",
    "SolverResult",
    "grade",
    "prepare_workspace",
    "run_solver",
]

__version__ = "0.1.0"
