# Rule reference

NoFutureData separates three kinds of evidence: availability-time contracts,
static source review gates, and runtime invariance checks. Static findings are
deliberately conservative review gates; runtime invariance failures are stronger
evidence that historical output depends on future input.

## Availability-time rules

| Code | Meaning |
| --- | --- |
| `TIME001` | `known_at` is missing, invalid, or timezone-naive. |
| `TIME002` | `eligible_from` is present but invalid or timezone-naive. |
| `TIME003` | `eligible_from` precedes `known_at`. |
| `TIME004` | the configured decision-time field is missing, invalid, or timezone-naive. |
| `LEAK001` | the record became available after the decision that consumed it. |

NoFutureData does not require `event_time <= known_at`. A future scheduled event
can legitimately be known before it happens. The causal boundary is availability
to the consumer, not event chronology alone.

## Static source rules

| Code | Pattern | Why it is gated |
| --- | --- | --- |
| `SRC000` | source or notebook JSON cannot be parsed | an unparsed file cannot be claimed as checked |
| `SRC001` | negative `shift`, such as `shift(-1)` | reads a later row into an earlier row |
| `SRC002` | `bfill()` / `backfill()` | can copy future observations backward |
| `SRC003` | `rolling(..., center=True)` | centered windows can include future rows |
| `SRC004` | `merge_asof(..., direction="forward"|"nearest")` | may match a row that was not yet available |

## Scan configuration rules

| Code | Meaning |
| --- | --- |
| `CFG001` | a requested scan path does not exist |
| `CFG002` | none of the requested paths contains a Python or Jupyter source file |

These configuration failures are errors so a typo such as `nofuture scan scr/`
cannot silently turn a CI gate green.

These patterns can be legitimate in label construction or retrospective
analysis. Suppress an intentional use on the exact line:

```python
label = close.shift(-1) > close  # nofuture: ignore[SRC001]
```

Use `# nofuture: ignore` only when every NoFutureData finding on that line is
intentional. Rule-specific suppressions are preferred because they survive new
rules more safely.

For Jupyter notebooks, IPython line magics (`%...`), shell escapes (`!...`),
and Python-executing cell magics such as `%%time` are normalized before AST
analysis while preserving cell-local line numbers. Non-Python cell magics such
as `%%bash` are skipped.

## Runtime invariance rules

| Code | Check | Failure means |
| --- | --- | --- |
| `LEAK101` | prefix invariance | recomputing on only historical rows changes an already-produced historical output |
| `LEAK102` | future mutation invariance | mutating only future values changes an already-produced historical output |

Runtime checks are transform-agnostic. They are useful for custom feature code
that a syntax rule cannot recognize.

## Severity and exit status

Current rules are emitted as `error`. The CLI returns exit code `1` when any
error finding exists and `0` when the report is clean. JSON and SARIF outputs
carry the same rule IDs so CI policy can remain stable across output formats.
