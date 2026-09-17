"""Compare NoFutureData's static and behavioral leakage checks.

This is a deliberately small, deterministic method-ablation corpus.  It is not
an estimate of real-world prevalence or recall.  Each case has an explicit
ground-truth label and, when runnable, a transform with the same causal shape as
the source example.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from typing import Any

from nofuturedata import (
    audit_python_source,
    future_mutation_invariance,
    prefix_invariance,
)


Rows = Sequence[dict[str, Any]]
Transform = Callable[[Rows], Sequence[Any]]


def _safe_cumulative(rows: Rows) -> list[int]:
    total = 0
    output: list[int] = []
    for row in rows:
        total += int(row["x"])
        output.append(total)
    return output


def _safe_lag(rows: Rows) -> list[Any]:
    return [None] + [row["x"] for row in rows[:-1]] if rows else []


def _next_value(rows: Rows) -> list[Any]:
    return [rows[index + 1]["x"] if index + 1 < len(rows) else None for index in range(len(rows))]


def _global_sum(rows: Rows) -> list[int]:
    total = sum(int(row["x"]) for row in rows)
    return [total for _ in rows]


def _last_value(rows: Rows) -> list[Any]:
    if not rows:
        return []
    last = rows[-1]["x"]
    return [last for _ in rows]


def _backfill(rows: Rows) -> list[Any]:
    output: list[Any] = []
    for index, row in enumerate(rows):
        value = row["x"]
        if value is None:
            value = next(
                (future["x"] for future in rows[index + 1 :] if future["x"] is not None),
                None,
            )
        output.append(value)
    return output


BASE_ROWS = [{"x": value} for value in range(1, 9)]
BACKFILL_ROWS = [{"x": 1}, {"x": None}, {"x": 3}, {"x": 4}, {"x": 5}]


CASES: list[dict[str, Any]] = [
    {
        "id": "safe-cumulative",
        "kind": "safe",
        "source": "out = df.x.cumsum()\n",
        "rows": BASE_ROWS,
        "transform": _safe_cumulative,
    },
    {
        "id": "safe-lag",
        "kind": "safe",
        "source": "out = df.x.shift(1)\n",
        "rows": BASE_ROWS,
        "transform": _safe_lag,
    },
    {
        "id": "negative-shift",
        "kind": "leak",
        "source": "out = df.x.shift(-1)\n",
        "rows": BASE_ROWS,
        "transform": _next_value,
    },
    {
        "id": "backfill",
        "kind": "leak",
        "source": "out = df.x.bfill()\n",
        "rows": BACKFILL_ROWS,
        "transform": _backfill,
    },
    {
        "id": "indirect-global-sum",
        "kind": "leak",
        "source": "total = sum(row['x'] for row in rows)\nout = [total for _ in rows]\n",
        "rows": BASE_ROWS,
        "transform": _global_sum,
    },
    {
        "id": "indirect-last-row",
        "kind": "leak",
        "source": "last = rows[-1]['x']\nout = [last for _ in rows]\n",
        "rows": BASE_ROWS,
        "transform": _last_value,
    },
]


def _metrics(rows: list[dict[str, Any]], key: str) -> dict[str, float | int]:
    tp = sum(row["kind"] == "leak" and row[key] for row in rows)
    fp = sum(row["kind"] == "safe" and row[key] for row in rows)
    fn = sum(row["kind"] == "leak" and not row[key] for row in rows)
    tn = sum(row["kind"] == "safe" and not row[key] for row in rows)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    specificity = tn / (tn + fp) if tn + fp else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive_cases": tp,
        "false_positive_cases": fp,
        "false_negative_cases": fn,
        "true_negative_cases": tn,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
    }


def run() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in CASES:
        static_report = audit_python_source(case["source"])
        prefix_report = prefix_invariance(case["transform"], case["rows"])
        mutation_report = future_mutation_invariance(case["transform"], case["rows"])
        static_detected = not static_report.ok
        prefix_detected = not prefix_report.ok
        mutation_detected = not mutation_report.ok
        runtime_detected = prefix_detected or mutation_detected
        combined_detected = static_detected or runtime_detected
        results.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "static_detected": static_detected,
                "static_codes": sorted(item.code for item in static_report.findings),
                "prefix_detected": prefix_detected,
                "mutation_detected": mutation_detected,
                "runtime_detected": runtime_detected,
                "combined_detected": combined_detected,
            }
        )

    metrics = {
        "static": _metrics(results, "static_detected"),
        "prefix_invariance": _metrics(results, "prefix_detected"),
        "future_mutation": _metrics(results, "mutation_detected"),
        "runtime_union": _metrics(results, "runtime_detected"),
        "combined": _metrics(results, "combined_detected"),
    }
    expected = {
        "static": {"recall": 0.5, "specificity": 1.0},
        "runtime_union": {"recall": 1.0, "specificity": 1.0},
        "combined": {"recall": 1.0, "specificity": 1.0},
    }
    ok = all(
        metrics[method][metric] == value
        for method, checks in expected.items()
        for metric, value in checks.items()
    )
    return {
        "schema_version": "nofuturedata-method-comparison-v1",
        "cases": len(results),
        "leak_cases": sum(row["kind"] == "leak" for row in results),
        "safe_cases": sum(row["kind"] == "safe" for row in results),
        "ok": ok,
        "metrics": metrics,
        "results": results,
        "interpretation": {
            "static_boundary": "AST rules catch explicit known patterns but not arbitrary indirect future dependencies.",
            "runtime_boundary": "Behavioral checks require an executable transform and representative rows.",
            "claim_limit": "These deterministic ablations demonstrate method complementarity, not real-world recall.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"NoFutureData method comparison: {result['cases']} cases "
            f"({result['leak_cases']} leak, {result['safe_cases']} safe)"
        )
        for method in ("static", "prefix_invariance", "future_mutation", "runtime_union", "combined"):
            metrics = result["metrics"][method]
            print(
                f"{method:18} precision={metrics['precision']:.3f} "
                f"recall={metrics['recall']:.3f} specificity={metrics['specificity']:.3f} "
                f"f1={metrics['f1']:.3f}"
            )
        for row in result["results"]:
            print(
                f"{row['id']:22} kind={row['kind']:4} static={int(row['static_detected'])} "
                f"prefix={int(row['prefix_detected'])} mutation={int(row['mutation_detected'])}"
            )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
