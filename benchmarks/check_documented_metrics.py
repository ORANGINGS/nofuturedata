"""Fail when reviewer-facing headline metrics drift from the live evaluator.

The research docs intentionally contain concrete benchmark numbers so a reviewer
can assess the current evidence without running code first. Those numbers are
useful only if they stay synchronized with the executable evaluation suite. This
check derives the current values from ``run_evaluation`` and verifies visible
headline fragments in README, the research brief, the evaluation note, and the
landing page.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from run_evaluation import run as run_evaluation


ROOT = Path(__file__).parents[1]


def _required_fragments(result: dict[str, Any]) -> dict[str, list[str]]:
    summary = result["summary"]
    conformance = result["conformance"]
    notebooks = result["notebook_corpus"]
    downstream = result["downstream_metric_inflation"]
    external = result["external_reproductions"]
    external_metrics = external["observed_current_metrics"]
    reported = result["reported_cases"]

    conformance_score = summary["conformance_exact_cases"]
    notebook_score = (
        summary["notebook_cases_passed"],
        summary["notebook_cases_total"],
        summary["notebook_paired_rules"],
        summary["notebook_shipped_rules"],
    )
    mutation = (
        summary["mutation_validity_checks_passed"],
        summary["mutation_validity_checks_total"],
    )
    sensitivity = (
        summary["intervention_sensitivity_checks_passed"],
        summary["intervention_sensitivity_checks_total"],
    )
    behavioral = (
        summary["behavioral_generalization_matched"],
        summary["behavioral_generalization_cases"],
        summary["behavioral_generalization_detected_leaks"],
        summary["behavioral_generalization_leak_cases"],
        summary["behavioral_generalization_clean_safe_cases"],
        summary["behavioral_generalization_safe_cases"],
    )
    revision = (
        summary["revision_vintage_checks_passed"],
        summary["revision_vintage_checks_total"],
    )
    revision_property = (
        summary["revision_property_checks_passed"],
        summary["revision_property_checks_total"],
    )
    external_source = external_metrics["detected_leaks"]
    external_assisted = external_metrics["assisted_detected_leaks"]
    external_leaks = external["leak_cases"]
    external_safe = external["safe_cases"]
    reported_score = (reported["baseline_matches"], reported["cases"])
    reported_leaks = (reported["layered_detected_leaks"], reported["leak_cases"])
    reported_false_positive_boundaries = (
        reported["known_static_false_positive_boundaries"],
        reported["safe_cases"],
    )
    causal_r2 = downstream["causal_metrics"]["r2"]
    leaking_r2 = downstream["leaking_metrics"]["r2"]
    r2_inflation = downstream["r2_inflation"]
    rmse_ratio = downstream["rmse_ratio_leak_over_causal"]
    downstream_checks = (
        summary["downstream_checks_passed"],
        summary["downstream_checks_total"],
    )

    return {
        "README.md": [
            (
                f"current corpus contains {conformance['cases']} independently checked cases: "
                f"{conformance['leak_cases']} planted leaks and"
            ),
            f"{conformance['safe_cases']} safe controls.",
            (
                f"Current notebook-fixture result: **{notebook_score[0]}/{notebook_score[1]} "
                f"cases pass across {notebook_score[2]}/{notebook_score[3]} paired semantic"
            ),
            f"Current mutation-validity result: **{mutation[0]}/{mutation[1]} checks passing**.",
            f"current result is **{sensitivity[0]}/{sensitivity[1]} checks passing**",
            (
                f"**R² {causal_r2:.3f}** vs leaked **{leaking_r2:.3f}** "
                f"(Δ **{r2_inflation:+.3f}**)"
            ),
            (
                f"Real-pandas behavioral transfer: **{behavioral[0]}/{behavioral[1]} cases match**; "
                f"runtime checks detect {behavioral[2]}/{behavioral[3]} leaks and keep "
                f"{behavioral[4]}/{behavioral[5]} safe controls clean."
            ),
            f"current deterministic result is **{revision[0]}/{revision[1]} checks passing**",
            (
                f"Hypothesis property result: **{revision_property[0]}/{revision_property[1]} "
                f"invariant evaluations pass** across {summary['revision_property_examples']} "
                "generated examples."
            ),
            f"source-only scanner detects {external_source} of {external_leaks}",
            f"keeps all {external_safe} safe controls clean",
            f"it detects {external_assisted} of {external_leaks}.",
            (
                "GitHub-reported regression result: "
                f"**{reported_score[0]}/{reported_score[1]} reviewed baselines match**"
            ),
            f"checks surface {reported_leaks[0]}/{reported_leaks[1]} reported leaks",
        ],
        "docs/EVALUATION.md": [
            f"exact case match: **{conformance_score}**",
            (
                f"Current notebook result: **{notebook_score[0]}/{notebook_score[1]} cases pass "
                f"across {notebook_score[2]}/{notebook_score[3]} paired semantic rules**."
            ),
            f"Current result: **{mutation[0]}/{mutation[1]} checks pass**.",
            f"Current result: **{sensitivity[0]}/{sensitivity[1]} checks pass**.",
            f"The R² inflation is **{r2_inflation:+.3f}**",
            f"the leaked RMSE is **{rmse_ratio:.3f}×**",
            (
                f"All **{downstream_checks[0]}/{downstream_checks[1]} acceptance checks pass**"
            ),
            (
                f"Behavioral-transfer result: **{behavioral[0]}/{behavioral[1]} executable pandas "
                "cases match the declared causal labels**."
            ),
            (
                f"Current result: **{revision[0]}/{revision[1]} checks pass across "
                f"{summary['revision_vintage_trials']} generated trials**."
            ),
            (
                f"Property-based result: **{revision_property[0]}/{revision_property[1]} invariant "
                f"evaluations pass across {summary['revision_property_examples']} Hypothesis examples**."
            ),
            f"documented leak cases: **{external_leaks}**",
            f"detected by current static scanner: **{external_source}/{external_leaks}",
            (
                "detected with declared time-series context where applicable: "
                f"**{external_assisted}/{external_leaks}"
            ),
            f"safe controls left clean: **{external_safe}/{external_safe}",
            (
                "Current reported-case result: "
                f"**{reported_score[0]}/{reported_score[1]} reviewed baselines match**."
            ),
            f"layered checks surface **{reported_leaks[0]}/{reported_leaks[1]}** reported leak cases",
            (
                "known static false-positive boundaries: "
                f"**{reported_false_positive_boundaries[0]}/{reported_false_positive_boundaries[1]}**"
            ),
        ],
        "docs/RESEARCH_BRIEF.md": [
            f"| Static conformance corpus | **{conformance_score} exact match**",
            (
                f"| Jupyter fixture corpus | **{notebook_score[0]}/{notebook_score[1]} cases; "
                f"{notebook_score[2]}/{notebook_score[3]} rule pairs**"
            ),
            f"| Mutation intervention validity | **{mutation[0]}/{mutation[1]} checks pass**",
            f"| Intervention sensitivity | **{sensitivity[0]}/{sensitivity[1]} checks pass**",
            (
                f"| Synthetic downstream impact | **R² {causal_r2:.3f} → "
                f"{leaking_r2:.3f} ({r2_inflation:+.3f})**"
            ),
            f"| Real-pandas behavioral transfer | **{behavioral[0]}/{behavioral[1]} cases match**",
            f"| Revision/vintage robustness | **{revision[0]}/{revision[1]} checks pass**",
            (
                "| Revision/vintage property search | "
                f"**{revision_property[0]}/{revision_property[1]} invariant evaluations pass**"
            ),
            f"| External documented leaks | **{external_source}/{external_leaks} detected**",
            (
                "| External + declared temporal context | "
                f"**{external_assisted}/{external_leaks} detected**"
            ),
            f"| External safe controls | **{external_safe}/{external_safe} clean**",
            (
                "| GitHub-reported cases | "
                f"**{reported_score[0]}/{reported_score[1]} reviewed baselines**"
            ),
        ],
        "docs/index.html": [
            f'<span class="score">{conformance_score}</span>',
            (
                f'<span class="score">{notebook_score[0]}/{notebook_score[1]} · '
                f'{notebook_score[2]}/{notebook_score[3]}</span>'
            ),
            f'<span class="score">{mutation[0]}/{mutation[1]}</span>',
            f'<span class="score">{sensitivity[0]}/{sensitivity[1]}</span>',
            f'<span class="score">{causal_r2:.3f} → {leaking_r2:.3f}</span>',
            f'<span class="score">{behavioral[0]}/{behavioral[1]}</span>',
            f'<span class="score">{revision[0]}/{revision[1]}</span>',
            f'<span class="score">{revision_property[0]}/{revision_property[1]}</span>',
            (
                f'<span class="score">{external_source}/{external_leaks} → '
                f'{external_assisted}/{external_leaks}</span>'
            ),
            (
                f'<span class="score">{reported_leaks[0]}/{reported_leaks[1]} · '
                f'{reported_false_positive_boundaries[0]} FP</span>'
            ),
        ],
    }


def run() -> dict[str, Any]:
    evaluation = run_evaluation()
    requirements = _required_fragments(evaluation)
    missing: list[dict[str, str]] = []
    checked = 0
    for relative_path, fragments in requirements.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in fragments:
            checked += 1
            if fragment not in text:
                missing.append({"path": relative_path, "fragment": fragment})
    return {
        "schema_version": "nofuturedata-documented-metrics-v1",
        "ok": not missing,
        "files": len(requirements),
        "fragments_checked": checked,
        "missing": missing,
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
            f"NoFutureData documented metrics: {state} "
            f"({result['files']} files, {result['fragments_checked']} headline fragments)"
        )
        for missing in result["missing"]:
            print(f"MISSING {missing['path']}: {missing['fragment']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
