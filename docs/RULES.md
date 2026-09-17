---
layout: default
title: NoFutureData rule reference
permalink: /RULES.html
---

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

## Point-in-time join contract

`point_in_time_join()` is an optional pandas helper for revision/vintage data.
It always performs a backward as-of match from each decision timestamp to the
latest eligible right-side row. `eligible_from` is preferred when present and
falls back to `known_at` for rows without an explicit eligibility timestamp.

The helper fails closed on timezone-naive timestamps, `eligible_from < known_at`,
missing exact-match `by` keys, and duplicate right-side rows with the same `by`
keys and availability timestamp. The duplicate rule is deliberate: revision
selection must not depend on dataframe row order. pandas remains an optional
extra and is not imported until this helper is called.

## Static source rules

| Code | Pattern | Why it is gated |
| --- | --- | --- |
| `SRC000` | source or notebook JSON cannot be parsed | an unparsed file cannot be claimed as checked |
| `SRC001` | negative `shift`, such as `shift(-1)` or `shift(time=-1)` | reads a later row into an earlier row |
| `SRC002` | `bfill()` / `backfill()` | can copy future observations backward |
| `SRC003` | `rolling(..., center=True)` | centered windows can include future rows |
| `SRC004` | `merge_asof(..., direction="forward"|"nearest")` | may match a row that was not yet available |
| `SRC005` | negative `diff(...)` / `pct_change(...)` periods | compares an earlier row with a later observation |
| `SRC006` | `fillna(method="bfill"|"backfill")` | can copy future observations backward through the legacy fillna API |
| `SRC007` | `interpolate(limit_direction="backward"|"both")` | may use later observations to fill earlier missing values |
| `SRC008` | whole-series aggregate assigned back to a column on the same dataframe | can broadcast a statistic computed with future rows into historical feature rows |
| `SRC009` | negative absolute `.iloc[-N]` indexing | selects from the end of the full object and can expose a future row to earlier decisions |
| `SRC010` | fixed/day interval `resample(...).<aggregate>()` with default/left labeling | can timestamp values observed later in the interval at the interval's left edge |
| `SRC011` | generic/random/group CV while `temporal_context="time_series"` is enabled | can train/evaluate with future observations when a splitter does not enforce chronological train-before-test order |
| `SRC012` | `np.roll(..., negative_shift)` / `numpy.roll(..., negative_shift)` while `temporal_context="time_series"` is enabled | circular negative roll moves later values into earlier positions on ordered rows |

`SRC011` is opt-in because the source syntax alone does not establish that a
dataset is time ordered. Enable it through `audit_python_source(...,
temporal_context="time_series")` or `nofuture scan ... --time-series`. The
default source scanner intentionally leaves ordinary IID `KFold` code clean.
In time-series context the rule covers classical K-fold/shuffle splitters,
`GroupKFold`, `GroupShuffleSplit`, shuffled `train_test_split`, and scikit-learn
evaluation/search helpers whose `cv` is omitted, `None`, or a literal integer.
That helper set includes `cross_val_score`, `cross_validate`, `cross_val_predict`,
`learning_curve`, `validation_curve`, `permutation_test_score`, `GridSearchCV`,
and `RandomizedSearchCV`.
The grouped splitters are context-gated because grouping can separate entities
without preserving chronological forecasting order. An explicit `TimeSeriesSplit`
control stays clean; a dynamic `cv=cv` expression is left unresolved rather than
guessed.

`SRC012` uses the same opt-in temporal context and is deliberately narrower than
a generic `roll` rule. It recognizes NumPy attribute calls rooted at the
conventional `np` or `numpy` module names with a literal negative shift. Dynamic
shifts, imported aliases, arbitrary objects exposing `.roll`, and positive rolls
remain outside the static rule and are left to behavioral checks when their
temporal semantics matter.

`SRC001` also recognizes negative offsets on the explicitly temporal keyword
dimensions `time`, `date`, `datetime`, and `timestamp`. Other negative keyword
arguments such as `axis=-1` are left clean because their temporal meaning is not
established by syntax alone.

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

`future_mutation_invariance()` also validates the intervention itself. A custom
mutator must preserve row count and the historical prefix. Callers can provide
an `input_validator` for domain invariants; an out-of-domain mutation is rejected
with `ValueError` rather than being reported as `LEAK102`. This separates a
causal failure from a malformed counterfactual.

## Dataset manifest rules

Repository-level temporal contracts use the `MAN001`-`MAN007`, `TIME005`,
`REV001`, `REV002`, and `NULL001` rules documented in the
[manifest reference](MANIFEST.html). Dataset rows also reuse the availability
rules above, so a timezone-naive `known_at` remains `TIME001` whether it is
checked directly or through a manifest.

## Severity and exit status

Current rules are emitted as `error`. The CLI returns exit code `1` when any
error finding exists and `0` when the report is clean. JSON and SARIF outputs
carry the same rule IDs so CI policy can remain stable across output formats.
