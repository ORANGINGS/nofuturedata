"""Run the public planted-leak corpus used by NoFutureData CI.

This benchmark is intentionally small and deterministic. It is not a claim of
recall on arbitrary temporal leakage. Its purpose is to make the shipped static
rules and their safe controls independently reproducible.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from nofuturedata import audit_python_source


CORPUS = Path(__file__).with_name("corpus.json")
AUDIT_SOURCE = Path(__file__).parents[1] / "src" / "nofuturedata" / "audit.py"


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return numerator / denominator if denominator else 1.0


def _shipped_semantic_rule_codes() -> list[str]:
    """Discover semantic SRC rules from the implementation itself.

    ``SRC000`` is the parser/configuration failure sentinel rather than a
    temporal pattern rule, so the planted leak corpus covers ``SRC001+``.
    Reading the source makes a newly added semantic rule fail this benchmark
    until an exact expected case is committed for it.
    """

    tree = ast.parse(AUDIT_SOURCE.read_text(encoding="utf-8"), filename=str(AUDIT_SOURCE))
    codes = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.fullmatch(r"SRC\d{3}", node.value)
    }
    return sorted(codes - {"SRC000"})


def run() -> dict[str, object]:
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    passed = 0
    leak_cases = 0
    safe_cases = 0
    leak_cases_detected = 0
    safe_cases_clean = 0
    expected_pairs: set[tuple[str, str]] = set()
    actual_pairs: set[tuple[str, str]] = set()
    for case in cases:
        expected = sorted(case["expected"])
        temporal_context = case.get("temporal_context")
        actual = sorted(
            item.code
            for item in audit_python_source(
                case["source"], temporal_context=temporal_context
            ).findings
        )
        ok = actual == expected
        if ok:
            passed += 1
        if case["kind"] == "leak":
            leak_cases += 1
            leak_cases_detected += int(bool(actual))
        else:
            safe_cases += 1
            safe_cases_clean += int(not actual)
        expected_pairs.update((case["id"], code) for code in expected)
        actual_pairs.update((case["id"], code) for code in actual)
        rows.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "temporal_context": temporal_context,
                "expected": expected,
                "actual": actual,
                "pass": ok,
            }
        )

    true_positive_pairs = expected_pairs & actual_pairs
    false_positive_pairs = actual_pairs - expected_pairs
    false_negative_pairs = expected_pairs - actual_pairs
    precision = _ratio(
        len(true_positive_pairs),
        len(true_positive_pairs) + len(false_positive_pairs),
    )
    recall = _ratio(
        len(true_positive_pairs),
        len(true_positive_pairs) + len(false_negative_pairs),
    )
    f1 = _ratio(2 * precision * recall, precision + recall)
    rule_codes = sorted({code for _, code in expected_pairs | actual_pairs})
    per_rule = {}
    for code in rule_codes:
        expected_for_rule = {pair for pair in expected_pairs if pair[1] == code}
        actual_for_rule = {pair for pair in actual_pairs if pair[1] == code}
        tp = len(expected_for_rule & actual_for_rule)
        fp = len(actual_for_rule - expected_for_rule)
        fn = len(expected_for_rule - actual_for_rule)
        rule_precision = _ratio(tp, tp + fp)
        rule_recall = _ratio(tp, tp + fn)
        per_rule[code] = {
            "expected_cases": len(expected_for_rule),
            "actual_cases": len(actual_for_rule),
            "true_positive_cases": tp,
            "false_positive_cases": fp,
            "false_negative_cases": fn,
            "precision": rule_precision,
            "recall": rule_recall,
            "f1": _ratio(2 * rule_precision * rule_recall, rule_precision + rule_recall),
        }

    shipped_semantic_rules = _shipped_semantic_rule_codes()
    covered_rules = sorted({code for _, code in expected_pairs})
    missing_rule_coverage = sorted(set(shipped_semantic_rules) - set(covered_rules))
    rule_coverage_ok = not missing_rule_coverage

    return {
        "schema_version": "nofuturedata-benchmark-v2",
        "cases": len(cases),
        "leak_cases": leak_cases,
        "safe_cases": safe_cases,
        "passed": passed,
        "failed": len(cases) - passed,
        "ok": passed == len(cases) and rule_coverage_ok,
        "metrics": {
            "exact_case_accuracy": _ratio(passed, len(cases)),
            "finding_precision": precision,
            "finding_recall": recall,
            "finding_f1": f1,
            "leak_case_detection_rate": _ratio(leak_cases_detected, leak_cases),
            "safe_case_specificity": _ratio(safe_cases_clean, safe_cases),
            "true_positive_findings": len(true_positive_pairs),
            "false_positive_findings": len(false_positive_pairs),
            "false_negative_findings": len(false_negative_pairs),
        },
        "per_rule": per_rule,
        "rule_coverage": {
            "shipped_semantic_rules": shipped_semantic_rules,
            "covered_rules": covered_rules,
            "missing_rules": missing_rule_coverage,
            "ok": rule_coverage_ok,
        },
        "results": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        metrics = result["metrics"]
        print(
            f"NoFutureData planted-leak corpus: {result['passed']}/{result['cases']} pass "
            f"({result['leak_cases']} leak, {result['safe_cases']} safe controls)"
        )
        print(
            "finding precision={:.3f} recall={:.3f} f1={:.3f}; "
            "leak detection={:.3f} specificity={:.3f}".format(
                metrics["finding_precision"],
                metrics["finding_recall"],
                metrics["finding_f1"],
                metrics["leak_case_detection_rate"],
                metrics["safe_case_specificity"],
            )
        )
        coverage = result["rule_coverage"]
        print(
            "semantic rule coverage={}/{}".format(
                len(coverage["covered_rules"]),
                len(coverage["shipped_semantic_rules"]),
            )
        )
        if coverage["missing_rules"]:
            print("missing semantic rule cases=" + ",".join(coverage["missing_rules"]))
        for row in result["results"]:
            marker = "PASS" if row["pass"] else "FAIL"
            print(f"{marker:4}  {row['id']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
