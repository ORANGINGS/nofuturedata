# NoFutureData

[![CI](https://github.com/ORANGINGS/nofuturedata/actions/workflows/ci.yml/badge.svg)](https://github.com/ORANGINGS/nofuturedata/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/ORANGINGS/nofuturedata)](https://github.com/ORANGINGS/nofuturedata/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/ORANGINGS/nofuturedata/total)](https://github.com/ORANGINGS/nofuturedata/releases)
[![Project site](https://img.shields.io/badge/site-NoFutureData-9b7cff)](https://orangings.github.io/nofuturedata/)

**Zero-mandatory-dependency temporal data-leakage linter and point-in-time guard for
Python/Jupyter time-series, ML, forecasting, and backtests.**

Most leakage tools ask whether train and test rows overlap. NoFutureData asks a
more operational question:

> At the instant this prediction or decision was made, could the pipeline have
> actually known every input it used?

It separates event time from availability time, statically flags common
future-looking pandas patterns, and can test a feature pipeline by deleting or
mutating future inputs and verifying that past outputs do not change.

NoFutureData is local and deterministic. The core has no mandatory runtime
dependency or network service; the dataframe join helper uses optional pandas.

> **Reviewer path:** start with the [research brief](docs/RESEARCH_BRIEF.md),
> inspect the [evaluation and falsification contract](docs/EVALUATION.md), then
> run `python benchmarks/run_evaluation.py`. The committed evaluation is designed
> to expose misses and failed controls rather than optimize a single headline
> score.

Use it four ways without adopting a backtesting framework:

- `nofuture scan` in CI/pre-commit for Python and Jupyter source review;
- `audit_availability` / `as_of` for explicit point-in-time data contracts;
- `nofuture audit-manifest` for repository-level dataset availability contracts;
- prefix and future-mutation invariance checks for custom feature pipelines.

## Why this exists

A timestamp saying when an event happened is not enough for an honest historical
simulation. Revised macro data, delayed feeds, edited messages, restated
fundamentals, finalized labels, and post-close files can all exist in today's
dataset even though they were unavailable at the historical decision time.

NoFutureData uses three deliberately separate concepts:

- `event_time`: when the described event happened or is scheduled to happen.
- `known_at`: when the record was first observed or published to the consumer.
- `eligible_from`: the earliest time the record is allowed to affect a decision
  after validation, normalization, latency, or policy constraints.

It does **not** assume `event_time <= known_at`. A future calendar event can be
known today. The causal requirement is that the row is available before the
decision that consumes it.

## Install

The `main` branch currently targets **0.5.0.dev0**. The latest tagged stable
release is **v0.4.0**, so the release-wheel and Action examples below intentionally
remain pinned to v0.4.0 until the next release is cut.

Install the signed-off release wheel directly from GitHub:

```bash
python -m pip install https://github.com/ORANGINGS/nofuturedata/releases/download/v0.4.0/nofuturedata-0.4.0-py3-none-any.whl
```

The release also includes `SHA256SUMS.txt`. For editable development from a
checkout:

```bash
python -m pip install -e .
```

The package requires Python 3.10+. The core has no runtime dependency outside
the standard library. For the pandas join helper, install pandas 2.1+ alongside
the release wheel, or use `python -m pip install -e ".[pandas]"` from a checkout.

PyPI publishing is prepared through GitHub OIDC Trusted Publishing. It will be
enabled after the one-time PyPI project/publisher binding is completed; until
then the GitHub release wheel above is the canonical install artifact.

## 1. Audit timestamp causality

```python
from nofuturedata import audit_availability

rows = [
    {
        "event_time": "2026-09-20T12:00:00+00:00",
        "known_at": "2026-09-16T09:00:00+00:00",
        "eligible_from": "2026-09-16T09:01:00+00:00",
        "decision_time": "2026-09-16T09:00:30+00:00",
    }
]

report = audit_availability(rows, decision_time="decision_time")
assert not report.ok
print(report.to_dict())
```

The row fails because `eligible_from` is later than the historical decision.

CSV works from the CLI:

```bash
nofuture audit-csv features.csv --decision-time decision_time
```

Naive timestamps without a timezone fail closed.

## 2. Query data "as known then"

```python
from nofuturedata import as_of

visible = as_of(records, "2026-09-16T09:30:00+00:00")
```

`eligible_from` is used first, with `known_at` as the fallback. If neither is
present, the query raises instead of silently treating today's data as
historically available.

## 3. Point-in-time join revised data with pandas

```python
from nofuturedata import point_in_time_join

joined = point_in_time_join(
    decisions,
    vintages,
    decision_time="decision_time",
    by=["series", "event_time"],
)
```

The helper always uses backward/as-of semantics: a vintage cannot match a
decision made before that vintage's `eligible_from` (or `known_at` fallback).
All timestamps must carry a timezone. Duplicate right rows with the same `by`
keys and availability timestamp fail closed instead of letting dataframe row
order silently choose a revision.

## 4. Enforce dataset temporal contracts in CI

Commit a small JSON manifest next to the data contract:

```json
{
  "schema_version": 1,
  "datasets": [
    {
      "path": "data/vintages.csv",
      "format": "csv",
      "event_time": {
        "column": "event_time",
        "semantics": "observation_period"
      },
      "known_at": {
        "column": "known_at",
        "semantics": "first_observed_by_consumer"
      },
      "eligible_from": {
        "policy": "explicit_column",
        "column": "eligible_from"
      },
      "timezone": "offset-aware",
      "revision": {
        "policy": "append_only_vintages",
        "key": ["series_id", "event_time"]
      },
      "null_reason": {
        "policy": "required_when_value_missing",
        "column": "null_reason",
        "value_columns": ["value"]
      }
    }
  ]
}
```

Then validate the referenced data:

```bash
nofuture audit-manifest temporal-contract.json
```

The validator requires explicit event-time and known-at semantics, an
eligible-from policy, offset-aware timestamps, a revision policy, and a null
reason policy. It also checks required columns, optional decision-time
causality, ambiguous revision timestamps, and missing-value explanations.
Dataset paths are relative to the manifest, making the contract portable in CI.
See the [manifest reference](docs/MANIFEST.md) and the portable
[JSON Schema](schemas/temporal-contract.schema.json) for the full format.

## 5. Scan Python and Jupyter source

```bash
nofuture scan src/
```

Multiple paths are accepted, so the same command works naturally with
pre-commit's filename passing:

```bash
nofuture scan src tests notebooks
```

Missing paths and an entirely empty scan fail closed instead of returning a
misleading PASS.

Python code cells inside `.ipynb` files are scanned too. Findings report the
notebook cell number; markdown and non-Python notebooks are ignored.

Current static rules flag:

- negative `shift(...)`, such as `shift(-1)`;
- `bfill()` / `backfill()`;
- centered rolling windows;
- `merge_asof(..., direction="forward"|"nearest")`;
- negative `diff(...)` / `pct_change(...)` periods;
- `fillna(method="bfill"|"backfill")`;
- backward or bidirectional interpolation;
- same-dataframe whole-series feature aggregates;
- negative absolute `.iloc[-N]` indexing;
- fixed/day resample aggregations labeled at the left interval edge.

Some risks are only meaningful once the data semantics are known. Opt into
time-series evaluation context when scanning forecasting/backtest evaluation
code:

```bash
nofuture scan src --time-series
```

This enables `SRC011` for generic/random cross-validation patterns such as
`KFold`, `ShuffleSplit`, shuffled `train_test_split`, and scikit-learn
evaluation/search helpers whose `cv` is omitted, `None`, or a literal integer.
The same syntax remains clean in the default scanner because it can be valid for
IID data. Explicit `TimeSeriesSplit`, `train_test_split(..., shuffle=False)`, and
unresolved dynamic `cv=cv` expressions remain clean in this mode.

These are review gates, not proofs of a bug. Some pipelines use these operations
legitimately when building labels. The point is to force the temporal assumption
to be explicit.

When a future-looking operation is intentional, suppress the exact rule on that
line so reviewers can see the exception in source control:

```python
label = price.shift(-1) > price  # nofuture: ignore[SRC001]
```

`# nofuture: ignore` suppresses all NoFutureData findings on that line. Prefer
the rule-specific form when possible.

Example:

```text
FAIL: 1 finding(s), 5 row/line(s) scanned
[SRC001] negative shift can read future rows (line 5)
```

For GitHub Code Scanning or another SARIF consumer:

```bash
nofuture scan src notebooks --sarif nofuturedata.sarif
```

## 6. Test the pipeline, not only the syntax

Static scanning cannot catch arbitrary code. Runtime invariance checks can.

```python
from nofuturedata import prefix_invariance, future_mutation_invariance

def cumulative(rows):
    total = 0
    out = []
    for row in rows:
        total += row["x"]
        out.append(total)
    return out

rows = [{"x": n} for n in range(1, 100)]

assert prefix_invariance(cumulative, rows).ok
assert future_mutation_invariance(cumulative, rows).ok
```

`prefix_invariance` recomputes on historical prefixes and compares them with the
same prefix from the full run. `future_mutation_invariance` changes only future
numeric values and verifies that already-produced output remains identical.

This catches classes of leakage that simple source scanning misses.

For constrained inputs, pass both a domain-preserving `mutator` and an
`input_validator`. The mutation check rejects an intervention if it changes the
historical prefix, changes row count, or violates the declared input contract,
instead of treating an invalid counterfactual as evidence of leakage.

```python
report = future_mutation_invariance(
    transform,
    rows,
    mutator=bounded_future_mutator,
    input_validator=valid_probability_rows,
)
```

The committed mutation-validity benchmark applies the same contract to bounded
probabilities, OHLC candles, simplex-normalized vectors, and monotonic cumulative
counters. Each domain has a negative control that must reject an invalid
counterfactual before transform behavior can be interpreted as leakage evidence.
Current mutation-validity result: **13/13 checks passing**.

## Public planted-leak corpus

The repository includes a deterministic corpus of intentionally leaking and safe
controls. It exercises every shipped semantic static rule (`SRC001+`) and is
executed on every CI run:

```bash
python benchmarks/run_benchmark.py
```

The current corpus contains 31 independently checked cases: 18 planted leaks and
13 safe controls. It now includes opt-in time-series cases for `SRC011` and
`SRC012` alongside their chronological/causal controls. A case passes only when
the emitted rule IDs exactly equal its
declared expectation. The benchmark also reports finding-level precision,
recall/F1, leak-case detection rate, safe-case specificity, and per-rule coverage.
These are conformance metrics on a planted corpus, not estimates of recall on
arbitrary real-world temporal leakage.

Run the full research evaluation (static conformance, method ablation,
downstream metric inflation, intervention validity and sensitivity, real-pandas
behavioral transfer, revision/vintage robustness, and external reproductions)
with one command:

```bash
python -m pip install -e ".[pandas,dev]"
python benchmarks/run_evaluation.py
```

The research suite installs the optional pandas extra because the generative
revision/vintage experiments exercise the real `point_in_time_join` helper. The
developer extra also pins Hypothesis for property-based counterexample search;
the core package itself remains dependency-free.

Use `--json` for a single machine-readable report suitable for CI artifacts or
independent review. A suite PASS means the reviewed benchmark contracts still
reproduce; it does not mean the external scanner has perfect recall.

CI also runs `python benchmarks/check_documented_metrics.py`. That check derives
headline numbers from the live evaluator and fails when reviewer-facing README,
research, evaluation, or landing-page metrics drift from those results.
The Python 3.12 CI job also uploads the full `run_evaluation.py --json` output as
a machine-readable workflow artifact for independent review.

The source distribution carries the benchmark suite, reviewer-facing research
docs, schemas, examples, and fixtures. CI extracts the built sdist and reruns
this same evaluation and documentation-metric gate from the packaged source tree
before the wheel smoke test.

### Research question and falsification

The project asks whether a small repository-local guard can make temporal
causality assumptions testable without requiring a feature store, backtesting
engine, or ML framework. The evaluation is intentionally split by evidence
strength:

1. **Static conformance:** every shipped rule needs a planted leak and a safe
   counter-example, and the emitted rule IDs must match exactly.
2. **Behavioral causality:** prefix and future-mutation checks test whether past
   outputs actually change when only future inputs are removed or perturbed.
3. **Data availability:** manifest and point-in-time checks test whether each
   record was known and eligible before the decision that consumed it.

The project treats counter-examples as first-class evidence. A real-world leak
that passes the current checks becomes a false-negative reproduction to preserve
before extending a rule. A legitimate pipeline that is flagged becomes a
false-positive reproduction and should narrow or remove the rule. Adoption data
and externally contributed reproductions are required before making claims about
real-world recall.

### Method ablation: static vs behavioral checks

The repository also includes a deterministic method-comparison experiment:

```bash
python benchmarks/method_comparison.py
```

Its six cases include explicit pandas lookahead patterns, indirect future
dependencies that are intentionally outside the AST rule set, and safe controls.
On this ablation corpus, the static rules detect 2/4 leak cases with no safe-case
false positives, while the union of prefix and future-mutation invariance detects
4/4 leak cases and both safe controls remain clean. The combined method therefore
also detects 4/4. This is evidence of complementarity, not an estimate of
real-world recall: static analysis can review code without executing it, while
behavioral checks require a runnable transform and representative input rows.

### Downstream metric inflation demonstration

The repository includes a fixed-seed synthetic forecasting experiment that asks
what the leak can do to an otherwise ordinary chronological holdout:

```bash
python benchmarks/downstream_metric_inflation.py
```

The same OLS model and 1,600/800 train/test split are evaluated twice. The causal
model uses only lag/current observations; the leaking model adds the next
observation as an unavailable feature. Synthetic downstream impact: causal
chronological holdout **R² 0.630** vs leaked **0.991** (Δ **+0.361**), with the
leaked RMSE falling to **0.158×** the causal RMSE. The safe lag source stays clean
and the future shift emits `SRC001`.

This experiment demonstrates a mechanism by which temporal leakage can make an
offline result look dramatically stronger. It is a fixed synthetic example, not
an estimate of real-world metric inflation or expected model performance.

### Revision/vintage generative robustness

The manifest contract also has a fixed-seed generative benchmark:

```bash
python benchmarks/revision_vintage_robustness.py
```

It generates 24 different append-only vintage histories with explicit positive
eligibility delays. Each trial checks manifest acceptance in original and
shuffled row order, duplicate-availability rejection, pre-eligibility selection,
and post-eligibility latest-vintage selection after the right-side rows are
shuffled. The current deterministic result is **120/120 checks passing**. This is
reproducible generative coverage of the revision contract, not a claim that every
possible vintage history has been exhausted.

### Property-based revision/vintage search

The same five core invariants plus seven multi-column/null edge invariants are
also searched with Hypothesis rather than a fixed sample:

```bash
python benchmarks/property_revision_vintage.py
```

Hypothesis varies series count, observation count, vintage count, eligibility
delay, row permutation, duplicate insertion position, 2–4 segment multi-column
revision keys, null-value reasons, and missing-key injections, and shrinks a
failing case to a smaller counterexample. Hypothesis property result: **768/768 invariant evaluations pass** across 64 generated examples. This broadens the search space
without turning a finite property test into a proof over arbitrary histories.

### Intervention sensitivity

The domain-valid mutation conclusions are also stressed across a fixed grid:

```bash
python benchmarks/intervention_sensitivity.py
```

The current result is **48/48 checks passing** across four input domains, three
historical cut points, and two valid mutation strengths. Every grid point must
keep the causal transform clean and detect the planted future dependency; the
benchmark does not tune or select a favorable intervention after seeing results.

### Behavioral transfer on real pandas operations

The behavioral checks are also exercised against executable pandas operations,
instead of only hand-written transforms that mimic the same causal shape:

```bash
python benchmarks/behavioral_generalization.py
```

Real-pandas behavioral transfer: **18/18 cases match**; runtime checks detect 9/9 leaks and keep 9/9 safe controls clean.
The original trailing rolling, expanding, and exponentially weighted controls
remain clean while centered rolling, backward fill, and full-series centering
remain detected. The expanded set adds interleaved panel rows and irregular
timestamps: grouped expanding/EWM and irregular forward fill stay causal, while
group-wide mean, grouped backward fill, and time interpolation are detected.
It now also pairs backward/forward `merge_asof`, right-closed/right-labeled vs
left-labeled 15-minute resampling, and two-column historical vs future `diff`
pipelines. The grouped/irregular mutation contract changes only future `x`
values while preserving timestamp order and group identity; the new multi-column
contract mutates both future numeric features while preserving row identity and
time order. This is a transfer check over 18 executable pandas operations, not a
claim of perfect behavioral recall on arbitrary pipelines.

### External reproductions and context-dependent rules

`benchmarks/external_reproductions.json` keeps a second corpus derived from
public documentation rather than examples invented for this project. It includes
Freqtrade's documented negative-shift, whole-dataframe aggregation, absolute
`iloc`, resampling, and safe trailing-window patterns; pandas forward/backward
fill semantics; scikit-learn's time-series cross-validation guidance; Polars,
Xarray, and Dask shift semantics; and NumPy circular roll semantics. Each
entry records its source URL and the detector behavior reviewed for the current
version.

```bash
python benchmarks/run_external_reproductions.py
```

On this small documentation-backed corpus the source-only scanner detects 8 of 17
documented leak cases and keeps all 13 safe controls clean. With declared
time-series context it detects 17 of 17. `SRC010` covers the narrow fixed/day
resampling case when an aggregate is labeled at the left interval edge, and the
existing negative-shift rule transfers to both Polars and Dask. Two source-only
scikit-learn single-level CV misses and the nested `GridSearchCV` +
`cross_val_score` reproduction become conditional `SRC011` detections under
explicit time-series context. `GroupKFold` and `GroupShuffleSplit` are also
context-gated for panel forecasting because grouping alone does not impose
chronological train-before-test order. The same opt-in rule now covers
`learning_curve`, `validation_curve`, and `permutation_test_score` when they use
default/integer CV; paired explicit `TimeSeriesSplit` controls remain clean. The
nested control uses explicit `TimeSeriesSplit` at both levels and remains clean.
The existing negative-shift rule also transfers to Xarray when a negative offset
is attached to an explicitly temporal dimension such as `shift(time=-1)`; the
paired `shift(time=1)` and non-temporal `axis=-1` controls remain clean.
NumPy `np.roll(values, -1)` is now covered by the opt-in `SRC012` rule only when
time-series context is declared. The default source-only scan still leaves it
clean because circular roll is not inherently temporal, while the paired
positive-roll lag control remains clean under temporal context. This change was
made against the previously published miss and paired control rather than by
broadening every `.roll(...)` call. These curated, non-random rates are not
estimates of real-world recall or specificity.

## GitHub Action

Downstream projects can put a source scan in CI:

```yaml
name: temporal-leakage
on: [push, pull_request]

jobs:
  nofuture:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: ORANGINGS/nofuturedata@v0.4.0
        with:
          path: src
```

The unreleased `0.5.0.dev0` source adds an optional `time-series: "true"`
Action input matching the CLI `--time-series` context. Keep public workflows on
the tagged v0.4.0 interface until a 0.5 release is cut; reviewers testing this
checkout can exercise the new input with the repository-local `uses: ./` Action.

To publish findings in GitHub Code Scanning, grant `security-events: write` and
turn on SARIF upload:

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v7
  - uses: ORANGINGS/nofuturedata@v0.4.0
    with:
      path: .
      sarif: nofuturedata.sarif
      upload-sarif: "true"
```

## Pre-commit

```yaml
repos:
  - repo: https://github.com/ORANGINGS/nofuturedata
    rev: v0.4.0
    hooks:
      - id: nofuturedata
```

Then run `pre-commit run --all-files`. The hook receives changed `.py` and
`.ipynb` files directly and fails closed when it finds a temporal leakage gate.

## What NoFutureData is not

It is not a backtesting engine and does not decide whether a model is good. It
checks a narrower prerequisite: whether the historical information boundary is
internally consistent.

It also does not claim that passing these checks proves absence of all leakage.
Data revisions, survivorship bias, target construction, cross-validation, and
provider-specific publication semantics still need domain-specific review.

## Design principles

1. **Availability is data.** Preserve when information became usable, not only
   the event timestamp.
2. **Fail closed.** Missing causal timestamps are an error when the pipeline
   claims point-in-time safety.
3. **Mutation beats naming.** A column named `holdout` proves little; changing
   future data and observing whether history changes is stronger evidence.
4. **Small auditable rules.** Static checks explain exactly what pattern caused
   the finding.
5. **Provider-agnostic core.** Finance is one use case; the same problem appears
   in forecasting, recommender systems, operations, experimentation, and ML.

## Documentation

- [Why this matters](docs/WHY.md) — evidence for temporal leakage as a
  cross-domain reproducibility and engineering problem, plus the scope of this tool.
- [Research brief](docs/RESEARCH_BRIEF.md) — research question, contribution,
  current evidence, negative result, and next falsifiable experiments.
- [Evaluation and falsification](docs/EVALUATION.md) — reproducible benchmark
  results, method ablation, external reproductions, context-dependent rules,
  and claim limits.
- [Rule reference](docs/RULES.md) — stable rule IDs, rationale, suppressions,
  and runtime invariance semantics.
- [Temporal contract manifests](docs/MANIFEST.md) — repository-level dataset
  availability and revision contracts.
- [PyPI publishing](docs/PYPI_PUBLISHING.md) — tokenless OIDC release workflow
  and the one-time Trusted Publisher setup.
- [Roadmap](ROADMAP.md) — next candidate capabilities and adoption evidence.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Synthetic minimal reproductions are
preferred. New static rules need both a leaking example and a safe
counter-example.

## License

MIT.
