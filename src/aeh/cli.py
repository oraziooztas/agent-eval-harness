"""aeh — CLI: validate fixtures, run solvers, regenerate reports.

Exit codes: 0 ok/solved · 1 harness or validation error · 2 run completed but not solved.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from aeh import sandbox
from aeh.fixture import Fixture, FixtureError
from aeh.grader import grade
from aeh.importer import AfbImportError, import_tasks
from aeh.matrix import write_matrix
from aeh.report import write_results, write_run_card
from aeh.runner import apply_reference_solver, load_usage, prepare_workspace, run_solver


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
    p_run.add_argument(
        "--sandbox-solver",
        action="store_true",
        help="nega la rete al solver (solo solver locali/offline; errore se nessun backend)",
    )
    p_run.add_argument(
        "--no-grading-sandbox",
        action="store_true",
        help="non negare la rete al grading (default: negata quando un backend esiste)",
    )
    p_run.add_argument("--price-in", type=float, help="prezzo input EUR per Mtok (per usage)")
    p_run.add_argument("--price-out", type=float, help="prezzo output EUR per Mtok (per usage)")
    p_run.add_argument(
        "--label",
        help="etichetta del solver nei report (default: il comando); chiave di raggruppamento in matrix",
    )

    p_rep = sub.add_parser("report", help="rigenera run_card.md da results.json")
    p_rep.add_argument("run_dir")

    p_mat = sub.add_parser("matrix", help="aggrega N run dir in una matrice cross-solver")
    p_mat.add_argument("run_dirs", nargs="+")
    p_mat.add_argument("--out", default="runs/matrix", help="directory output (default: runs/matrix)")

    p_imp = sub.add_parser(
        "import-afb",
        help="importa i task eseguibili di agent-failure-eval-bench come fixture aeh (ADR-001)",
    )
    p_imp.add_argument("afb_root", help="root del repo AFB (clone pubblico o repo di lavoro)")
    p_imp.add_argument(
        "--task-id",
        action="append",
        help="importa solo questo task id (ripetibile; default: tutti gli eseguibili)",
    )
    p_imp.add_argument("--out", default="fixtures", help="directory destinazione (default: fixtures)")
    p_imp.add_argument(
        "--holdout-dir",
        help="materiale privato per task id: <dir>/<task-id>/{hidden_tests,reference_solution}",
    )
    p_imp.add_argument("--force", action="store_true", help="sovrascrive fixture già importate")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "validate":
            return _cmd_validate(args.fixtures)
        if args.cmd == "run":
            return _cmd_run(args)
        if args.cmd == "matrix":
            return _cmd_matrix(args)
        if args.cmd == "import-afb":
            return _cmd_import(args)
        return _cmd_report(args.run_dir)
    except (AfbImportError, FixtureError, FileNotFoundError, FileExistsError, RuntimeError) as exc:
        print(f"aeh: errore: {exc}", file=sys.stderr)
        return 1


def _cmd_run(args: argparse.Namespace) -> int:
    fixture = Fixture.load(args.fixture)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) if args.out else Path("runs") / f"{fixture.id}-{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    solver_backend = None
    if args.sandbox_solver:
        solver_backend = sandbox.backend()
        if solver_backend is None:
            raise RuntimeError("--sandbox-solver richiesto ma nessun backend sandbox su questo host")

    workspace = prepare_workspace(fixture, run_dir)
    solver_result = None
    usage = None
    if args.ref:
        apply_reference_solver(fixture, workspace)
        label = args.label or "builtin:ref"
    elif args.noop:
        label = args.label or "builtin:noop"
    else:
        label = args.label or args.solver
        usage_file = run_dir / "usage.json"
        solver_result = run_solver(
            workspace,
            args.solver,
            fixture.timeout_seconds,
            run_dir / "transcript.txt",
            net_sandbox_backend=solver_backend,
            usage_file=usage_file,
        )
        usage = load_usage(usage_file, args.price_in, args.price_out)

    result = grade(fixture, workspace, run_dir, net_sandbox=not args.no_grading_sandbox)
    write_results(run_dir, fixture, label, solver_result, result, usage)
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


def _cmd_import(args: argparse.Namespace) -> int:
    outcomes = import_tasks(
        args.afb_root,
        args.out,
        task_ids=args.task_id,
        holdout_dir=args.holdout_dir,
        force=args.force,
    )
    partials = 0
    for outcome in outcomes:
        if outcome.status == "complete":
            stub_note = (
                f" (stub nel seed: {', '.join(outcome.seed_stubs)})" if outcome.seed_stubs else ""
            )
            print(
                f"{outcome.task_id} → {outcome.fixture_dir} [complete, "
                f"holdout: {outcome.hidden_origin}] entry: {', '.join(outcome.entry_files)}{stub_note}"
            )
        else:
            partials += 1
            print(
                f"{outcome.task_id} → {outcome.fixture_dir} [PARTIAL] "
                f"mancano: {', '.join(outcome.missing)} — vedi MISSING.md"
            )
    print(f"importate {len(outcomes)} fixture, {partials} parziali")
    return 2 if partials else 0


def _cmd_report(run_dir: str) -> int:
    card = write_run_card(run_dir)
    print(f"run card: {card}")
    return 0


def _cmd_matrix(args: argparse.Namespace) -> int:
    md = write_matrix(args.run_dirs, args.out)
    print(f"matrix: {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
