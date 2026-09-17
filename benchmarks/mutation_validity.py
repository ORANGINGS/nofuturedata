"""Test whether future-mutation leakage checks use valid interventions.

The default numeric mutator is intentionally generic.  This benchmark gives the
input a probability-domain contract, shows that the generic mutation is rejected
when it leaves that domain, and then verifies that a domain-preserving mutator
keeps a causal transform clean while still detecting an actual future dependency.

It also exercises an OHLC candle contract.  A mutation that makes ``close`` exceed
``high`` must be rejected, while an affine future-only price mutation that preserves
the candle ordering must keep a causal transform clean and expose a planted global
future dependency.

Finally, it exercises simplex-normalized vectors.  A mutation that breaks the
non-negative unit-sum constraint must be rejected, while a future-only component
permutation preserves the domain and can be used for the same causal/leaking pair.

The fourth domain is a monotonic cumulative counter.  A future mutation that
decreases the counter below its historical predecessor must be rejected, while a
future-only level shift preserves monotonicity and separates a causal incremental
transform from a planted dependency on the final cumulative value.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from nofuturedata import future_mutation_invariance


ROWS = [{"p": value} for value in (0.1, 0.2, 0.3, 0.4)]

OHLC_ROWS = [
    {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0},
    {"open": 101.0, "high": 104.0, "low": 100.0, "close": 103.0},
    {"open": 103.0, "high": 105.0, "low": 101.0, "close": 102.0},
    {"open": 102.0, "high": 106.0, "low": 101.0, "close": 105.0},
]

VECTOR_ROWS = [
    {"weights": [0.6, 0.3, 0.1]},
    {"weights": [0.5, 0.2, 0.3]},
    {"weights": [0.2, 0.7, 0.1]},
    {"weights": [0.1, 0.3, 0.6]},
]

CUMULATIVE_ROWS = [
    {"count": 10.0},
    {"count": 20.0},
    {"count": 35.0},
    {"count": 50.0},
]


def _valid_probabilities(rows) -> bool:
    return all(0.0 <= row["p"] <= 1.0 for row in rows)


def _bounded_mutator(rows, point):
    changed = [dict(row) for row in rows]
    for index in range(point, len(changed)):
        changed[index]["p"] = 1.0 - changed[index]["p"]
    return changed


def _past_edit_mutator(rows, point):
    changed = [dict(row) for row in rows]
    changed[0]["p"] = 0.9
    return changed


def _safe_transform(rows):
    return [row["p"] for row in rows]


def _leaking_transform(rows):
    mean = sum(row["p"] for row in rows) / len(rows)
    return [mean for _ in rows]


def _valid_ohlc(rows) -> bool:
    required = {"open", "high", "low", "close"}
    for row in rows:
        if not required.issubset(row):
            return False
        open_ = row["open"]
        high = row["high"]
        low = row["low"]
        close = row["close"]
        if not all(isinstance(value, (int, float)) for value in (open_, high, low, close)):
            return False
        if low > min(open_, close) or high < max(open_, close) or low > high:
            return False
    return True


def _invalid_ohlc_mutator(rows, point):
    changed = [dict(row) for row in rows]
    for index in range(point, len(changed)):
        changed[index]["close"] = changed[index]["high"] + 10.0
    return changed


def _valid_ohlc_mutator(rows, point):
    changed = [dict(row) for row in rows]
    for index in range(point, len(changed)):
        for field in ("open", "high", "low", "close"):
            changed[index][field] += 25.0
    return changed


def _safe_ohlc_transform(rows):
    return [row["close"] - row["open"] for row in rows]


def _leaking_ohlc_transform(rows):
    future_high = max(row["high"] for row in rows)
    return [future_high - row["open"] for row in rows]


def _valid_normalized_vectors(rows) -> bool:
    for row in rows:
        weights = row.get("weights")
        if not isinstance(weights, list) or len(weights) < 2:
            return False
        if not all(isinstance(value, (int, float)) for value in weights):
            return False
        if any(value < 0.0 or value > 1.0 for value in weights):
            return False
        if abs(sum(weights) - 1.0) > 1e-9:
            return False
    return True


def _invalid_vector_mutator(rows, point):
    changed = [{**row, "weights": list(row["weights"])} for row in rows]
    for index in range(point, len(changed)):
        changed[index]["weights"] = [0.8, 0.8, 0.0]
    return changed


def _valid_vector_mutator(rows, point):
    changed = [{**row, "weights": list(row["weights"])} for row in rows]
    for index in range(point, len(changed)):
        weights = changed[index]["weights"]
        weights[0], weights[1] = weights[1], weights[0]
    return changed


def _safe_vector_transform(rows):
    return [row["weights"][0] for row in rows]


def _leaking_vector_transform(rows):
    mean_first_component = sum(row["weights"][0] for row in rows) / len(rows)
    return [mean_first_component for _ in rows]


def _valid_cumulative(rows) -> bool:
    previous = None
    for row in rows:
        value = row.get("count")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if value < 0.0:
            return False
        if previous is not None and value < previous:
            return False
        previous = value
    return True


def _invalid_cumulative_mutator(rows, point):
    changed = [dict(row) for row in rows]
    changed[point]["count"] = changed[point - 1]["count"] - 1.0
    return changed


def _valid_cumulative_mutator(rows, point):
    changed = [dict(row) for row in rows]
    for index in range(point, len(changed)):
        changed[index]["count"] += 100.0
    return changed


def _safe_cumulative_transform(rows):
    increments = []
    previous = 0.0
    for row in rows:
        value = row["count"]
        increments.append(value - previous)
        previous = value
    return increments


def _leaking_cumulative_transform(rows):
    final_count = rows[-1]["count"]
    return [final_count - row["count"] for row in rows]


def _rejected(call, expected_fragment: str) -> bool:
    try:
        call()
    except ValueError as exc:
        return expected_fragment in str(exc)
    return False


def run() -> dict[str, Any]:
    default_invalid_rejected = _rejected(
        lambda: future_mutation_invariance(
            _safe_transform,
            ROWS,
            cut_points=[2],
            input_validator=_valid_probabilities,
        ),
        "input contract",
    )
    past_edit_rejected = _rejected(
        lambda: future_mutation_invariance(
            _safe_transform,
            ROWS,
            cut_points=[2],
            mutator=_past_edit_mutator,
            input_validator=_valid_probabilities,
        ),
        "historical prefix",
    )
    safe_report = future_mutation_invariance(
        _safe_transform,
        ROWS,
        cut_points=[2],
        mutator=_bounded_mutator,
        input_validator=_valid_probabilities,
    )
    leak_report = future_mutation_invariance(
        _leaking_transform,
        ROWS,
        cut_points=[2],
        mutator=_bounded_mutator,
        input_validator=_valid_probabilities,
    )
    invalid_ohlc_rejected = _rejected(
        lambda: future_mutation_invariance(
            _safe_ohlc_transform,
            OHLC_ROWS,
            cut_points=[2],
            mutator=_invalid_ohlc_mutator,
            input_validator=_valid_ohlc,
        ),
        "input contract",
    )
    safe_ohlc_report = future_mutation_invariance(
        _safe_ohlc_transform,
        OHLC_ROWS,
        cut_points=[2],
        mutator=_valid_ohlc_mutator,
        input_validator=_valid_ohlc,
    )
    leak_ohlc_report = future_mutation_invariance(
        _leaking_ohlc_transform,
        OHLC_ROWS,
        cut_points=[2],
        mutator=_valid_ohlc_mutator,
        input_validator=_valid_ohlc,
    )
    invalid_vector_rejected = _rejected(
        lambda: future_mutation_invariance(
            _safe_vector_transform,
            VECTOR_ROWS,
            cut_points=[2],
            mutator=_invalid_vector_mutator,
            input_validator=_valid_normalized_vectors,
        ),
        "input contract",
    )
    safe_vector_report = future_mutation_invariance(
        _safe_vector_transform,
        VECTOR_ROWS,
        cut_points=[2],
        mutator=_valid_vector_mutator,
        input_validator=_valid_normalized_vectors,
    )
    leak_vector_report = future_mutation_invariance(
        _leaking_vector_transform,
        VECTOR_ROWS,
        cut_points=[2],
        mutator=_valid_vector_mutator,
        input_validator=_valid_normalized_vectors,
    )
    invalid_cumulative_rejected = _rejected(
        lambda: future_mutation_invariance(
            _safe_cumulative_transform,
            CUMULATIVE_ROWS,
            cut_points=[2],
            mutator=_invalid_cumulative_mutator,
            input_validator=_valid_cumulative,
        ),
        "input contract",
    )
    safe_cumulative_report = future_mutation_invariance(
        _safe_cumulative_transform,
        CUMULATIVE_ROWS,
        cut_points=[2],
        mutator=_valid_cumulative_mutator,
        input_validator=_valid_cumulative,
    )
    leak_cumulative_report = future_mutation_invariance(
        _leaking_cumulative_transform,
        CUMULATIVE_ROWS,
        cut_points=[2],
        mutator=_valid_cumulative_mutator,
        input_validator=_valid_cumulative,
    )
    valid_safe_control_clean = safe_report.ok
    valid_leak_detected = not leak_report.ok
    valid_ohlc_safe_control_clean = safe_ohlc_report.ok
    valid_ohlc_leak_detected = not leak_ohlc_report.ok
    valid_vector_safe_control_clean = safe_vector_report.ok
    valid_vector_leak_detected = not leak_vector_report.ok
    valid_cumulative_safe_control_clean = safe_cumulative_report.ok
    valid_cumulative_leak_detected = not leak_cumulative_report.ok
    ok = all(
        (
            default_invalid_rejected,
            past_edit_rejected,
            valid_safe_control_clean,
            valid_leak_detected,
            invalid_ohlc_rejected,
            valid_ohlc_safe_control_clean,
            valid_ohlc_leak_detected,
            invalid_vector_rejected,
            valid_vector_safe_control_clean,
            valid_vector_leak_detected,
            invalid_cumulative_rejected,
            valid_cumulative_safe_control_clean,
            valid_cumulative_leak_detected,
        )
    )
    return {
        "schema_version": "nofuturedata-mutation-validity-v1",
        "ok": ok,
        "checks": {
            "default_out_of_domain_mutation_rejected": default_invalid_rejected,
            "historical_prefix_edit_rejected": past_edit_rejected,
            "domain_valid_safe_control_clean": valid_safe_control_clean,
            "domain_valid_future_dependency_detected": valid_leak_detected,
            "invalid_ohlc_mutation_rejected": invalid_ohlc_rejected,
            "domain_valid_ohlc_safe_control_clean": valid_ohlc_safe_control_clean,
            "domain_valid_ohlc_future_dependency_detected": valid_ohlc_leak_detected,
            "invalid_normalized_vector_mutation_rejected": invalid_vector_rejected,
            "domain_valid_vector_safe_control_clean": valid_vector_safe_control_clean,
            "domain_valid_vector_future_dependency_detected": valid_vector_leak_detected,
            "invalid_cumulative_mutation_rejected": invalid_cumulative_rejected,
            "domain_valid_cumulative_safe_control_clean": valid_cumulative_safe_control_clean,
            "domain_valid_cumulative_future_dependency_detected": valid_cumulative_leak_detected,
        },
        "claim_limit": (
            "This benchmark establishes intervention validity for bounded-probability, OHLC "
            "candle, simplex-normalized vector, and monotonic cumulative contracts. Other "
            "domains require their own validators and mutators."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"NoFutureData mutation-validity experiment: {state}")
        for name, passed in result["checks"].items():
            print(f"{'PASS' if passed else 'FAIL':4}  {name}")
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
