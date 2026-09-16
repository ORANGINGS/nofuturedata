# Contributing

NoFutureData should stay small, deterministic, and useful outside any one
industry. Bug reports and minimal reproductions are especially valuable.

## Development

```bash
python -m venv .venv
python -m pip install -e . pytest
pytest
nofuture scan src tests examples
```

For a new leakage rule, include a failing example, a safe counter-example, and
a test showing why the rule cannot be replaced by a simpler existing check.

The static scanner is intentionally conservative. A source-code finding means
"review this causal assumption", while runtime prefix/future-mutation failures
are stronger evidence that historical output depends on future input.

