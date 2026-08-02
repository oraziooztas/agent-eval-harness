# How to read aeh metrics

Short version: **solve rate is the signal, public pass rate is not, and hidden gap
means nothing without a floor.**

This file exists because the rule was written once in a DEVLOG entry (2026-07-25)
and the code kept reporting the opposite for a week. A policy that lives only in a
log is a policy the next reader does not have.

## 1. Public pass rate is a regression guard, never a solve signal

A fixture is only valid if the intact seed **passes every public test** and
**fails at least one hidden test** — `aeh validate` enforces exactly that. So on
any valid fixture the public suite is green *before the agent does anything*.

Consequence: a solver that touches nothing still shows a full public score. This
was measured, not assumed — the calibration matrix of 2026-07-25 ran `--noop`
against the three disclosed AFB fixtures and the public suites came back
4/4, 2/2 and 3/3.

Public tests are still worth running and worth showing: they catch a solver that
breaks working behaviour while chasing the hidden contract. That is a regression
guard. It is not evidence that a task was solved, and it must never lead a
summary, a run card or a matrix row.

## 2. Solve rate is the primary metric

`solved` requires every public **and** every hidden test to pass. It is the only
per-run number that answers the question the harness was built for: did the agent
implement the real contract of the task, or only the part it could see?

## 3. Hidden gap must be read against a floor

`hidden_gap_pp = 100 × (public_pass_rate − hidden_pass_rate)`

Lower is better: the ceiling is 0 pp (everything passes), and the floor is
whatever a do-nothing solver scores on the same fixtures. Because public is
pinned near 100% by construction, the gap is mostly a restatement of the hidden
pass rate — which is why a bare gap is easy to misread as an achievement.

`aeh matrix` therefore derives the floor **from the runs in the matrix itself**:

- a `builtin:noop` row is tagged `floor`, a `builtin:ref` row is tagged `ceiling`;
- every row gets `gap_vs_floor_pp`, its distance from that floor;
- if no floor run is present, the matrix prints a warning instead of a naked
  number.

`gap_vs_floor_pp ≈ 0` means the solver did nothing useful, regardless of how
green its visible tests look.

Always include both builtin runs in the same `aeh matrix` invocation as the real
solvers, over the same fixtures:

```bash
aeh run fixtures/<fx> --noop  --out runs/floor
aeh run fixtures/<fx> --ref   --out runs/ceiling
aeh run fixtures/<fx> --solver '<cmd>' --label '<model>' --out runs/<model>
aeh matrix runs/floor runs/ceiling runs/<model> --out runs/matrix
```

## 4. The measured AFB calibration (scope-limited)

From the calibration matrix of 2026-08-02, over the three **disclosed** AFB
fixtures (`afb-v0-002`, `afb-v0-006`, `afb-v0-009`):

| run | solved | solve rate | hidden gap |
|---|---|---|---|
| `builtin:ref` | 3/3 | 100% | 0.0 pp |
| `builtin:noop` | 0/3 | 0% | 66.7 pp |

Per fixture the floor is 50.0 pp on `afb-v0-002` and 75.0 pp on both
`afb-v0-006` and `afb-v0-009`. Public suites stay green under `--noop` in all
three cases (4/4, 2/2, 3/3), which is invariant 1 holding, not a gap.

These two numbers bound any real run **on that fixture set only**. They are not
constants of the harness and are deliberately not hardcoded anywhere in `src/`:
a floor measured on one set of fixtures does not transfer to another, and a
hardcoded one would travel silently. Recompute it per fixture set.

The floor moves when the hidden suites change, and it already has: it read
58.3 pp on the 2026-07-25 matrix, when `afb-v0-002` separated noop from ref on a
single hidden check. AFB added two more discriminating checks on 2026-08-01,
taking that fixture from 1/4 to 3/6 and the aggregate floor from 58.3 to
66.7 pp. Treat any quoted floor as valid only for a stated fixture set at a
stated date, and re-run the two builtins after touching a hidden suite.

## 5. What these numbers are not

- Not a benchmark score, not a leaderboard, not a model ranking.
- The AFB fixtures are **disclosed examples**, not an unseen holdout: any run on
  them must be labelled that way.
- Cost is always solver-reported, never metered by the harness.
