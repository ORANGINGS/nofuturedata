"""Run literature/documentation-backed temporal-leakage reproductions.

Unlike the planted conformance corpus, this corpus preserves examples derived
from external project documentation.  Known current misses are expected results:
the runner fails when detector behavior changes without updating the reviewed
baseline, not merely because a documented leak is currently undetected.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nofuturedata import audit_python_source


CORPUS = Path(__file__).with_name("external_reproductions.json")


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def run() -> dict[str, Any]:
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    baseline_matches = 0
    leak_cases = 0
    detected_leaks = 0
    safe_cases = 0
    clean_safe_cases = 0
    context_required_leaks = 0
    context_required_misses = 0
    context_cases = 0
    context_baseline_matches = 0
    context_detected_leaks = 0
    context_safe_cases = 0
    context_clean_safe_cases = 0
    assisted_detected_leaks = 0
    assisted_clean_safe_cases = 0

    for case in cases:
        actual = sorted(item.code for item in audit_python_source(case["source"]).findings)
        expected = sorted(case["expected_current_codes"])
        baseline_match = actual == expected
        baseline_matches += int(baseline_match)
        detected = bool(actual)

        context_name = case.get("scan_context")
        expected_context = sorted(case.get("expected_context_codes", []))
        actual_context: list[str] | None = None
        context_match: bool | None = None
        context_detected: bool | None = None
        if context_name is not None:
            context_cases += 1
            actual_context = sorted(
                item.code
                for item in audit_python_source(
                    case["source"], temporal_context=context_name
                ).findings
            )
            context_match = actual_context == expected_context
            context_baseline_matches += int(context_match)
            context_detected = bool(actual_context)
            if case["kind"] == "leak":
                context_detected_leaks += int(context_detected)
            else:
                context_safe_cases += 1
                context_clean_safe_cases += int(not context_detected)
        if case["kind"] == "leak":
            leak_cases += 1
            detected_leaks += int(detected)
            if case.get("context_required", False):
                context_required_leaks += 1
                context_required_misses += int(not detected)
        else:
            safe_cases += 1
            clean_safe_cases += int(not detected)

        assisted_detected = detected or bool(context_detected)
        if case["kind"] == "leak":
            assisted_detected_leaks += int(assisted_detected)
        else:
            assisted_clean_safe_cases += int(not assisted_detected)
        results.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "source_project": case["source_project"],
                "source_url": case["source_url"],
                "context_required": bool(case.get("context_required", False)),
                "expected_current_codes": expected,
                "actual_codes": actual,
                "baseline_match": baseline_match,
                "detected": detected,
                "scan_context": context_name,
                "expected_context_codes": expected_context if context_name else None,
                "actual_context_codes": actual_context,
                "context_baseline_match": context_match,
                "context_detected": context_detected,
                "assisted_detected": assisted_detected,
            }
        )

    return {
        "schema_version": "nofuturedata-external-reproductions-v1",
        "cases": len(cases),
        "leak_cases": leak_cases,
        "safe_cases": safe_cases,
        "baseline_matches": baseline_matches,
        "ok": baseline_matches == len(cases) and context_baseline_matches == context_cases,
        "observed_current_metrics": {
            "documented_leak_detection_rate": _ratio(detected_leaks, leak_cases),
            "safe_case_specificity": _ratio(clean_safe_cases, safe_cases),
            "detected_leaks": detected_leaks,
            "known_missed_leaks": leak_cases - detected_leaks,
            "context_required_leaks": context_required_leaks,
            "context_required_misses": context_required_misses,
            "context_cases": context_cases,
            "context_baseline_matches": context_baseline_matches,
            "context_detected_leaks": context_detected_leaks,
            "context_safe_cases": context_safe_cases,
            "context_safe_specificity": _ratio(
                context_clean_safe_cases, context_safe_cases
            ),
            "assisted_documented_leak_detection_rate": _ratio(
                assisted_detected_leaks, leak_cases
            ),
            "assisted_detected_leaks": assisted_detected_leaks,
            "assisted_safe_specificity": _ratio(
                assisted_clean_safe_cases, safe_cases
            ),
        },
        "source_projects": sorted({case["source_project"] for case in cases}),
        "results": results,
        "claim_limit": (
            "This curated documentation-backed corpus is small and non-random; its metrics describe "
            "these reproductions only and are not estimates of real-world recall or specificity."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        metrics = result["observed_current_metrics"]
        print(
            f"NoFutureData external reproductions: {result['baseline_matches']}/{result['cases']} "
            "match reviewed detector baseline"
        )
        print(
            "documented leak detection={:.3f} ({}/{}); safe specificity={:.3f}".format(
                metrics["documented_leak_detection_rate"],
                metrics["detected_leaks"],
                result["leak_cases"],
                metrics["safe_case_specificity"],
            )
        )
        print(
            "context-assisted detection={:.3f} ({}/{}); safe specificity={:.3f}".format(
                metrics["assisted_documented_leak_detection_rate"],
                metrics["assisted_detected_leaks"],
                result["leak_cases"],
                metrics["assisted_safe_specificity"],
            )
        )
        for row in result["results"]:
            state = "DETECTED" if row["detected"] else "MISS/CLEAN"
            print(f"{state:10} {row['id']} ({row['source_project']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
