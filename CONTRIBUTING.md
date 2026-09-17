# Contributing

NoFutureData should stay small, deterministic, and useful outside any one
industry. Bug reports and minimal reproductions are especially valuable.

## Development

```bash
python -m venv .venv
python -m pip install -e ".[pandas,dev]"
python -m pytest -q
nofuture scan src tests examples
python benchmarks/run_evaluation.py
python benchmarks/check_documented_metrics.py
```

For a new leakage rule, include a failing example, a safe counter-example, and
a test showing why the rule cannot be replaced by a simpler existing check.

The static scanner is intentionally conservative. A source-code finding means
"review this causal assumption", while runtime prefix/future-mutation failures
are stronger evidence that historical output depends on future input.

## Turn failures into evaluation cases

False negatives and false positives are research inputs, not just bug counts.
When possible, file them with a minimal reproducer, the closest paired safe
control, the scan context, and a public documentation/provenance URL.

An externally sourced false negative should first be preserved as a reviewed
baseline reproduction. A detector change should then add the narrowest rule that
closes that case while keeping the paired control clean. The planted conformance
runner fails if a shipped semantic `SRC` rule has no exact expected corpus case,
and the unified evaluation must remain green before the change is accepted.

Do not broaden a rule solely to improve a headline score. If the syntax does not
establish temporal semantics, require explicit context or leave the case visible
for runtime/domain-specific checks.
