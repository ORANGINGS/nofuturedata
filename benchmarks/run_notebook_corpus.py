"""Validate the checked-in Jupyter fixture corpus against exact rule/cell expectations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from nofuturedata import audit_notebook_source
from run_benchmark import _shipped_semantic_rule_codes


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "notebooks" / "fixtures" / "manifest.json"


def build_notebook(case: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical tiny notebook represented by one manifest case."""

    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": (
                    f"# {case['rule']} {case['kind']} fixture\n\n"
                    "Synthetic NoFutureData notebook conformance fixture."
                ),
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": case["source"],
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _finding_signature(report: Any) -> list[dict[str, Any]]:
    return [
        {
            "code": finding.code,
            "cell": finding.details.get("cell"),
            "line": finding.line,
        }
        for finding in report.findings
    ]


def run() -> dict[str, Any]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = payload["cases"]
    shipped_rules = _shipped_semantic_rule_codes()
    results: list[dict[str, Any]] = []
    pair_counts = {
        rule: {"leak": 0, "safe": 0}
        for rule in shipped_rules
    }
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    contextual_source_only_clean = 0

    for case in cases:
        case_id = case["id"]
        relative_path = case["path"]
        path = ROOT / relative_path
        fixture_root = (ROOT / "notebooks" / "fixtures").resolve()
        resolved_path = path.resolve()
        duplicate_id = case_id in seen_ids
        duplicate_path = relative_path in seen_paths
        seen_ids.add(case_id)
        seen_paths.add(relative_path)

        exists = path.is_file()
        actual_notebook = json.loads(path.read_text(encoding="utf-8")) if exists else None
        canonical_notebook = build_notebook(case)
        canonical = actual_notebook == canonical_notebook
        report = audit_notebook_source(
            json.dumps(actual_notebook) if actual_notebook is not None else "{}",
            filename=relative_path,
            temporal_context=case.get("temporal_context"),
        )
        actual = _finding_signature(report)
        expected = case["expected"]
        rule = case["rule"]
        kind = case["kind"]
        expected_codes = [item.get("code") for item in expected]
        case_contract_ok = bool(
            kind in {"leak", "safe"}
            and resolved_path.is_relative_to(fixture_root)
            and (
                (kind == "leak" and expected_codes == [rule])
                or (kind == "safe" and expected == [])
            )
        )
        path_metadata_ok = all(
            finding.details.get("path") == relative_path
            for finding in report.findings
        )

        source_only_clean = True
        if case.get("temporal_context") == "time_series" and case["kind"] == "leak":
            source_only = audit_notebook_source(
                json.dumps(actual_notebook) if actual_notebook is not None else "{}",
                filename=relative_path,
            )
            source_only_clean = source_only.ok
            contextual_source_only_clean += int(source_only_clean)

        if rule in pair_counts and kind in pair_counts[rule]:
            pair_counts[rule][kind] += 1

        ok = bool(
            exists
            and canonical
            and not duplicate_id
            and not duplicate_path
            and case_contract_ok
            and actual == expected
            and path_metadata_ok
            and source_only_clean
        )
        results.append(
            {
                "id": case_id,
                "path": relative_path,
                "rule": rule,
                "kind": kind,
                "ok": ok,
                "expected": expected,
                "actual": actual,
                "exists": exists,
                "canonical": canonical,
                "case_contract_ok": case_contract_ok,
                "path_metadata_ok": path_metadata_ok,
                "contextual_source_only_clean": source_only_clean,
            }
        )

    paired_rules = sorted(
        rule
        for rule, counts in pair_counts.items()
        if counts == {"leak": 1, "safe": 1}
    )
    missing_or_duplicated_pairs = sorted(set(shipped_rules) - set(paired_rules))
    passed = sum(result["ok"] for result in results)
    leak_cases = sum(case["kind"] == "leak" for case in cases)
    safe_cases = sum(case["kind"] == "safe" for case in cases)
    contextual_leaks = sum(
        case.get("temporal_context") == "time_series" and case["kind"] == "leak"
        for case in cases
    )
    coverage_ok = not missing_or_duplicated_pairs and len(paired_rules) == len(shipped_rules)

    return {
        "schema_version": payload["schema_version"],
        "ok": passed == len(cases) and coverage_ok,
        "passed": passed,
        "cases": len(cases),
        "leak_cases": leak_cases,
        "safe_cases": safe_cases,
        "shipped_semantic_rules": shipped_rules,
        "paired_rules": paired_rules,
        "missing_or_duplicated_pairs": missing_or_duplicated_pairs,
        "contextual_leaks": contextual_leaks,
        "contextual_source_only_clean": contextual_source_only_clean,
        "results": results,
        "claim_limit": (
            "These fixtures are deterministic conformance examples for the shipped rules; "
            "they are not estimates of real-world notebook leakage prevalence or recall."
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
            "NoFutureData notebook corpus: {} ({}/{} cases; {}/{} paired semantic rules)".format(
                state,
                result["passed"],
                result["cases"],
                len(result["paired_rules"]),
                len(result["shipped_semantic_rules"]),
            )
        )
        print(
            "leaks={} safe={} contextual-source-only-clean={}/{}".format(
                result["leak_cases"],
                result["safe_cases"],
                result["contextual_source_only_clean"],
                result["contextual_leaks"],
            )
        )
        for row in result["results"]:
            print(f"{'PASS' if row['ok'] else 'FAIL':4} {row['id']} -> {row['actual']}")
        if result["missing_or_duplicated_pairs"]:
            print("PAIR COVERAGE FAIL: " + ", ".join(result["missing_or_duplicated_pairs"]))
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
