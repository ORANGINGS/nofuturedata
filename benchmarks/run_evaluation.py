"""Run the complete reproducible NoFutureData evaluation suite.

The suite intentionally mixes nine evaluation components spanning static,
behavioral, and availability evidence: planted static conformance,
static-vs-runtime method ablation, a synthetic downstream metric-inflation
demonstration, intervention-validity checks, intervention sensitivity,
real-pandas behavioral transfer, fixed-seed revision/vintage robustness,
property-based revision search, and documentation-backed external reproductions.
A PASS means each reviewed benchmark contract still holds; it does not mean the
external scanner has perfect recall.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

import nofuturedata
from behavioral_generalization import run as run_behavioral_generalization
from downstream_metric_inflation import run as run_downstream_metric_inflation
from intervention_sensitivity import run as run_intervention_sensitivity
from method_comparison import run as run_method_comparison
from mutation_validity import run as run_mutation_validity
from property_revision_vintage import run as run_property_revision_vintage
from revision_vintage_robustness import run as run_revision_vintage_robustness
from run_benchmark import run as run_conformance
from run_external_reproductions import run as run_external_reproductions


def run() -> dict[str, Any]:
    conformance = run_conformance()
    methods = run_method_comparison()
    downstream_impact = run_downstream_metric_inflation()
    mutation_validity = run_mutation_validity()
    intervention_sensitivity = run_intervention_sensitivity()
    behavioral_generalization = run_behavioral_generalization()
    revision_vintage = run_revision_vintage_robustness()
    revision_property = run_property_revision_vintage()
    external = run_external_reproductions()
    external_metrics = external["observed_current_metrics"]
    method_metrics = methods["metrics"]
    downstream_checks = downstream_impact["checks"]
    downstream_checks_passed = sum(bool(value) for value in downstream_checks.values())
    downstream_checks_total = len(downstream_checks)
    mutation_checks = mutation_validity["checks"]
    mutation_checks_passed = sum(bool(value) for value in mutation_checks.values())
    mutation_checks_total = len(mutation_checks)
    return {
        "schema_version": "nofuturedata-evaluation-suite-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "package_version": nofuturedata.__version__,
        "ok": bool(
            conformance["ok"]
            and methods["ok"]
            and downstream_impact["ok"]
            and mutation_validity["ok"]
            and intervention_sensitivity["ok"]
            and behavioral_generalization["ok"]
            and revision_vintage["ok"]
            and revision_property["ok"]
            and external["ok"]
        ),
        "summary": {
            "conformance_exact_cases": f"{conformance['passed']}/{conformance['cases']}",
            "conformance_safe_specificity": conformance["metrics"]["safe_case_specificity"],
            "method_static_recall": method_metrics["static"]["recall"],
            "method_runtime_union_recall": method_metrics["runtime_union"]["recall"],
            "downstream_causal_r2": downstream_impact["causal_metrics"]["r2"],
            "downstream_leaking_r2": downstream_impact["leaking_metrics"]["r2"],
            "downstream_r2_inflation": downstream_impact["r2_inflation"],
            "downstream_causal_rmse": downstream_impact["causal_metrics"]["rmse"],
            "downstream_leaking_rmse": downstream_impact["leaking_metrics"]["rmse"],
            "downstream_rmse_ratio": downstream_impact[
                "rmse_ratio_leak_over_causal"
            ],
            "downstream_checks_passed": downstream_checks_passed,
            "downstream_checks_total": downstream_checks_total,
            "mutation_validity_all_checks_pass": mutation_validity["ok"],
            "mutation_validity_checks_passed": mutation_checks_passed,
            "mutation_validity_checks_total": mutation_checks_total,
            "intervention_sensitivity_checks_passed": intervention_sensitivity["passed"],
            "intervention_sensitivity_checks_total": intervention_sensitivity["checks"],
            "intervention_sensitivity_domains": intervention_sensitivity["domains"],
            "intervention_sensitivity_cut_points": len(
                intervention_sensitivity["cut_points"]
            ),
            "intervention_sensitivity_strengths": len(intervention_sensitivity["strengths"]),
            "behavioral_generalization_matched": behavioral_generalization["matched"],
            "behavioral_generalization_cases": behavioral_generalization["cases"],
            "behavioral_generalization_detected_leaks": behavioral_generalization[
                "detected_leaks"
            ],
            "behavioral_generalization_leak_cases": behavioral_generalization["leak_cases"],
            "behavioral_generalization_clean_safe_cases": behavioral_generalization[
                "clean_safe_cases"
            ],
            "behavioral_generalization_safe_cases": behavioral_generalization["safe_cases"],
            "behavioral_generalization_pandas_version": behavioral_generalization[
                "pandas_version"
            ],
            "revision_vintage_checks_passed": revision_vintage["passed"],
            "revision_vintage_checks_total": revision_vintage["checks"],
            "revision_vintage_trials": revision_vintage["trials"],
            "revision_vintage_seed": revision_vintage["seed"],
            "revision_property_checks_passed": revision_property["passed"],
            "revision_property_checks_total": revision_property["checks"],
            "revision_property_examples": revision_property["examples"],
            "revision_property_invariants": revision_property["invariants_per_example"],
            "revision_property_hypothesis_version": revision_property["hypothesis_version"],
            "external_documented_leak_detection_rate": external_metrics[
                "documented_leak_detection_rate"
            ],
            "external_known_missed_leaks": external_metrics["known_missed_leaks"],
            "external_context_required_misses": external_metrics["context_required_misses"],
            "external_context_detected_leaks": external_metrics["context_detected_leaks"],
            "external_context_safe_specificity": external_metrics["context_safe_specificity"],
            "external_assisted_documented_leak_detection_rate": external_metrics[
                "assisted_documented_leak_detection_rate"
            ],
            "external_assisted_detected_leaks": external_metrics[
                "assisted_detected_leaks"
            ],
            "external_assisted_safe_specificity": external_metrics[
                "assisted_safe_specificity"
            ],
            "external_safe_specificity": external_metrics["safe_case_specificity"],
            "external_source_projects": external["source_projects"],
        },
        "conformance": conformance,
        "method_comparison": methods,
        "downstream_metric_inflation": downstream_impact,
        "mutation_validity": mutation_validity,
        "intervention_sensitivity": intervention_sensitivity,
        "behavioral_generalization": behavioral_generalization,
        "revision_vintage_robustness": revision_vintage,
        "revision_vintage_property": revision_property,
        "external_reproductions": external,
        "claim_limit": (
            "PASS means the reviewed deterministic contracts reproduced. The external corpus is "
            "small and curated, and its observed rates are not population-level estimates of "
            "real-world recall or specificity."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the full machine-readable report")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        summary = result["summary"]
        state = "PASS" if result["ok"] else "FAIL"
        print(f"NoFutureData evaluation suite: {state} ({result['package_version']})")
        print(
            "conformance={} safe-specificity={:.3f}".format(
                summary["conformance_exact_cases"],
                summary["conformance_safe_specificity"],
            )
        )
        print(
            "method-ablation static-recall={:.3f} runtime-union-recall={:.3f}".format(
                summary["method_static_recall"],
                summary["method_runtime_union_recall"],
            )
        )
        print(
            "downstream-impact causal-r2={:.3f} leaked-r2={:.3f} delta={:+.3f} "
            "rmse-ratio={:.3f} checks={}/{}".format(
                summary["downstream_causal_r2"],
                summary["downstream_leaking_r2"],
                summary["downstream_r2_inflation"],
                summary["downstream_rmse_ratio"],
                summary["downstream_checks_passed"],
                summary["downstream_checks_total"],
            )
        )
        print(
            "mutation-validity={}/{} ({})".format(
                summary["mutation_validity_checks_passed"],
                summary["mutation_validity_checks_total"],
                "PASS" if summary["mutation_validity_all_checks_pass"] else "FAIL",
            )
        )
        print(
            "intervention-sensitivity={}/{} ({} domains, {} cuts, {} strengths)".format(
                summary["intervention_sensitivity_checks_passed"],
                summary["intervention_sensitivity_checks_total"],
                summary["intervention_sensitivity_domains"],
                summary["intervention_sensitivity_cut_points"],
                summary["intervention_sensitivity_strengths"],
            )
        )
        print(
            "behavioral-generalization={}/{} (pandas {}; leaks {}/{}, safe {}/{})".format(
                summary["behavioral_generalization_matched"],
                summary["behavioral_generalization_cases"],
                summary["behavioral_generalization_pandas_version"],
                summary["behavioral_generalization_detected_leaks"],
                summary["behavioral_generalization_leak_cases"],
                summary["behavioral_generalization_clean_safe_cases"],
                summary["behavioral_generalization_safe_cases"],
            )
        )
        print(
            "revision-vintage-robustness={}/{} ({} trials, seed={})".format(
                summary["revision_vintage_checks_passed"],
                summary["revision_vintage_checks_total"],
                summary["revision_vintage_trials"],
                summary["revision_vintage_seed"],
            )
        )
        print(
            "revision-vintage-property={}/{} ({} examples, {} invariants, Hypothesis {})".format(
                summary["revision_property_checks_passed"],
                summary["revision_property_checks_total"],
                summary["revision_property_examples"],
                summary["revision_property_invariants"],
                summary["revision_property_hypothesis_version"],
            )
        )
        print(
            "external documented-leak-detection={:.3f} known-misses={} safe-specificity={:.3f}".format(
                summary["external_documented_leak_detection_rate"],
                summary["external_known_missed_leaks"],
                summary["external_safe_specificity"],
            )
        )
        print(
            "external context-assisted-detection={:.3f} safe-specificity={:.3f}".format(
                summary["external_assisted_documented_leak_detection_rate"],
                summary["external_assisted_safe_specificity"],
            )
        )
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
