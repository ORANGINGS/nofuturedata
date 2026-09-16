# NoFutureData

[![CI](https://github.com/ORANGINGS/nofuturedata/actions/workflows/ci.yml/badge.svg)](https://github.com/ORANGINGS/nofuturedata/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/ORANGINGS/nofuturedata)](https://github.com/ORANGINGS/nofuturedata/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/ORANGINGS/nofuturedata/total)](https://github.com/ORANGINGS/nofuturedata/releases)

**Fail-closed temporal leakage checks for time-series, ML, forecasting, and backtests.**

Most leakage tools ask whether train and test rows overlap. NoFutureData asks a
more operational question:

> At the instant this prediction or decision was made, could the pipeline have
> actually known every input it used?

It separates event time from availability time, statically flags common
future-looking pandas patterns, and can test a feature pipeline by deleting or
mutating future inputs and verifying that past outputs do not change.

NoFutureData is local, deterministic, and has no runtime dependency or network
service.

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

Install the signed-off release wheel directly from GitHub:

```bash
python -m pip install https://github.com/ORANGINGS/nofuturedata/releases/download/v0.2.0/nofuturedata-0.2.0-py3-none-any.whl
```

The release also includes `SHA256SUMS.txt`. For editable development from a
checkout:

```bash
python -m pip install -e .
```

The package requires Python 3.10+ and has no runtime dependency outside the
standard library.

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

## 3. Scan Python and Jupyter source

```bash
nofuture scan src/
```

Multiple paths are accepted, so the same command works naturally with
pre-commit's filename passing:

```bash
nofuture scan src tests notebooks
```

Python code cells inside `.ipynb` files are scanned too. Findings report the
notebook cell number; markdown and non-Python notebooks are ignored.

Version 0.1 flags:

- negative `shift(...)`, such as `shift(-1)`;
- `bfill()` / `backfill()`;
- centered rolling windows;
- `merge_asof(..., direction="forward"|"nearest")`.

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

## 4. Test the pipeline, not only the syntax

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
      - uses: ORANGINGS/nofuturedata@v0.2.0
        with:
          path: src
```

To publish findings in GitHub Code Scanning, grant `security-events: write` and
turn on SARIF upload:

```yaml
permissions:
  contents: read
  security-events: write

steps:
  - uses: actions/checkout@v7
  - uses: ORANGINGS/nofuturedata@v0.2.0
    with:
      path: .
      sarif: nofuturedata.sarif
      upload-sarif: "true"
```

## Pre-commit

```yaml
repos:
  - repo: https://github.com/ORANGINGS/nofuturedata
    rev: v0.2.0
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

- [Rule reference](docs/RULES.md) — stable rule IDs, rationale, suppressions,
  and runtime invariance semantics.
- [PyPI publishing](docs/PYPI_PUBLISHING.md) — tokenless OIDC release workflow
  and the one-time Trusted Publisher setup.
- [Roadmap](ROADMAP.md) — next candidate capabilities and adoption evidence.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Synthetic minimal reproductions are
preferred. New static rules need both a leaking example and a safe
counter-example.

## License

MIT.
