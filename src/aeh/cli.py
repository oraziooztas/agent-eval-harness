"""aeh — CLI: validate fixtures, run solvers, regenerate reports.

Exit codes: 0 ok/solved · 1 harness or validation error · 2 run completed but not solved.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aeh.fixture import Fixture, FixtureError
from aeh.grader import grade
from aeh.report import write_results, write_run_card
from aeh.runner import apply_reference_solver, prepare_workspace, run_solver


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aeh", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="verifica il contratto di 1+ fixture (ref all-pass, seed hidden-fail)")
    p_val.add_argument("fixtures", nargs="+")

    p_run = sub.add_parser("run", help="prepara workspace, esegue il solver, valuta, scrive report")
    p_run.add_argument("fixture")
    group = p_run.add_mutually_exclusive_group(required=True)
    group.add_argument("--solver", help="comando shell eseguito con cwd=workspace")
    group.add_argument("--ref", action="store_true", help="solver builtin: applica la reference solution")
    group.add_argument("--noop", action="store_true", help="solver builtin: non fa nulla (baseline seed)")
    p_run.add_argument("--out", help="directory del run (default: runs/{id}-{ts})")

    p_rep = sub.add_parser("report", help="rigenera run_card.md da results.json")
    p_rep.add_argument("run_dir")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "validate":
            return _cmd_validate(args.fixtures)
        if args.cmd == "run":
            return _cmd_run(args)
        return _cmd_report(args.run_dir)
    except (FixtureError, FileNotFoundError, FileExistsError, RuntimeError) as exc:
        print(f"aeh: errore: {exc}", file=sys.stderr)
        return 1


def _cmd_run(args: argparse.Namespace) -> int:
    fixture = Fixture.load(args.fixture)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) if args.out else Path("runs") / f"{fixture.id}-{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    workspace = prepare_workspace(fixture, run_dir)
    solver_result = None
    if args.ref:
        apply_reference_solver(fixture, workspace)
        label = "builtin:ref"
    elif args.noop:
        label = "builtin:noop"
    else:
        label = args.solver
        solver_result = run_solver(
            workspace, args.solver, fixture.timeout_seconds, run_dir / "transcript.txt"
        )

    result = grade(fixture, workspace, run_dir)
    write_results(run_dir, fixture, label, solver_result, result)
    card = write_run_card(run_dir)
    print(
        f"{fixture.id}: {result.verdict} — public {result.public_passed}/{len(result.public)}, "
        f"hidden {result.hidden_passed}/{len(result.hidden)}\nrun card: {card}"
    )
    return 0 if result.solved else 2


def _cmd_validate(fixture_paths: list[str]) -> int:
    failures = 0
    for path in fixture_paths:
        fixture = Fixture.load(path)
        with tempfile.TemporaryDirectory(prefix="aeh-validate-") as tmp:
            ws_ref = prepare_workspace(fixture, Path(tmp) / "ref")
            apply_reference_solver(fixture, ws_ref)
            g_ref = grade(fixture, ws_ref, Path(tmp) / "ref")

            ws_seed = prepare_workspace(fixture, Path(tmp) / "seed")
            g_seed = grade(fixture, ws_seed, Path(tmp) / "seed")

        checks = [
            ("reference passa tutti i test", g_ref.solved),
            ("seed passa i test pubblici", g_seed.public_passed == len(g_seed.public)),
            ("seed fallisce almeno 1 hidden", g_seed.hidden_passed < len(g_seed.hidden)),
        ]
        ok = all(passed for _, passed in checks)
        failures += 0 if ok else 1
        print(f"{fixture.id}: {'VALID' if ok else 'INVALID'}")
        for label, passed in checks:
            print(f"  {'✓' if passed else '✗'} {label}")
    return 1 if failures else 0


def _cmd_report(run_dir: str) -> int:
    card = write_run_card(run_dir)
    print(f"run card: {card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
