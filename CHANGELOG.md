# Changelog

All notable changes to NoFutureData are documented here.

## 0.5.0.dev0 - Unreleased

- Add a deterministic static-vs-runtime method ablation covering explicit source
  patterns, indirect future dependencies, and safe controls; run it in CI and
  document method boundaries without claiming real-world recall.
- Add an externally sourced reproduction corpus with provenance URLs and preserve
  known misses as reviewed baseline evidence instead of overstating scanner recall.
- Add a reviewer-facing evaluation/falsification note that separates conformance,
  method ablation, and documentation-backed evidence with explicit claim limits.
- Add conservative static checks for same-dataframe whole-series aggregates
  (`SRC008`) and negative absolute `iloc` indexing (`SRC009`), covering two
  high-confidence documentation-backed reproductions while retaining paired safe
  controls.
- Add a narrow left-labeled fixed/day resample aggregation gate (`SRC010`) with
  paired right-label/calendar-frequency controls, closing the Freqtrade resample
  reproduction without treating every resample call as unsafe.
- Expand external reproductions to scikit-learn time-series cross-validation and
  preserve temporally unsafe CV syntax as explicit context-required misses; the
  corpus initially spans three independently maintained projects.
- Expand the external corpus again with official Polars shift and NumPy roll
  semantics, bringing it to five independent projects. The Polars negative-shift
  reproduction is detected by the existing rule while NumPy negative roll is
  first preserved as a documented time-series-context miss rather than hidden.
- Close that published NumPy negative-roll miss with opt-in `SRC012`, restricted
  to `np`/`numpy` attribute calls with literal negative shifts under declared
  time-series context. Add paired positive-roll and non-NumPy controls, and extend
  the planted conformance runner so contextual rules are tested explicitly.
- Make static-rule coverage executable: the conformance runner discovers shipped
  semantic `SRC` codes from the implementation and fails if any new rule lacks an
  exact expected corpus case. Add a reviewer-facing worked falsification loop and
  claim-specific reproduction commands to the research brief.
- Add a fixed-seed downstream metric-inflation experiment using the same OLS
  model and chronological split with causal versus future-exposing features. The
  synthetic holdout moves from R² 0.630 to 0.991 (+0.361) while `SRC001` catches
  the leaking source pattern; the experiment is part of the unified evaluation
  and is explicitly not presented as a real-world effect-size estimate.
- Structure GitHub failure intake around false negatives, false positives,
  temporal context, provenance, paired controls, and explicit acceptance
  criteria; document the failure-to-regression workflow for contributors. CI now
  uploads the Python 3.12 unified evaluation JSON as a reviewable artifact.
- Add a checked-in Jupyter fixture corpus with one leaking and one safe notebook
  for every semantic `SRC001+` rule. The notebook benchmark verifies exact rule
  IDs, cell numbers, canonical fixture contents, paired 12/12 rule coverage, and
  source-only cleanliness for context-gated `SRC011`/`SRC012`; CI and the sdist
  smoke test now enforce the corpus.
- Add an official Dask `Series.shift` leak/control pair as a sixth independent
  external project; the existing negative-shift rule transfers without a Dask-
  specific detector while the positive-shift control remains clean.
- Add an opt-in time-series source context and `SRC011` for generic/random CV,
  exposed through the Python API, CLI `--time-series`, and GitHub Action input;
  the generic scanner remains unchanged for IID projects.
- Extend `SRC011` to scikit-learn evaluation/search helpers whose `cv` is
  omitted, `None`, or a literal integer, with explicit `TimeSeriesSplit` and
  unresolved dynamic-CV controls to keep the rule conservative.
- Add an official scikit-learn nested-CV reproduction using inner
  `GridSearchCV` and outer `cross_val_score`. In declared time-series context the
  existing rule emits one `SRC011` at each IID CV layer, while the paired nested
  `TimeSeriesSplit` control remains clean; no detector change was needed.
- Extend the opt-in `SRC011` contract to `GroupKFold` and `GroupShuffleSplit`
  for declared panel/time-series evaluation, backed by official scikit-learn
  ordering/randomization semantics. The default IID scanner remains unchanged.
- Extend `SRC011` to metadata-routing-capable `learning_curve`,
  `validation_curve`, and `permutation_test_score` when declared time-series
  evaluation uses default/integer CV. Each reproduction has an explicit
  `TimeSeriesSplit` control, and the default IID scanner remains unchanged.
- Add an official Xarray `DataArray.shift` leak/control pair as a seventh
  independent external project. Extend `SRC001` narrowly to negative offsets on
  explicit temporal dimension names such as `time=-1`; positive temporal shifts
  and non-temporal negative keywords remain clean controls.
- Harden future-mutation invariance so interventions cannot change row count or
  the historical prefix, add optional `input_validator` support, and add a
  bounded-probability mutation-validity experiment to the unified evaluation.
- Extend intervention-validity evidence to OHLC candles, including rejection of
  an invalid `close > high` counterfactual and paired causal/leaking transforms
  under a domain-preserving future-only price mutation.
- Extend intervention-validity evidence again to simplex-normalized vectors,
  rejecting unit-sum violations while a future-only component permutation keeps
  the safe control clean and exposes the planted global dependency.
- Extend intervention-validity evidence to monotonic cumulative counters,
  rejecting future decreases while a domain-preserving future level shift keeps
  the causal incremental transform clean and exposes a planted final-value leak.
- Add a fixed-grid intervention-sensitivity benchmark spanning four domains,
  three cut points, and two valid mutation strengths; all 48 paired safe/leak
  checks must pass without selecting a favorable counterfactual after the fact.
- Add a real-pandas behavioral-generalization benchmark that executes library
  transforms rather than hand-written causal analogues, then expand it from six
  to eighteen cases. The added panel/irregular-time cases keep grouped
  expanding/EWM and forward fill clean while detecting group-wide mean, grouped
  backward fill, and time interpolation under explicit future-only mutation
  contracts that preserve timestamps and group identity. Additional paired cases
  cover backward/forward as-of alignment, right-closed/right-labeled vs
  left-labeled resampling, and two-column historical vs future differences under
  a mutation contract that changes both future feature columns without changing
  timestamp order or row count.
- Add a fixed-seed revision/vintage robustness benchmark with 24 generated
  histories and 120 checks covering valid order, row-order invariance,
  deterministic `REV001` detection after duplicate-availability injection,
  explicit eligibility delays, and latest-vintage selection under shuffled
  right-side rows; run it as part of the unified evaluation suite.
- Add a developer-only Hypothesis 6.168.0 property search over the five core
  revision/availability invariants plus seven multi-column/null edge invariants.
  Sixty-four generated examples produce 768 invariant evaluations with
  counterexample shrinking; coverage includes three-column revision keys,
  null-reason controls, null-to-value revisions, and missing-key rejection.
  Hypothesis is pinned in the `dev` extra after MPL-2.0/source/OSV review, while
  the core remains free of mandatory third-party runtime dependencies.
- Fail closed with `REV002` when any row participating in an append-only vintage
  contract has a missing revision-key value, aligning manifest behavior with the
  pandas point-in-time join's existing rejection of missing exact-match keys.
- Add an installed-wheel CI smoke test and package/runtime version consistency
  test so source checks cannot pass while the built artifact is stale or broken.
- Include the deterministic benchmarks, reviewer-facing research/evaluation docs,
  schemas, examples, and fixtures in the source distribution; CI now extracts
  the built sdist and reruns the unified evaluation from that artifact.
- Add a one-command evaluation-suite runner that aggregates conformance, method
  ablation, and external reproductions into one human or JSON report while
  preserving explicit claim limits and known misses.
- Gate reviewer-facing benchmark numbers in CI and in the built source
  distribution by deriving expected headline fragments from the live unified
  evaluator; stale README/research/evaluation/landing-page metrics now fail CI.
- Add a reviewer-facing research brief that makes the research question,
  contribution, negative result, reproducibility evidence, and next falsifiable
  experiments readable without reconstructing them from implementation docs.

- Expand the static scanner with high-confidence checks for negative
  `diff`/`pct_change` periods, legacy backward `fillna`, and backward/bidirectional
  interpolation.
- Expand the planted-leak corpus from 12 to 27 paired leak/safe cases.
- Report exact-case accuracy, finding precision/recall/F1, leak detection,
  specificity, and per-rule coverage from the deterministic benchmark runner.

## 0.4.0 - 2026-09-16

- Add `nofuture audit-manifest` and the zero-dependency `audit_manifest()` API
  for repository-level temporal data contracts.
- Require explicit event-time/known-at semantics, eligible-from and revision
  policies, offset-aware timestamps, and null-reason behavior.
- Validate referenced CSV columns, optional decision-time causality, duplicate
  revision availability times, explicit eligibility values, and unexplained
  missing values.
- Add a portable example manifest/dataset and run it in the Python compatibility
  CI matrix.
- Publish a Draft 2020-12 JSON Schema, valid/invalid fixtures, and stable
  `MAN001`-`MAN007`, `TIME005`, `REV001`, and `NULL001` rule IDs.

## 0.3.0 - 2026-09-16

- Add an optional pandas `point_in_time_join()` helper with backward-only as-of
  semantics, timezone-aware decision/availability validation, fail-closed
  duplicate handling, and revision/vintage regression tests.
- Add an evidence-backed ecosystem-importance note explaining the cross-domain
  temporal leakage problem and how NoFutureData complements framework-specific tools.
- Render documentation pages as HTML on GitHub Pages and publish a sitemap/robots file.

## 0.2.3 - 2026-09-16

- Harden composite Action inputs by passing user-controlled path values through
  environment variables instead of interpolating them into shell source.
- Add a CI regression test proving a valid path containing shell metacharacters
  remains data and does not execute as shell source.
- Ignore local downloaded workflow artifacts to prevent accidental commits.

## 0.2.2 - 2026-09-16

- Add a deterministic public planted-leak corpus and run it in CI.
- Add GitHub Marketplace branding metadata for the composite Action.
- Add a lightweight GitHub Pages landing page for discoverability.
- Move package licensing metadata to the current SPDX/PEP 639 form.

## 0.2.1 - 2026-09-16

- Add a tokenless, manually gated PyPI Trusted Publishing workflow.
- Add a stable rule reference.
- Add weekly Dependabot maintenance for GitHub Actions and Python build tooling.
- Make source scanning fail closed on missing paths or an entirely empty scan.
- Make `as_of()` reject an `eligible_from` timestamp that precedes `known_at`.
- Normalize common IPython magics in notebooks and skip non-Python cell magics.

## 0.2.0 - 2026-09-16

- Scan Python code cells in Jupyter notebooks.
- Accept multiple paths in `nofuture scan` for pre-commit compatibility.
- Add SARIF 2.1.0 export for GitHub Code Scanning and other SARIF consumers.
- Add a reusable pre-commit hook.
- Extend the GitHub Action with optional SARIF upload while preserving scan exit status.
- Add targeted (`nofuture: ignore[SRCxxx]`) and generic inline suppressions.

## 0.1.0 - 2026-09-16

- Add fail-closed availability auditing with timezone-aware `known_at` and
  `eligible_from` semantics.
- Add `as_of` filtering for historically available records.
- Add Python AST checks for negative shifts, backfill, centered rolling windows,
  and forward/nearest as-of joins.
- Add prefix-invariance and future-mutation runtime tests.
- Add CLI, GitHub Action, CI matrix, examples, and contributor documentation.
