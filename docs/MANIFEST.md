---
layout: default
title: Temporal contract manifests
permalink: /MANIFEST.html
---

# Temporal contract manifests

`nofuture audit-manifest` turns a dataset's historical availability assumptions
into an executable CI contract. The validator itself remains zero-dependency and
the same contract is published as JSON Schema for editors and other tooling.

```json
{
  "schema_version": 1,
  "datasets": [
    {
      "path": "features/vintages.csv",
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

Paths are resolved relative to the manifest. `format` currently supports CSV.
`event_time.semantics` and `known_at.semantics` are deliberately descriptive
strings so providers can document their own meaning without a NoFutureData-
specific vocabulary.

Availability timestamps must be offset-aware. `eligible_from.policy` is either
`explicit_column` or `known_at`; the explicit policy requires every row to carry
an eligible timestamp. An optional `decision_time` object can name a decision
column and reuse the normal `LEAK001` causality check.

For revised data, `append_only_vintages` requires a key containing the event-time
column. Two vintages with the same logical key and the same `known_at` fail as
ambiguous. Use `revision.policy: "none"` for immutable datasets.

Null handling is explicit too. `required_when_value_missing` names the data
columns being monitored and a reason column; missing values without a reason fail
CI. Use `not_applicable` when the dataset contract intentionally has no nullable
value fields.

Run the contract locally or in CI:

```bash
nofuture audit-manifest temporal-contract.json
```

The portable schema lives at
[`schemas/temporal-contract.schema.json`](../schemas/temporal-contract.schema.json).
The repository also contains a passing contract, a schema-invalid contract, and
a schema-valid dataset with deliberately invalid temporal rows under
`tests/fixtures/manifest/`.

## Manifest and revision rules

| Code | Meaning |
| --- | --- |
| `MAN001` | manifest is missing, malformed JSON, or not a JSON object |
| `MAN002` | unsupported `schema_version` |
| `MAN003` | `datasets` is missing, empty, or not a list |
| `MAN004` | a dataset's temporal contract is incomplete or malformed |
| `MAN005` | a referenced dataset does not exist |
| `MAN006` | dataset format is unsupported |
| `MAN007` | dataset is missing a required contract column |
| `TIME005` | explicit `eligible_from` policy has a missing row value |
| `REV001` | a logical observation has duplicate revision availability time |
| `REV002` | a logical observation has a missing revision-key value |
| `NULL001` | a monitored value is missing without a null reason |

Availability findings such as `TIME001`, `TIME003`, and `LEAK001` are reused
unchanged so direct CSV audits and manifest-driven audits share the same causal
rule IDs.
