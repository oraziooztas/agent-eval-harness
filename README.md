# agent-eval-harness

Minimal harness for evaluating coding agents with **real hidden-check separation**: the agent works on a seed repo with only the public tests; grading happens in a clean directory with both public and hidden tests intact, taken from the fixture. Runtime is 100% stdlib.

## Why it exists

Evaluating an agent on the tests the agent itself can see (or modify) measures nothing. This harness makes the separation a structural invariant, not a convention:

1. **The agent's workspace never contains the hidden tests** (checked at the end of preparation and re-checked at grading).
2. **Grading does not trust the workspace**: a fresh directory holds the intact seed plus ONLY the agent's entry files plus public and hidden tests taken from the fixture. An agent that rewrites the tests changes its own grade by zero.
3. **Every run records the SHA-256 of the hidden set**: cryptographic proof of which checks graded the run.

## Anatomy of a fixture

```
fx-001-csv-dedup/
├── task.json          id, title, prompt, entry_files, timeout_seconds, taxonomy
├── seed/              the buggy/incomplete repo the agent starts from
├── tests_public/      test_public*.py — visible to the agent (happy path)
├── tests_hidden/      test_hidden*.py — NEVER seen by the agent (edge cases)
└── reference/         correct solution of the entry files
```

Design contract (checked by `aeh validate`): the seed **passes the public tests** but **fails ≥1 hidden test** (the bug lives in the edge cases); the reference passes everything. That way "passes the public tests" and "solved the task" stay distinct measures.

## Usage

```bash
# install (dev)
uv venv .venv && uv pip install -e ".[dev]" --python .venv/bin/python

# 1. check the fixture contract
aeh validate fixtures/fx-001-csv-dedup fixtures/fx-002-slugify

# 2. baseline: what happens with no agent (seed as-is)
aeh run fixtures/fx-001-csv-dedup --noop      # exit 2, PARTIAL

# 3. sanity: the reference solves it
aeh run fixtures/fx-001-csv-dedup --ref       # exit 0, SOLVED

# 4. a real agent: any shell command, cwd = workspace
aeh run fixtures/fx-001-csv-dedup \
  --solver 'claude -p "$(cat PROMPT.md)" --permission-mode acceptEdits' \
  --label claude-sonnet --price-in 2.5 --price-out 12.0

# 5. cross-solver matrix from N runs (solve rate, hidden gap, EUR/solved task)
aeh matrix runs/* --out runs/matrix
```

Each run produces `runs/{id}-{ts}/` with `workspace/` (what the agent saw and touched), `grading/` (the clean evaluation), `transcript.txt`, `results.json` and `run_card.md` (verdict, public/hidden table, hash of the hidden set, reproduction steps).

Exit codes: `0` solved · `1` harness/contract error · `2` valid run but not solved.

## What it measures (and what it doesn't)

- Measures: the agent's ability to solve the REAL contract of the task, not just the tests it sees. The gap between public-pass and hidden-pass is the interesting signal (overfitting to the visible tests).
- `tamper_suspect`: files named like hidden tests, created by the agent in the workspace, are flagged in the run card (grading stays valid either way).
- Does not (yet): filesystem confinement of the solver (it runs as your user, so use an agent CLI you trust), multi-language support (fixture tests are Python `unittest`), run parallelism.

## Network sandbox

The code written by the agent IS EXECUTED at grading (the tests import the entry
files), so grading runs with the network denied whenever a backend exists:
`sandbox-exec` on macOS (seatbelt: deprecated in the headers but present and
maintained; a refused connect becomes EPERM), `unshare --net` on Linux. Every run
records in `results.json` what actually happened (`grading_sandbox`: backend,
`unavailable`, `disabled`, or `fallback-off:*` if the backend would not start).
Escape hatch: `--no-grading-sandbox`. The solver, on the other hand, has network by
default (agent CLIs need it for the API); `--sandbox-solver` denies it explicitly to
local/offline solvers.

## Cost per solved task

The solver can report its own consumption by writing JSON to the file named by
`$AEH_USAGE_FILE` (`{"tokens_in": …, "tokens_out": …, "cost_eur": …}`); with
`--price-in/--price-out` (EUR per Mtok) the cost is computed from the tokens. The
provenance is always marked `solver-reported`: it is data from the process under
evaluation, not a proof. `aeh matrix` aggregates N runs per label (`--label`) and
reports, for each solver, solve rate, hidden gap, median latency and
**EUR/solved-task** (only when ALL of the solver's runs carry a cost: no invented
averages on partial data).

## AFB bridge (`aeh import-afb`)

aeh is the runner for the next matrices of the [Agent Failure Eval Bench](https://github.com/oraziooztas/agent-failure-eval-bench): two separate repos with a one-way bridge (ADR-001 in `docs/`). AFB stays the bench artifact (specs, taxonomy, policy, evidence), aeh executes. The importer converts AFB's executable tasks into aeh fixtures:

```bash
aeh import-afb path/to/afb/repo --out fixtures               # holdout inside the working repo
aeh import-afb path/to/public/clone --holdout-dir DIR        # external private materials
```

- `agent_visible/` → `seed/` (without `tests/` and TASK.md, which becomes the prompt); public tests renamed `test_public_*`; the non-.py test assets stay visible in the workspace but grading ignores them.
- `entry_files` detected by diffing reference against visible; reference-only artifacts the agent must produce (e.g. `attempt_log.json`) get a stub in the seed, recorded in `provenance.seed_stubs` together with the holdout origin and timestamp.
- The public AFB bundle **excludes** hidden tests and reference (disclosure policy): without the private materials the import is `PARTIAL` (exit 2) with a `MISSING.md` listing the published hidden checks as author guidance. Complete imported fixtures contain the bench's private material, so do NOT commit them to a public repo (here: `.gitignore fixtures/afb-*`).
- AFB's process/rubric checks (trace, communication) do not become aeh tests: only the mechanically executable part carries over. Matrix results go back to AFB as evidence, citing the version of aeh used.

On the first real import (v0.3.0) `aeh validate` caught a real drift in the bench: the hidden test of `afb-v0-006` expected a trailing newline the published note does not have, confirmed by AFB's internal validator and fixed on the private holdout side (the public file is frozen by the SHA-256 manifest).

## Quality

- 70 pytest tests, 94% coverage (CI gate: 80%), ruff clean.
- The suite explicitly checks: separation (no hidden test in the workspace), tamper-proofing (edits to the tests leave grading unchanged), fixture contract (4 fixtures), solver timeout, CLI exit codes, REAL network denial (loopback probe: refused without the sandbox, EPERM/unreachable under it), honest backend fallback, usage ingestion, matrix, and AFB import (mapping, rename, stub, external holdout, partial, full contract of the imported fixture).
