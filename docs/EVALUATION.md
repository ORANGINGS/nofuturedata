---
layout: default
title: Evaluation and falsification
permalink: /EVALUATION.html
---

# Evaluation and falsification

Date: 2026-09-17 (Asia/Taipei)
Evaluation update: GPT-5.6 Sol (`gpt-5.6-sol`)

NoFutureData asks a narrow research question: **can a small repository-local
guard make temporal causality assumptions testable without requiring a feature
store, backtesting engine, or ML framework?**

The project does not treat a single benchmark score as proof. It separates three
forms of evidence because they fail in different ways.

| Evidence layer | What it tests | Main failure mode |
| --- | --- | --- |
| Static source rules | Known future-looking source patterns | Misses arbitrary indirect dependencies and can be context-sensitive |
| Behavioral invariance | Whether past outputs change after future rows are removed or mutated | Requires an executable transform and representative inputs |
| Availability contracts | Whether a record was known and eligible before a historical decision | Depends on correct provider/publication semantics |

## Current reproducible results

### 1. Static conformance corpus

`benchmarks/corpus.json` contains 31 deterministic cases: 18 planted leaks and
13 safe controls. Every shipped semantic static rule (`SRC001+`), including the
opt-in contextual rules, has a leaking case and a safe counter-example where
applicable. `SRC000` is the parse/configuration failure sentinel and is tested
separately rather than treated as a leakage pattern.

Current result:

- exact case match: **31/31**
- finding precision: **1.000**
- finding recall: **1.000**
- safe-case specificity: **1.000**

These are conformance metrics on a corpus designed around the shipped rules.
They are not estimates of real-world scanner recall.

### 2. Jupyter notebook fixture corpus

`notebooks/fixtures/` contains 24 minimal notebooks: exactly one planted leak and
one paired safe control for each of the 12 shipped semantic `SRC001+` rules. The
fixtures are generated deterministically from `notebooks/fixtures/manifest.json`
and validated by `benchmarks/run_notebook_corpus.py`.

Current notebook result: **24/24 cases pass across 12/12 paired semantic rules**.
For every leaking notebook, CI checks the exact rule ID and notebook cell number;
for every safe notebook it requires zero findings. The runner also verifies that
the checked-in notebook JSON still matches the manifest source, that finding
metadata points back to the correct notebook path, and that the contextual
`SRC011`/`SRC012` leak examples remain clean without declared time-series context.

The notebook corpus is a deterministic interface/conformance test. It does not
measure how often temporal leakage occurs in arbitrary notebooks or estimate
real-world scanner recall.

### 3. Static vs behavioral method ablation

`benchmarks/method_comparison.py` contains six cases: four leaks and two safe
controls. Two leaks use explicit source patterns known by the AST scanner; two
use indirect future dependencies that intentionally sit outside its rule set.

| Method | Precision | Recall | Specificity | F1 |
| --- | ---: | ---: | ---: | ---: |
| Static rules | 1.000 | 0.500 | 1.000 | 0.667 |
| Prefix invariance | 1.000 | 1.000 | 1.000 | 1.000 |
| Future-mutation invariance | 1.000 | 1.000 | 1.000 | 1.000 |
| Runtime union | 1.000 | 1.000 | 1.000 | 1.000 |
| Static + runtime | 1.000 | 1.000 | 1.000 | 1.000 |

This experiment is designed to expose method boundaries. It demonstrates that
the behavioral tests catch indirect future dependence that the current static
rules do not. It does not imply that behavioral testing has perfect recall on
arbitrary real pipelines.

### 4. Synthetic downstream metric inflation

`benchmarks/downstream_metric_inflation.py` connects the source-level problem to
a model-level consequence. A fixed-seed AR(1) process produces 2,400 forecasting
rows. Both models use the same ordinary least-squares implementation and the same
chronological 1,600/800 train/test split. The causal model sees lag/current
observations; the leaking model receives one additional feature: the next latent
observation, which is unavailable at the forecast time.

| Model | Holdout R² | Holdout RMSE |
| --- | ---: | ---: |
| Causal lag/current features | **0.630** | **0.962** |
| Adds unavailable future feature | **0.991** | **0.152** |

The R² inflation is **+0.361** and the leaked RMSE is **0.158×** the causal
RMSE. All **7/7 acceptance checks pass**: the split is non-empty, the causal
model stays non-trivial, the leaked model becomes near-perfect, the performance
gap is material, the safe lag source remains clean, and the future-shift source
emits `SRC001`.

This is a synthetic mechanism demonstration, not an estimate of how much
leakage improves metrics in real projects. Its purpose is to make the practical
failure mode reviewable while keeping the causal claim deliberately narrow.

### 5. Mutation intervention validity

`benchmarks/mutation_validity.py` tests four materially different input
contracts: bounded probabilities, valid OHLC candles, simplex-normalized
vectors, and monotonic cumulative counters. For probabilities, the
generic numeric mutator intentionally leaves the valid domain, so the experiment
must reject that intervention rather than interpret the resulting behavior as
leakage. For OHLC, a deliberately invalid mutator makes `close > high` and must
also be rejected. For normalized vectors, a deliberately invalid mutation breaks
the non-negative unit-sum contract and must be rejected. For cumulative counters,
a future value that drops below its historical predecessor must be rejected.
Domain-preserving mutators are then used on paired causal and leaking transforms
in all four domains.

Current result: **13/13 checks pass**.

- out-of-domain default mutation is rejected;
- a mutator that edits the historical prefix is rejected;
- the probability-domain safe transform stays clean;
- the same valid probability intervention detects the planted future dependency;
- an OHLC mutation that violates candle ordering is rejected;
- the OHLC-domain safe transform stays clean;
- the same valid OHLC intervention detects the planted future dependency.
- a normalized-vector mutation that violates the simplex constraint is rejected;
- the normalized-vector safe transform stays clean;
- the same valid vector intervention detects the planted future dependency.
- a cumulative-counter mutation that violates monotonicity is rejected;
- the cumulative-domain safe transform stays clean;
- the same valid cumulative intervention detects the planted future dependency.

These four input domains are not proof that the default intervention is valid
for arbitrary schemas. They establish an executable contract for testing
domain-aware counterfactuals without interpreting malformed interventions as
leakage evidence.

### 6. Intervention sensitivity

`benchmarks/intervention_sensitivity.py` asks whether the causal/leaking
conclusions survive more than one hand-picked counterfactual. It evaluates all
four intervention domains at three historical cut points and two valid mutation
strengths. Each scenario contributes two checks: the causal control must remain
clean and the planted future dependency must still be detected.

Current result: **48/48 checks pass**.

- 4 domain contracts;
- 3 cut points (`1`, `2`, `3`);
- 2 domain-preserving mutation strengths (`0.25`, `0.50`);
- paired safe/leak conclusions at every grid point.

The grid is intentionally fixed and reviewable. A failure at any valid cut point
or mutation strength is evidence against the current behavioral claim; the
benchmark does not select or report only the best-performing intervention.

### 7. Real-pandas behavioral transfer

`benchmarks/behavioral_generalization.py` removes one simplifying assumption
from the method ablation: its transforms call pandas directly instead of using
hand-written equivalents. It now covers ordinary trailing transforms,
interleaved grouped/stateful transforms, and irregular timestamp/missing-data
pipelines plus index alignment, resampling boundaries, and multi-column
stateful pipelines with paired causal and future-dependent cases.

Behavioral-transfer result: **18/18 executable pandas cases match the declared causal labels**.

- runtime union detects 9/9 future-dependent transforms;
- 9/9 causal controls remain clean;
- grouped expanding/EWM and irregular forward fill remain clean;
- group-wide mean, grouped backward fill, and time interpolation are detected;
- backward `merge_asof`, right-closed/right-labeled resampling, and a two-column
  historical-difference pipeline remain clean, while their forward-asof,
  left-labeled-resample, and future-difference counterparts are detected;
- grouped/irregular future mutations preserve timestamp order and group identity
  and alter only future numeric `x` values;
- multi-column future mutations preserve timestamp order and row count while
  changing both future numeric feature columns;
- prefix invariance and future-mutation invariance each detect all nine leak
  cases in this corpus;
- pandas is an optional research/evaluation dependency rather than a new core
  runtime dependency.

This transfer result reduces dependence on benchmark-authored surrogate
implementations, but the 18 operations are still curated and finite. It does
not establish recall over arbitrary pandas pipelines or other dataframe systems.

### 8. Revision/vintage generative robustness

`benchmarks/revision_vintage_robustness.py` uses fixed seed `20260916` to
generate 24 different append-only vintage histories with explicit positive
eligibility delays. Each generated history is checked five ways: unique vintages
in their original order must pass, the same rows in a shuffled order must still
pass, one injected duplicate `known_at` for the same logical observation must
emit `REV001`, a decision between `known_at` and `eligible_from` must not expose
that vintage early, and a decision just after eligibility must select the latest
eligible vintage identically even when right-side rows are shuffled.

Current result: **120/120 checks pass across 24 generated trials**.

- 24/24 ordered unique-vintage histories are accepted;
- 24/24 shuffled versions are accepted;
- 24/24 injected duplicate revision availability times are detected;
- 24/24 eligibility-delay selections hide the not-yet-eligible vintage;
- 24/24 shuffled revision selections return the correct latest eligible vintage.

The fixed seed makes failures exactly reproducible while varying series count,
observation count, vintage count, values, eligibility delays, timestamps, and
row order. This is a deterministic generative sample, not a formal proof over all
revision histories.

### 9. Property-based revision/vintage search

`benchmarks/property_revision_vintage.py` lifts the five fixed-seed invariants
plus seven multi-column/null edge invariants into Hypothesis strategies. Unlike
the fixed-seed sample, Hypothesis varies the history shape, row permutation,
multi-column key partitions, and null/revision interactions while retaining
shrinking, so a failure is reduced toward a smaller reproducible counterexample.

Property-based result: **768/768 invariant evaluations pass across 64 Hypothesis examples**.

- 1–3 series per example;
- 1–3 logical observations per series;
- 1–4 vintages per logical observation;
- 1–180 minute positive eligibility delays;
- arbitrary generated right-row permutation and duplicate insertion position;
- 2–4 segment partitions sharing availability times under a three-column revision key;
- valid and invalid null reasons, missing revision-key values, and null-to-value revisions;
- left/right missing `by` keys must fail closed in the pandas point-in-time join;
- 12 invariants evaluated on every generated example.

The property strategy is deliberately bounded. It strengthens counterexample
search beyond the 24 fixed-seed histories, but it remains finite evidence rather
than a proof over all revision processes.

### 10. Documentation-backed external reproductions

`benchmarks/external_reproductions.json` preserves examples derived from public
Freqtrade, pandas, scikit-learn, Polars, Xarray, NumPy, and Dask documentation, including
source URLs, context requirements, and the reviewed current detector behavior.

Current result:

- documented leak cases: **17**
- detected by current static scanner: **8/17 (0.471)**
- detected with declared time-series context where applicable: **17/17 (1.000)**
- safe controls: **13**
- safe controls left clean: **13/13 (1.000 specificity on this corpus)**

Three earlier misses are now covered with deliberately narrow rules: `SRC008`
flags a direct whole-series aggregate only when it is assigned back to a column
on the same dataframe, `SRC009` flags negative absolute `iloc` positions, and
`SRC010` flags fixed/day resample aggregations that use the left interval label.
Nine source-only misses are intentionally kept visible and are recovered only
after the caller declares time-series semantics. scikit-learn documents that classical folds are
inappropriate for time-series evaluation, but the same
`KFold`, `cross_val_score(..., cv=5)`, or nested integer-CV search/evaluation
source can be legitimate for IID data. With the explicit
`temporal_context="time_series"` contract, `SRC011` detects both single-level
cases and both levels of the nested `GridSearchCV` + `cross_val_score`
reproduction. It also covers `GroupKFold` and `GroupShuffleSplit` in declared
panel/time-series evaluation: official scikit-learn documentation states that
GroupKFold groups appear in arbitrary fold order and that GroupShuffleSplit uses
randomized group partitions, neither of which alone establishes chronological
train-before-test ordering. The metadata-routing-capable `learning_curve`,
`validation_curve`, and `permutation_test_score` APIs are also context-gated
when `cv` is omitted, `None`, or a literal integer because their documented
default splitters are KFold/StratifiedKFold. Paired explicit `TimeSeriesSplit`
controls remain clean. NumPy's official `roll` semantics provide a separate
contextual case: `np.roll(values, -1)` moves later elements toward earlier
positions and therefore creates a future dependency on ordered data. `SRC012`
detects only the narrow `np`/`numpy` attribute-call form with a literal negative
shift under declared time-series context. Source-only scans, arbitrary `.roll`
methods, dynamic shifts, and the paired positive-roll lag control remain clean.

Xarray provides a separate transfer test for the existing shift rule. Its
`DataArray.shift` API accepts offsets keyed by dimension, so `shift(time=-1)`
moves later values toward earlier timestamps. `SRC001` recognizes only a small
set of explicitly temporal dimension names; `shift(time=1)` and a non-temporal
`shift(axis=-1)` control stay clean rather than generalizing every negative
keyword argument.

## Falsification contract

The project treats the following outcomes as evidence against its current
design, not as cases to hide:

- a documented or user-provided temporal leak passes all applicable checks;
- a legitimate causal pipeline is flagged by a static rule;
- a behavioral check changes result solely because its mutation scheme violates
  the transform's input contract;
- a domain-valid change in mutation strength or cut point makes a causal control
  dirty or causes a planted future dependency to disappear;
- a point-in-time join or availability audit admits a row whose information was
  unavailable at the decision time;
- revision acceptance changes merely because valid vintage rows are reordered,
  or a duplicate revision availability time is accepted;
- a rule extension raises planted-corpus performance while degrading external
  safe controls.

Release reproducibility is checked from the built source distribution as well
as the repository checkout: CI requires the benchmark runners, research brief,
evaluation note, schema, examples, and fixtures to survive packaging, then runs
this evaluation suite from the extracted sdist with `PYTHONPATH=src`.

Any such case should be reduced to a minimal reproduction and committed before
changing the detector. The reproduction then becomes a regression case.

## Reproduce locally

```bash
python -m pip install -e ".[pandas,dev]"
python benchmarks/run_evaluation.py
python benchmarks/run_benchmark.py
python benchmarks/method_comparison.py
python benchmarks/mutation_validity.py
python benchmarks/intervention_sensitivity.py
python benchmarks/behavioral_generalization.py
python benchmarks/revision_vintage_robustness.py
python benchmarks/property_revision_vintage.py
python benchmarks/run_external_reproductions.py
pytest
nofuture audit-manifest examples/temporal_contract.json
nofuture scan src tests examples/safe_pipeline.py benchmarks
nofuture scan path/to/time_series_project --time-series
```

The pandas extra is required by the generative revision/vintage experiments so
they can exercise the shipped `point_in_time_join` implementation. Hypothesis is
developer-only and is used for counterexample generation/shrinking; the core
package still has no mandatory third-party runtime dependency.

`run_evaluation.py --json` emits one report containing all eight evaluation
components, the package version, UTC generation time, current miss count,
context-required miss count, source-project list, and explicit claim limits. Its
exit status is based on reviewed benchmark contracts rather than requiring the
intentionally incomplete external detector to reach 100% recall.

## Developer dependency audit

Audit date: 2026-09-17 (Asia/Taipei).

- `hypothesis==6.168.0`: official PyPI project with source under
  HypothesisWorks, MPL-2.0 license, Python `>=3.10`; OSV returned no known
  vulnerabilities for this exact version during adoption review. The wheel
  exposes the expected Hypothesis CLI and pytest plugin entry points; it is kept
  in the `dev` extra only.
- `sortedcontainers==2.4.0`: Hypothesis's resolved core dependency in the
  isolated validation environment; Apache-2.0 license and no known OSV findings
  for this exact version during the same review.
- Validation was performed in an isolated venv; no paper/live runtime,
  credentials, broker configuration, or runtime cache was modified.

## External provenance

- Freqtrade strategy documentation: https://docs.freqtrade.io/en/2026.8/strategy-customization/
- Freqtrade lookahead analysis: https://docs.freqtrade.io/en/latest/lookahead-analysis/
- pandas backward-fill semantics: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.fillna.html
- pandas forward-fill semantics: https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.ffill.html
- scikit-learn data-leakage guidance: https://scikit-learn.org/1.5/common_pitfalls.html
- scikit-learn time-series cross-validation guidance: https://scikit-learn.org/dev/modules/cross_validation.html#cross-validation-of-time-series-data
- scikit-learn `GroupKFold`: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
- scikit-learn `GroupShuffleSplit`: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupShuffleSplit.html
- scikit-learn metadata routing guide: https://scikit-learn.org/stable/metadata_routing.html
- scikit-learn `learning_curve`: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.learning_curve.html
- scikit-learn `validation_curve`: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.validation_curve.html
- scikit-learn `permutation_test_score`: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.permutation_test_score.html
- scikit-learn nested cross-validation example: https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html
- Polars `Series.shift`: https://docs.pola.rs/api/python/version/1/reference/series/index.html#polars.Series.shift
- Xarray `DataArray.shift`: https://docs.xarray.dev/en/latest/generated/xarray.DataArray.shift.html
- NumPy `roll`: https://numpy.org/doc/stable/reference/generated/numpy.roll.html
- Dask `Series.shift`: https://docs.dask.org/en/stable/generated/dask.dataframe.Series.shift.html

The external corpus is curated and non-random. Its rates describe only the
checked reproductions and must not be presented as population-level recall,
precision, or prevalence estimates.
