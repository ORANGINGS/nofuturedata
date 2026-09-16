"""Run the public planted-leak corpus used by NoFutureData CI.

This benchmark is intentionally small and deterministic. It is not a claim of
recall on arbitrary temporal leakage. Its purpose is to make the shipped static
rules and their safe controls independently reproducible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nofuturedata import audit_python_source


CORPUS = Path(__file__).with_name("corpus.json")


def run() -> dict[str, object]:
    cases = json.loads(CORPUS.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    passed = 0
    leak_cases = 0
    safe_cases = 0
    for case in cases:
        expected = sorted(case["expected"])
        actual = sorted(item.code for item in audit_python_source(case["source"]).findings)
        ok = actual == expected
        if ok:
            passed += 1
        if case["kind"] == "leak":
            leak_cases += 1
        else:
            safe_cases += 1
        rows.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "expected": expected,
                "actual": actual,
                "pass": ok,
            }
        )
    return {
        "schema_version": "nofuturedata-benchmark-v1",
        "cases": len(cases),
        "leak_cases": leak_cases,
        "safe_cases": safe_cases,
        "passed": passed,
        "failed": len(cases) - passed,
        "ok": passed == len(cases),
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
        print(
            f"NoFutureData planted-leak corpus: {result['passed']}/{result['cases']} pass "
            f"({result['leak_cases']} leak, {result['safe_cases']} safe controls)"
        )
        for row in result["results"]:
            marker = "PASS" if row["pass"] else "FAIL"
            print(f"{marker:4}  {row['id']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
