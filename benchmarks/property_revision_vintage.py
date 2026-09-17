"""Property-based search over revision/vintage point-in-time invariants.

The fixed-seed revision benchmark gives reviewers an exactly reproducible sample.
This companion experiment uses Hypothesis to search a wider space and shrink any
counterexample it finds.  Every generated history is checked against five public
behavioral invariants without changing the production implementation.
"""

from __future__ import annotations

import argparse
import csv
import json
import tempfile
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hypothesis import __version__ as hypothesis_version
from hypothesis import given, settings, strategies as st
from nofuturedata import point_in_time_join

from revision_vintage_robustness import (
    _codes,
    _normalized_values,
    _selection_properties,
    _write_case,
)


MAX_EXAMPLES = 64
INVARIANTS = (
    "ordered_unique_vintages_accepted",
    "shuffled_unique_vintages_accepted",
    "duplicate_known_at_detected",
    "eligibility_delay_selection_correct",
    "revision_order_selection_invariant",
    "multi_column_shared_availability_accepted",
    "multi_column_duplicate_known_at_detected",
    "null_value_with_reason_accepted",
    "null_value_without_reason_detected",
    "missing_revision_key_detected",
    "multi_column_null_revision_selection_invariant",
    "null_by_key_join_rejected",
)


@st.composite
def _vintage_histories(draw):
    series_count = draw(st.integers(min_value=1, max_value=3))
    observations_per_series = draw(st.integers(min_value=1, max_value=3))
    base_day_offset = draw(st.integers(min_value=0, max_value=30))
    rows: list[dict[str, str]] = []
    base_known = datetime(2026, 1, 2, 12, 0, tzinfo=timezone.utc) + timedelta(
        days=base_day_offset
    )

    for series_index in range(series_count):
        series_id = f"P{series_index}"
        for observation_index in range(observations_per_series):
            event_time = f"2026-01-{1 + observation_index * 7:02d}"
            vintage_count = draw(st.integers(min_value=1, max_value=4))
            delays = draw(
                st.lists(
                    st.integers(min_value=1, max_value=180),
                    min_size=vintage_count,
                    max_size=vintage_count,
                )
            )
            known_start = base_known + timedelta(
                days=series_index * 5 + observation_index * 2
            )
            for vintage_index, delay_minutes in enumerate(delays):
                # Four-hour spacing is wider than the maximum eligibility delay,
                # so each logical observation has a unique availability order.
                known_at = known_start + timedelta(hours=vintage_index * 4)
                eligible_from = known_at + timedelta(minutes=delay_minutes)
                rows.append(
                    {
                        "series_id": series_id,
                        "event_time": event_time,
                        "value": f"{series_index}:{observation_index}:{vintage_index}",
                        "known_at": known_at.isoformat(),
                        "eligible_from": eligible_from.isoformat(),
                    }
                )

    permutation = draw(st.permutations(tuple(range(len(rows)))))
    duplicate_index = draw(st.integers(min_value=0, max_value=len(rows) - 1))
    duplicate_position = draw(st.integers(min_value=0, max_value=len(rows)))
    shuffled = [deepcopy(rows[index]) for index in permutation]
    return rows, shuffled, duplicate_index, duplicate_position


def _edge_manifest_payload(dataset_name: str) -> dict[str, Any]:
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
                    "key": ["series_id", "event_time", "segment_id"],
                },
                "null_reason": {
                    "policy": "required_when_value_missing",
                    "column": "null_reason",
                    "value_columns": ["value"],
                },
            }
        ],
    }


def _write_edge_case(root: Path, stem: str, rows: list[dict[str, str]]) -> Path:
    dataset = root / f"{stem}.csv"
    with dataset.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "series_id",
                "event_time",
                "segment_id",
                "value",
                "known_at",
                "eligible_from",
                "null_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    manifest = root / f"{stem}.json"
    manifest.write_text(
        json.dumps(_edge_manifest_payload(dataset.name), indent=2),
        encoding="utf-8",
    )
    return manifest


@st.composite
def _revision_null_cases(draw):
    segment_count = draw(st.integers(min_value=2, max_value=4))
    focus_index = draw(st.integers(min_value=0, max_value=segment_count - 1))
    base_day_offset = draw(st.integers(min_value=0, max_value=20))
    first_delay = draw(st.integers(min_value=1, max_value=120))
    second_delay = draw(st.integers(min_value=1, max_value=120))
    revision_gap_hours = draw(st.integers(min_value=4, max_value=12))
    base_known = datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc) + timedelta(
        days=base_day_offset
    )
    second_known = base_known + timedelta(hours=revision_gap_hours)
    event_time = "2026-02-01"
    rows: list[dict[str, str]] = []

    for segment_index in range(segment_count):
        segment_id = f"G{segment_index}"
        first_missing = segment_index == focus_index
        rows.append(
            {
                "series_id": "EDGE",
                "event_time": event_time,
                "segment_id": segment_id,
                "value": "" if first_missing else f"{segment_id}:v0",
                "known_at": base_known.isoformat(),
                "eligible_from": (
                    base_known + timedelta(minutes=first_delay)
                ).isoformat(),
                "null_reason": "provider_pending" if first_missing else "",
            }
        )
        rows.append(
            {
                "series_id": "EDGE",
                "event_time": event_time,
                "segment_id": segment_id,
                "value": f"{segment_id}:v1",
                "known_at": second_known.isoformat(),
                "eligible_from": (
                    second_known + timedelta(minutes=second_delay)
                ).isoformat(),
                "null_reason": "",
            }
        )

    permutation = draw(st.permutations(tuple(range(len(rows)))))
    duplicate_index = draw(st.integers(min_value=0, max_value=len(rows) - 1))
    duplicate_position = draw(st.integers(min_value=0, max_value=len(rows)))
    shuffled = [deepcopy(rows[index]) for index in permutation]
    return rows, shuffled, focus_index, duplicate_index, duplicate_position


def _assert_missing_by_rejected(left, right, *, side: str) -> None:
    import pandas as pd

    left_case = left.copy()
    right_case = right.copy()
    if side == "left":
        left_case.loc[left_case.index[0], "segment_id"] = None
    elif side == "right":
        right_case.loc[right_case.index[0], "segment_id"] = None
    else:  # pragma: no cover - internal benchmark misuse
        raise ValueError(f"unsupported side: {side}")

    try:
        point_in_time_join(
            left_case,
            right_case,
            decision_time="decision_time",
            by=["series_id", "event_time", "segment_id"],
        )
    except ValueError as exc:
        assert f"{side} frame contains missing values in by columns" in str(exc)
    else:
        raise AssertionError(f"missing {side} by-key value was accepted")


@settings(
    max_examples=MAX_EXAMPLES,
    derandomize=True,
    database=None,
    deadline=None,
    print_blob=True,
)
@given(_vintage_histories(), _revision_null_cases())
def _property_contract(case, edge_case) -> None:
    rows, shuffled, duplicate_index, duplicate_position = case
    edge_rows, edge_shuffled, focus_index, edge_duplicate_index, edge_duplicate_position = (
        edge_case
    )
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)

        ordered_codes = _codes(_write_case(root, "property_ordered", rows))
        assert not ordered_codes, ordered_codes

        shuffled_codes = _codes(_write_case(root, "property_shuffled", shuffled))
        assert not shuffled_codes, shuffled_codes

        duplicate_rows = deepcopy(shuffled)
        duplicated = deepcopy(rows[duplicate_index])
        duplicated["value"] = duplicated["value"] + ":duplicate"
        duplicate_rows.insert(duplicate_position, duplicated)
        duplicate_codes = _codes(_write_case(root, "property_duplicate", duplicate_rows))
        assert "REV001" in duplicate_codes, duplicate_codes

        eligibility_ok, revision_order_ok, _ = _selection_properties(rows, shuffled)
        assert eligibility_ok
        assert revision_order_ok

        nonnull_edge_rows = deepcopy(edge_rows)
        for row in nonnull_edge_rows:
            if not row["value"]:
                row["value"] = f"{row['segment_id']}:v0"
                row["null_reason"] = ""
        multi_key_codes = _codes(
            _write_edge_case(root, "property_multi_key", nonnull_edge_rows)
        )
        assert not multi_key_codes, multi_key_codes

        duplicate_edge_rows = deepcopy(nonnull_edge_rows)
        duplicated_edge = deepcopy(nonnull_edge_rows[edge_duplicate_index])
        duplicated_edge["value"] = duplicated_edge["value"] + ":duplicate"
        duplicate_edge_rows.insert(edge_duplicate_position, duplicated_edge)
        duplicate_edge_codes = _codes(
            _write_edge_case(root, "property_multi_key_duplicate", duplicate_edge_rows)
        )
        assert "REV001" in duplicate_edge_codes, duplicate_edge_codes

        valid_null_codes = _codes(
            _write_edge_case(root, "property_null_reason_valid", edge_rows)
        )
        assert not valid_null_codes, valid_null_codes

        missing_reason_rows = deepcopy(edge_rows)
        focus_segment = f"G{focus_index}"
        missing_focus = next(
            row
            for row in missing_reason_rows
            if row["segment_id"] == focus_segment and not row["value"]
        )
        missing_focus["null_reason"] = ""
        missing_reason_codes = _codes(
            _write_edge_case(root, "property_null_reason_missing", missing_reason_rows)
        )
        assert "NULL001" in missing_reason_codes, missing_reason_codes

        missing_key_rows = deepcopy(edge_rows)
        missing_key_rows[0]["segment_id"] = ""
        missing_key_codes = _codes(
            _write_edge_case(root, "property_revision_key_missing", missing_key_rows)
        )
        assert "REV002" in missing_key_codes, missing_key_codes

        import pandas as pd

        focus_rows = [
            row for row in edge_rows if row["segment_id"] == focus_segment
        ]
        focus_rows.sort(key=lambda row: datetime.fromisoformat(row["eligible_from"]))
        first_eligible = datetime.fromisoformat(focus_rows[0]["eligible_from"])
        second_eligible = datetime.fromisoformat(focus_rows[1]["eligible_from"])
        left = pd.DataFrame(
            [
                {
                    "case_id": "first",
                    "series_id": "EDGE",
                    "event_time": focus_rows[0]["event_time"],
                    "segment_id": focus_segment,
                    "decision_time": (first_eligible + timedelta(seconds=1)).isoformat(),
                },
                {
                    "case_id": "second",
                    "series_id": "EDGE",
                    "event_time": focus_rows[0]["event_time"],
                    "segment_id": focus_segment,
                    "decision_time": (second_eligible + timedelta(seconds=1)).isoformat(),
                },
            ]
        )
        ordered_right = pd.DataFrame(edge_rows)
        shuffled_right = pd.DataFrame(edge_shuffled)
        ordered_right.loc[ordered_right["value"] == "", "value"] = None
        shuffled_right.loc[shuffled_right["value"] == "", "value"] = None
        join_kwargs = {
            "decision_time": "decision_time",
            "by": ["series_id", "event_time", "segment_id"],
        }
        selected_ordered = point_in_time_join(left, ordered_right, **join_kwargs)
        selected_shuffled = point_in_time_join(left, shuffled_right, **join_kwargs)
        ordered_values = _normalized_values(selected_ordered["value"].tolist(), pd)
        shuffled_values = _normalized_values(selected_shuffled["value"].tolist(), pd)
        expected_values = [None, f"{focus_segment}:v1"]
        assert ordered_values == expected_values, ordered_values
        assert shuffled_values == expected_values, shuffled_values

        _assert_missing_by_rejected(left, ordered_right, side="left")
        _assert_missing_by_rejected(left, ordered_right, side="right")


def run() -> dict[str, Any]:
    _property_contract()
    evaluations = MAX_EXAMPLES * len(INVARIANTS)
    return {
        "schema_version": "nofuturedata-revision-vintage-property-v2",
        "ok": True,
        "hypothesis_version": hypothesis_version,
        "examples": MAX_EXAMPLES,
        "invariants": list(INVARIANTS),
        "invariants_per_example": len(INVARIANTS),
        "passed": evaluations,
        "checks": evaluations,
        "strategy_bounds": {
            "series": [1, 3],
            "observations_per_series": [1, 3],
            "vintages_per_observation": [1, 4],
            "eligibility_delay_minutes": [1, 180],
            "multi_key_segments": [2, 4],
            "multi_key_revision_gap_hours": [4, 12],
            "multi_key_eligibility_delay_minutes": [1, 120],
        },
        "claim_limit": (
            "Hypothesis broadens and shrinks counterexample search over the declared strategy "
            "space, including multi-column revision keys and null/revision interactions; passing "
            "these examples is not a proof over all possible revision histories."
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
        print(
            "NoFutureData revision/vintage property search: PASS "
            f"({result['passed']}/{result['checks']}, {result['examples']} examples, "
            f"Hypothesis {result['hypothesis_version']})"
        )
        print(result["claim_limit"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
