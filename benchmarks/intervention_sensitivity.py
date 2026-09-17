"""Stress future-mutation conclusions across valid strengths and cut points.

This experiment reuses the four domain contracts from ``mutation_validity`` and
asks a different question: do the causal/leaking conclusions survive more than
one hand-picked counterfactual?  Each domain is evaluated at three historical
cut points and two domain-preserving mutation strengths.  Every scenario must
leave the causal prefix unchanged and expose the planted future dependency.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable, Sequence

from nofuturedata import future_mutation_invariance
from mutation_validity import (
    CUMULATIVE_ROWS,
    OHLC_ROWS,
    ROWS,
    VECTOR_ROWS,
    _leaking_cumulative_transform,
    _leaking_ohlc_transform,
    _leaking_transform,
    _leaking_vector_transform,
    _safe_cumulative_transform,
    _safe_ohlc_transform,
    _safe_transform,
    _safe_vector_transform,
    _valid_cumulative,
    _valid_normalized_vectors,
    _valid_ohlc,
    _valid_probabilities,
)


CUT_POINTS = (1, 2, 3)
STRENGTHS = (0.25, 0.50)


def _probability_mutator(strength: float):
    def mutate(rows, point):
        changed = [dict(row) for row in rows]
        for index in range(point, len(changed)):
            value = changed[index]["p"]
            changed[index]["p"] = value + strength * (1.0 - value)
        return changed

    return mutate


def _ohlc_mutator(strength: float):
    delta = 20.0 * strength

    def mutate(rows, point):
        changed = [dict(row) for row in rows]
        for index in range(point, len(changed)):
            for field in ("open", "high", "low", "close"):
                changed[index][field] += delta
        return changed

    return mutate


def _vector_mutator(strength: float):
    def mutate(rows, point):
        changed = [{**row, "weights": list(row["weights"])} for row in rows]
        for index in range(point, len(changed)):
            weights = changed[index]["weights"]
            rotated = [weights[1], weights[2], weights[0]]
            changed[index]["weights"] = [
                (1.0 - strength) * value + strength * other
                for value, other in zip(weights, rotated)
            ]
        return changed

    return mutate


def _cumulative_mutator(strength: float):
    delta = 40.0 * strength

    def mutate(rows, point):
        changed = [dict(row) for row in rows]
        for index in range(point, len(changed)):
            changed[index]["count"] += delta
        return changed

    return mutate


def _evaluate_domain(
    *,
    name: str,
    rows: Sequence[Any],
    validator: Callable[[Sequence[Any]], bool],
    safe_transform: Callable[[Sequence[Any]], Sequence[Any]],
    leaking_transform: Callable[[Sequence[Any]], Sequence[Any]],
    mutator_factory: Callable[[float], Callable[[Sequence[Any], int], Sequence[Any]]],
) -> tuple[dict[str, bool], list[dict[str, Any]]]:
    checks: dict[str, bool] = {}
    scenarios: list[dict[str, Any]] = []
    for strength in STRENGTHS:
        mutator = mutator_factory(strength)
        for point in CUT_POINTS:
            safe = future_mutation_invariance(
                safe_transform,
                rows,
                cut_points=[point],
                mutator=mutator,
                input_validator=validator,
            )
            leak = future_mutation_invariance(
                leaking_transform,
                rows,
                cut_points=[point],
                mutator=mutator,
                input_validator=validator,
            )
            stem = f"{name}_strength_{strength:.2f}_cut_{point}"
            checks[f"{stem}_safe_clean"] = safe.ok
            checks[f"{stem}_leak_detected"] = not leak.ok
            scenarios.append(
                {
                    "domain": name,
                    "strength": strength,
                    "cut_point": point,
                    "safe_clean": safe.ok,
                    "leak_detected": not leak.ok,
                }
            )
    return checks, scenarios


def run() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    scenarios: list[dict[str, Any]] = []
    domains = (
        (
            "probability",
            ROWS,
            _valid_probabilities,
            _safe_transform,
            _leaking_transform,
            _probability_mutator,
        ),
        (
            "ohlc",
            OHLC_ROWS,
            _valid_ohlc,
            _safe_ohlc_transform,
            _leaking_ohlc_transform,
            _ohlc_mutator,
        ),
        (
            "normalized_vector",
            VECTOR_ROWS,
            _valid_normalized_vectors,
            _safe_vector_transform,
            _leaking_vector_transform,
            _vector_mutator,
        ),
        (
            "cumulative",
            CUMULATIVE_ROWS,
            _valid_cumulative,
            _safe_cumulative_transform,
            _leaking_cumulative_transform,
            _cumulative_mutator,
        ),
    )
    for name, rows, validator, safe, leak, mutator_factory in domains:
        domain_checks, domain_scenarios = _evaluate_domain(
            name=name,
            rows=rows,
            validator=validator,
            safe_transform=safe,
            leaking_transform=leak,
            mutator_factory=mutator_factory,
        )
        checks.update(domain_checks)
        scenarios.extend(domain_scenarios)

    passed = sum(bool(value) for value in checks.values())
    return {
        "schema_version": "nofuturedata-intervention-sensitivity-v1",
        "ok": passed == len(checks),
        "passed": passed,
        "checks": len(checks),
        "domains": len(domains),
        "cut_points": list(CUT_POINTS),
        "strengths": list(STRENGTHS),
        "results": checks,
        "scenarios": scenarios,
        "claim_limit": (
            "This fixed-grid experiment tests conclusion stability across four planted "
            "domains, three cut points, and two valid mutation strengths. It is not a "
            "guarantee for arbitrary mutators, data distributions, or transforms."
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
        print(
            "NoFutureData intervention sensitivity: {} ({}/{}, {} domains, {} cuts, {} strengths)".format(
                state,
                result["passed"],
                result["checks"],
                result["domains"],
                len(result["cut_points"]),
                len(result["strengths"]),
            )
        )
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
