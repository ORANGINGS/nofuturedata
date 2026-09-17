"""Generative robustness checks for append-only revision/vintage contracts.

This benchmark uses a fixed seed so CI and reviewers reproduce the exact same
cases.  Each trial generates several logical observations with one or more
unique vintages with explicit eligibility delays, verifies that row order does
not change acceptance, tests point-in-time vintage selection before and after
eligibility, then injects one duplicate ``known_at`` for the same revision key
and requires the manifest audit to emit ``REV001``.

The experiment is intentionally dependency-free.  It is property-style
generative testing over a deterministic sample, not a proof over all possible
revision histories.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nofuturedata import audit_manifest, point_in_time_join


DEFAULT_SEED = 20260916
DEFAULT_TRIALS = 24


def _manifest_payload(dataset_name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "datasets": [
            {
                "path": dataset_name,
                "format": "csv",
                "event_time": {
                    "column": "event_time",
                    "semantics": "observation_period",
                },
                "known_at": {
                    "column": "known_at",
                    "semantics": "first_observed_by_consumer",
                },
                "eligible_from": {
                    "policy": "explicit_column",
                    "column": "eligible_from",
                },
                "timezone": "offset-aware",
                "revision": {
                    "policy": "append_only_vintages",
                    "key": ["series_id", "event_time"],
                },
                "null_reason": {"policy": "not_applicable"},
            }
        ],
    }


def _write_case(root: Path, stem: str, rows: list[dict[str, str]]) -> Path:
    dataset = root / f"{stem}.csv"
    with dataset.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "series_id",
                "event_time",
                "value",
                "known_at",
                "eligible_from",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    manifest = root / f"{stem}.json"
    manifest.write_text(
        json.dumps(_manifest_payload(dataset.name), indent=2),
        encoding="utf-8",
    )
    return manifest


def _generate_rows(rng: random.Random, trial: int) -> list[dict[str, str]]:
    series_count = rng.randint(1, 4)
    observations_per_series = rng.randint(1, 4)
    rows: list[dict[str, str]] = []
    base_known = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc)

    for series_index in range(series_count):
        series_id = f"S{trial:02d}_{series_index}"
        for observation_index in range(observations_per_series):
            event_day = 1 + observation_index * 7
            event_time = f"2026-01-{event_day:02d}"
            vintage_count = rng.randint(1, 4)
            known_start = base_known + timedelta(
                days=trial * 11 + series_index * 5 + observation_index * 2
            )
            for vintage_index in range(vintage_count):
                known_at = known_start + timedelta(hours=vintage_index * 13 + 1)
                eligible_from = known_at + timedelta(minutes=rng.randint(5, 90))
                rows.append(
                    {
                        "series_id": series_id,
                        "event_time": event_time,
                        "value": f"{rng.uniform(-5.0, 5.0):.6f}",
                        "known_at": known_at.isoformat(),
                        "eligible_from": eligible_from.isoformat(),
                    }
                )
    return rows


def _codes(path: Path) -> list[str]:
    return [finding.code for finding in audit_manifest(path).findings]


def _normalized_values(values, pd) -> list[str | None]:
    return [None if pd.isna(value) else str(value) for value in values]


def _selection_properties(
    rows: list[dict[str, str]], shuffled: list[dict[str, str]]
) -> tuple[bool, bool, dict[str, Any]]:
    import pandas as pd

    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (row["series_id"], row["event_time"])
        grouped.setdefault(key, []).append(row)

    left_rows: list[dict[str, str]] = []
    expected: list[str | None] = []
    phases: list[str] = []
    case_index = 0
    for key, vintages in grouped.items():
        ordered_vintages = sorted(
            vintages, key=lambda row: datetime.fromisoformat(row["eligible_from"])
        )
        previous_value: str | None = None
        for vintage in ordered_vintages:
            known = datetime.fromisoformat(vintage["known_at"])
            eligible = datetime.fromisoformat(vintage["eligible_from"])
            before_eligible = known + (eligible - known) / 2
            just_after_eligible = eligible + timedelta(seconds=1)

            left_rows.append(
                {
                    "case_id": str(case_index),
                    "series_id": key[0],
                    "event_time": key[1],
                    "decision_time": before_eligible.isoformat(),
                }
            )
            phases.append("pre")
            expected.append(previous_value)
            case_index += 1

            left_rows.append(
                {
                    "case_id": str(case_index),
                    "series_id": key[0],
                    "event_time": key[1],
                    "decision_time": just_after_eligible.isoformat(),
                }
            )
            phases.append("post")
            expected.append(vintage["value"])
            case_index += 1
            previous_value = vintage["value"]

    left = pd.DataFrame(left_rows)
    ordered_right = pd.DataFrame(rows)
    shuffled_right = pd.DataFrame(shuffled)
    join_kwargs = {
        "decision_time": "decision_time",
        "by": ["series_id", "event_time"],
    }
    joined_ordered = point_in_time_join(left, ordered_right, **join_kwargs)
    joined_shuffled = point_in_time_join(left, shuffled_right, **join_kwargs)

    ordered_values = _normalized_values(joined_ordered["value"].tolist(), pd)
    shuffled_values = _normalized_values(joined_shuffled["value"].tolist(), pd)
    pre_indices = [index for index, phase in enumerate(phases) if phase == "pre"]
    post_indices = [index for index, phase in enumerate(phases) if phase == "post"]

    eligibility_delay_correct = all(
        ordered_values[index] == expected[index] for index in pre_indices
    )
    revision_order_correct = (
        ordered_values == shuffled_values
        and all(ordered_values[index] == expected[index] for index in post_indices)
    )
    details = {
        "selection_cases": len(left_rows),
        "pre_eligibility_cases": len(pre_indices),
        "post_eligibility_cases": len(post_indices),
    }
    return eligibility_delay_correct, revision_order_correct, details


def run(*, trials: int = DEFAULT_TRIALS, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    if trials <= 0:
        raise ValueError("trials must be positive")

    rng = random.Random(seed)
    ordered_valid = 0
    shuffled_valid = 0
    duplicate_detected = 0
    eligibility_delay_correct = 0
    revision_order_correct = 0
    failures: list[dict[str, Any]] = []
    selection_cases = 0

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for trial in range(trials):
            rows = _generate_rows(rng, trial)

            ordered_manifest = _write_case(root, f"trial_{trial:02d}_ordered", rows)
            ordered_codes = _codes(ordered_manifest)
            if not ordered_codes:
                ordered_valid += 1
            else:
                failures.append(
                    {"trial": trial, "property": "ordered_valid", "codes": ordered_codes}
                )

            shuffled = deepcopy(rows)
            rng.shuffle(shuffled)
            shuffled_manifest = _write_case(
                root, f"trial_{trial:02d}_shuffled", shuffled
            )
            shuffled_codes = _codes(shuffled_manifest)
            if not shuffled_codes:
                shuffled_valid += 1
            else:
                failures.append(
                    {"trial": trial, "property": "shuffled_valid", "codes": shuffled_codes}
                )

            delay_ok, revision_ok, selection_details = _selection_properties(rows, shuffled)
            selection_cases += selection_details["selection_cases"]
            if delay_ok:
                eligibility_delay_correct += 1
            else:
                failures.append(
                    {
                        "trial": trial,
                        "property": "eligibility_delay_selection_correct",
                        **selection_details,
                    }
                )
            if revision_ok:
                revision_order_correct += 1
            else:
                failures.append(
                    {
                        "trial": trial,
                        "property": "revision_order_selection_invariant",
                        **selection_details,
                    }
                )

            duplicate_rows = deepcopy(shuffled)
            duplicated = dict(rng.choice(duplicate_rows))
            duplicated["value"] = f"{float(duplicated['value']) + 0.123456:.6f}"
            duplicate_rows.insert(rng.randrange(len(duplicate_rows) + 1), duplicated)
            duplicate_manifest = _write_case(
                root, f"trial_{trial:02d}_duplicate", duplicate_rows
            )
            duplicate_codes = _codes(duplicate_manifest)
            if "REV001" in duplicate_codes:
                duplicate_detected += 1
            else:
                failures.append(
                    {
                        "trial": trial,
                        "property": "duplicate_known_at_detected",
                        "codes": duplicate_codes,
                    }
                )

    passed = (
        ordered_valid
        + shuffled_valid
        + duplicate_detected
        + eligibility_delay_correct
        + revision_order_correct
    )
    total = trials * 5
    return {
        "schema_version": "nofuturedata-revision-vintage-robustness-v1",
        "ok": passed == total,
        "seed": seed,
        "trials": trials,
        "passed": passed,
        "checks": total,
        "properties": {
            "ordered_unique_vintages_accepted": ordered_valid,
            "shuffled_unique_vintages_accepted": shuffled_valid,
            "duplicate_known_at_detected": duplicate_detected,
            "eligibility_delay_selection_correct": eligibility_delay_correct,
            "revision_order_selection_invariant": revision_order_correct,
        },
        "selection_cases": selection_cases,
        "failures": failures,
        "claim_limit": (
            "Fixed-seed generative coverage tests append-only vintage uniqueness, explicit "
            "eligibility delays, and point-in-time revision selection under row reordering over "
            "a deterministic sample; it is not a proof over all revision histories."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    result = run(trials=args.trials, seed=args.seed)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(
            "NoFutureData revision/vintage robustness: {} ({}/{}, seed={})".format(
                state,
                result["passed"],
                result["checks"],
                result["seed"],
            )
        )
        for name, count in result["properties"].items():
            print(f"{count:2}/{result['trials']}  {name}")
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
