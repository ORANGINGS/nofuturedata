---
layout: default
title: Research brief
permalink: /RESEARCH_BRIEF.html
---

# Research brief

Date: 2026-09-17 (Asia/Taipei)
Research update: GPT-5.6 Sol (`gpt-5.6-sol`)
Project state: `0.5.0.dev0`

## Research question

Can a small, repository-local tool make temporal causality assumptions testable
in ordinary Python/Jupyter projects without requiring a feature store,
backtesting engine, or ML framework?

Temporal leakage is a difficult failure mode because it often improves offline
metrics. A pipeline can therefore look more convincing as its historical
validity gets worse. NoFutureData treats the historical information boundary as
an executable contract instead of an informal convention.

## Contribution

The project combines three complementary evidence layers behind one local API
and CLI:

1. **Static review gates** detect explicit future-looking source patterns and
   support narrow, source-controlled suppressions.
2. **Behavioral invariance checks** remove or mutate future inputs and test
   whether already-produced historical outputs change.
3. **Availability contracts** distinguish event time, first-known time, and
   eligibility time, then enforce those semantics in point-in-time joins and
   dataset manifests.

The design goal is not universal leak detection. It is to make a minimum causal
boundary cheap, inspectable, and repeatable enough to run on every pull request.

## Evidence

Run the complete evaluation with:

```bash
python -m pip install -e ".[pandas,dev]"
python benchmarks/run_evaluation.py
```

Current deterministic evidence:

| Evaluation | Result | What it supports |
| --- | ---: | --- |
| Static conformance corpus | **31/31 exact match** | all 12 shipped semantic `SRC001+` rules, including contextual rules, have exact cases and paired safe controls where applicable |
| Jupyter fixture corpus | **24/24 cases; 12/12 rule pairs** | every semantic source rule has one tiny leaking notebook and one safe notebook; exact rule IDs and cell numbers are checked in CI |
| Static method ablation | **0.500 recall** | syntax rules intentionally miss indirect future dependencies |
| Runtime-union ablation | **1.000 recall** | behavioral checks catch the two indirect leaks in this six-case ablation |
| Synthetic downstream impact | **R² 0.630 → 0.991 (+0.361)** | same OLS model and chronological split; adding one unavailable future feature inflates the fixed-seed holdout while `SRC001` flags the source pattern |
| Mutation intervention validity | **13/13 checks pass** | malformed counterfactuals are rejected across bounded-probability, OHLC, normalized-vector, and cumulative contracts; domain-valid mutations preserve safe controls and detect planted leaks |
| Intervention sensitivity | **48/48 checks pass** | safe/leak conclusions remain stable across four domains, three cut points, and two valid mutation strengths |
| Real-pandas behavioral transfer | **18/18 cases match** | 9/9 leaks detected and 9/9 causal controls clean across ordinary, grouped/stateful, irregular missing-data, as-of alignment, resampling-boundary, and multi-column stateful pandas transforms with explicit future-mutation contracts |
| Revision/vintage robustness | **120/120 checks pass** | 24 generated histories preserve explicit eligibility delays, select the correct latest eligible vintage under row permutation, and consistently reject an injected duplicate `known_at` with `REV001` |
| Revision/vintage property search | **768/768 invariant evaluations pass** | 64 Hypothesis examples search and shrink counterexamples across 12 invariants spanning the fixed-seed core plus multi-column keys, `REV002`, null reasons, and null-to-value revisions |
| External documented leaks | **8/17 detected** | source-only scanner behavior on curated reproductions spanning Freqtrade, pandas, scikit-learn, Polars, Xarray, NumPy, and Dask |
| External + declared temporal context | **17/17 detected** | opt-in context recovers the scikit-learn CV helpers and the narrow NumPy negative-roll reproduction while paired controls remain clean |
| External safe controls | **13/13 clean** | no findings on the curated safe controls |

These figures describe their named deterministic corpora only. They are not
population-level estimates of real-world recall, precision, or prevalence.

## Context-dependent boundaries kept explicit

The resampling experiment produced a narrow source-only condition: fixed/day
resample aggregations are gated when they use the left interval label, while
right-labeled, right-default calendar frequencies and dynamic frequencies stay
outside the rule.

The generic scanner still leaves random `KFold`, `cross_val_score(..., cv=5)`,
and nested integer-CV `GridSearchCV` + `cross_val_score` clean because the same
source can be legitimate for IID data. An explicit `time_series` context turns
those calls into conditional detections (`SRC011`) while explicit
`TimeSeriesSplit` controls stay clean at both nested levels. The same declared
context now gates `GroupKFold` and `GroupShuffleSplit` for panel forecasting;
group separation by itself is not treated as chronological evaluation.
The same contract now covers `learning_curve`, `validation_curve`, and
`permutation_test_score` when their `cv` is omitted, `None`, or an integer;
explicit `TimeSeriesSplit` controls for all three remain clean.
The external transfer set now also includes Xarray: `shift(time=-1)` is detected
by a narrow temporal-dimension extension of `SRC001`, while `shift(time=1)` and
non-temporal negative-keyword controls remain clean.
The same external corpus previously preserved `np.roll(values, -1)` as a known
miss even under time-series context. NumPy's documented circular shift semantics
made the temporal risk concrete; the miss is now closed by `SRC012`, which only
recognizes `np`/`numpy` attribute calls with a literal negative shift after the
caller declares time-series context. The paired positive-roll lag control stays
clean. The change demonstrates the intended falsification loop: a miss remains
public until a conservative rule and paired controls justify changing it.

## Worked falsification loop: NumPy `roll`

The latest rule addition is kept as a small worked example of the research
process rather than only as a higher benchmark number.

| Stage | Reviewable evidence |
| --- | --- |
| Observation | The documentation-backed corpus exposed `np.roll(values, -1)` as the only remaining context-assisted miss: 16/17 documented leak cases detected. |
| Hypothesis | In explicitly time-ordered data, a literal negative NumPy roll is future-dependent, but the same syntax is not inherently temporal outside a declared time-series context. |
| Conservative intervention | Add `SRC012` only for `np.roll` / `numpy.roll` attribute calls with a literal negative shift when `temporal_context="time_series"` is enabled. |
| Falsification controls | Default source-only scan must stay clean; a masked positive-roll lag and an unrelated `custom.roll(..., -1)` must stay clean under temporal context. |
| Acceptance result | Unit tests pass; static conformance is 31/31 with 12/12 semantic-rule coverage; external context-assisted detection becomes 17/17 while source-only detection remains 8/17 and all 13 external safe controls remain clean. |
| Remaining boundary | Imported aliases, dynamic shift expressions, and arbitrary roll-like APIs remain unresolved instead of being guessed by the static scanner. |

This is intentionally a narrow result. The 17/17 figure describes the committed
curated corpus, not arbitrary NumPy or real-world pipeline recall.

## Engineering and reproducibility

- zero mandatory runtime dependencies for the core;
- optional pandas point-in-time join helper;
- Python/Jupyter source scanning, SARIF, pre-commit, and GitHub Action support;
- fail-closed behavior for missing scan paths and ambiguous temporal contracts;
- deterministic benchmark corpora committed with the source;
- Hypothesis property search in the developer-only evaluation environment;
- CI across Python 3.10, 3.12, and 3.13;
- isolated wheel build/install smoke test in CI;
- source-distribution reproducibility gate that extracts the built sdist and
  reruns the unified evaluation from the packaged benchmark and documentation set;
- package/runtime version consistency check;
- public rule IDs and explicit claim limits.

## Next falsifiable experiments

1. **Temporal-context breadth:** nested, grouped/panel, and the current
   metadata-routing-capable CV helpers are covered; next test custom/predefined
   splitters and additional ecosystem CV routers before expanding `SRC011`.
2. **External validity:** the corpus now spans seven independent projects; keep
   adding minimal reproductions from independent ML, forecasting, and
   scientific-computing projects before making broader recall claims.
3. **Behavioral generalization:** index alignment, resampling boundaries, and
   multi-column stateful pandas pipelines are now covered; next test duplicated
   timestamps, session-aware resampling boundaries, and chained align/resample/
   missing-data pipelines with the same explicit input-contract discipline.
4. **Revision/vintage robustness:** extend beyond the new multi-column/null
   coverage to mixed key dtypes and broader availability-policy interactions,
   while preserving exact fixed-seed failure reproduction.

Each experiment has a failure condition that can be committed as a regression
case. Improving a headline score is not sufficient if a change weakens safe
controls or makes the rule harder to explain.

## Reviewer path

For a short review, install the checkout with
`python -m pip install -e ".[pandas,dev]"`, then use the smallest command that
tests the claim you care about:

| Question | Command |
| --- | --- |
| Does the newest falsification loop reproduce? | `python -m pytest -q tests/test_audit.py -k numpy_roll` |
| Do all semantic source rules have exact conformance cases? | `python benchmarks/run_benchmark.py` |
| Do notebook findings preserve exact rule IDs and cell locations? | `python benchmarks/run_notebook_corpus.py` |
| Do documentation-backed reproductions match the reviewed baseline? | `python benchmarks/run_external_reproductions.py` |
| Does the whole research contract reproduce? | `python benchmarks/run_evaluation.py` |
| Do reviewer-facing metrics still match executable results? | `python benchmarks/check_documented_metrics.py` |

For design rationale and adjacent tools, see
[Why temporal leakage deserves a CI guard](WHY.html). For exact detector
semantics, see the [Rule reference](RULES.html).
