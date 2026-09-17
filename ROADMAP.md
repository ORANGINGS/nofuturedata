# Roadmap

The project will prioritize evidence of real user pain over feature count.

## Shipped in 0.2

- SARIF output for GitHub code scanning.
- Jupyter notebook scanning.
- Pre-commit integration.
- Public planted-leak corpus with safe controls and CI verification.
- GitHub Pages landing page and Marketplace-ready Action metadata.

## Shipped in 0.3

- Point-in-time joins for pandas with explicit availability columns.

## Shipped in 0.4

- Repository-level JSON temporal contracts for CSV datasets.
- Revision/vintage ambiguity checks keyed by logical observation.
- CI example for `nofuture audit-manifest`.

## In 0.5 development

- Extend the Hypothesis revision/vintage search to 12 invariants covering
  multi-column revision keys, null/revision interactions, and missing-key
  fail-closed behavior (`REV002`).
- Expand real-pandas behavioral transfer to 18 paired cases spanning ordinary,
  grouped/stateful, irregular missing-data, as-of alignment, resampling-boundary,
  and multi-column stateful transforms with explicit future-only mutation
  contracts.

## Next

- Point-in-time joins for Polars with explicit availability columns.
- Purging and embargo helpers for overlapping labels.

## Later

- Reusable CI policy file for repository-wide temporal contracts.
- Expand the public corpus with real-world minimal reproductions contributed by users.

## Adoption evidence to publish

- Distinct downstream repositories using the action/package.
- Issue and PR turnaround time.
- False-positive examples and rule changes driven by user reports.
- Tagged releases and compatibility matrix.

## Evaluation evidence

- Keep the planted static corpus paired with safe controls and exact rule-ID expectations.
- Keep the static-vs-runtime method ablation in CI so method boundaries stay explicit.
- Continue expanding the externally sourced reproduction corpus beyond the
  current nine projects/backends before making real-world recall claims; preserve known
  misses rather than broadening rules without paired controls.
- Keep `SRC008` whole-frame aggregation and `SRC009` absolute-index rules narrow;
  expand their externally sourced safe controls before broadening either rule.
- Keep `SRC010` limited to fixed/day interval aggregation with default/left
  labeling; do not infer dynamic/calendar-frequency semantics without evidence.
- Expand the opt-in time-series evaluation contract only with paired contextual
  controls; `SRC011` must not become a global ban on ordinary IID cross-validation.
- Keep `SRC012` limited to explicit time-series context plus `np`/`numpy`
  attribute calls with literal negative shifts; add alias/dynamic-shift support
  only when paired controls justify the broader static semantics.
- Keep metadata-routing-capable CV helpers paired with explicit
  `TimeSeriesSplit` controls; test custom/predefined splitters before inferring
  safety from dynamic `cv` expressions.
- Keep the real-pandas behavioral-transfer layer in the unified evaluator and
  expand next to duplicated timestamps, session-aware resampling boundaries, and
  chained alignment/resampling/missing-data pipelines only with paired causal
  controls and explicit input contracts.
- Keep the fixed-seed revision/vintage generator in the unified evaluation and
  expand it only with explicit invariants and reproducible counterexamples.
- Keep the Hypothesis property search paired with that fixed-seed benchmark so
  shrinking broadens counterexample search without replacing exact reproduction.
