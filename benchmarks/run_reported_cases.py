"""Reproduce reviewed NoFutureData behavior on public GitHub-reported cases.

This corpus is intentionally separate from documentation-backed API examples.
It records real user-reported failure modes and a maintainer-confirmed framework
boundary. Reporter claims are provenance, not proof that a project maintainer
accepted the diagnosis.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from nofuturedata import audit_availability, audit_python_source


CORPUS = Path(__file__).with_name("reported_cases.json")


def _codes(report: Any) -> list[str]:
    return sorted(item.code for item in report.findings)


def run() -> dict[str, Any]:
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    baseline_matches = 0
    leak_cases = 0
    layered_detected_leaks = 0
    source_only_missed_leaks = 0
    availability_recovered_leaks = 0
    safe_cases = 0
    known_static_false_positive_boundaries = 0

    for case in cases:
        static_actual = _codes(audit_python_source(case["source"]))
        static_expected = sorted(case.get("expected_static_codes", []))
        static_match = static_actual == static_expected

        availability_actual: list[str] = []
        if case.get("availability_records") is not None:
            options = case.get("availability_options", {})
            availability_actual = _codes(
                audit_availability(
                    case["availability_records"],
                    eligible_from=options.get("eligible_from", "eligible_from"),
                    decision_time=options.get("decision_time"),
                )
            )
        availability_expected = sorted(case.get("expected_availability_codes", []))
        availability_match = availability_actual == availability_expected
        baseline_match = static_match and availability_match
        baseline_matches += int(baseline_match)

        semantic_label = case["semantic_label"]
        if semantic_label == "reported_leak":
            leak_cases += 1
            layered_detected = bool(static_actual or availability_actual)
            layered_detected_leaks += int(layered_detected)
            source_only_missed = not static_actual
            source_only_missed_leaks += int(source_only_missed)
            availability_recovered_leaks += int(source_only_missed and bool(availability_actual))
        elif semantic_label == "reported_safe":
            safe_cases += 1
            layered_detected = False
            known_static_false_positive_boundaries += int(
                bool(case.get("known_static_false_positive")) and bool(static_actual)
            )
        else:
            raise ValueError(f"unknown semantic_label: {semantic_label!r}")

        results.append(
            {
                "id": case["id"],
                "semantic_label": semantic_label,
                "evidence_class": case["evidence_class"],
                "source_project": case["source_project"],
                "source_url": case["source_url"],
                "expected_static_codes": static_expected,
                "actual_static_codes": static_actual,
                "expected_availability_codes": availability_expected,
                "actual_availability_codes": availability_actual,
                "baseline_match": baseline_match,
                "layered_detected": layered_detected,
                "known_static_false_positive": bool(
                    case.get("known_static_false_positive", False)
                ),
            }
        )

    evidence_classes = Counter(case["evidence_class"] for case in cases)
    ok = baseline_matches == len(cases) and layered_detected_leaks == leak_cases
    return {
        "schema_version": "nofuturedata-reported-cases-v1",
        "cases": len(cases),
        "baseline_matches": baseline_matches,
        "leak_cases": leak_cases,
        "layered_detected_leaks": layered_detected_leaks,
        "source_only_missed_leaks": source_only_missed_leaks,
        "availability_recovered_leaks": availability_recovered_leaks,
        "safe_cases": safe_cases,
        "known_static_false_positive_boundaries": known_static_false_positive_boundaries,
        "source_projects": sorted({case["source_project"] for case in cases}),
        "evidence_classes": dict(sorted(evidence_classes.items())),
        "ok": ok,
        "results": results,
        "claim_limit": (
            "These cases preserve public GitHub reports and reviewed detector behavior. "
            "Reporter-authored issue claims are not treated as maintainer-validated diagnoses, "
            "and the corpus is not a prevalence or accuracy estimate."
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
            f"NoFutureData GitHub-reported cases: {state} "
            f"({result['baseline_matches']}/{result['cases']} reviewed baselines)"
        )
        print(
            "reported-leak layered-detection={}/{} source-only-misses={} "
            "availability-recoveries={}".format(
                result["layered_detected_leaks"],
                result["leak_cases"],
                result["source_only_missed_leaks"],
                result["availability_recovered_leaks"],
            )
        )
        print(
            "known-static-false-positive-boundaries={}/{}".format(
                result["known_static_false_positive_boundaries"],
                result["safe_cases"],
            )
        )
        for row in result["results"]:
            print(
                "{} {} static={} availability={}".format(
                    "PASS" if row["baseline_match"] else "FAIL",
                    row["id"],
                    row["actual_static_codes"],
                    row["actual_availability_codes"],
                )
            )
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
