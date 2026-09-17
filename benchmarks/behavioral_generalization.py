"""Exercise runtime invariance checks against real pandas transforms.

The small method-comparison benchmark uses hand-written transforms with known
causal shapes.  This companion experiment asks whether the same behavioral
contracts transfer to executable pandas operations that users actually compose.
It deliberately pairs causal trailing, grouped/stateful, and irregular-time
transforms with future-dependent counterparts, including alignment, resampling,
and multi-column pipelines, and reports only this declared eighteen-case corpus.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from typing import Any

import pandas as pd

from nofuturedata import future_mutation_invariance, prefix_invariance


Rows = Sequence[dict[str, Any]]
Transform = Callable[[Rows], Sequence[Any]]


BASE_ROWS = [{"x": float(value)} for value in range(1, 9)]
MISSING_ROWS = [
    {"x": 1.0},
    {"x": None},
    {"x": 3.0},
    {"x": None},
    {"x": 5.0},
    {"x": 6.0},
]
PANEL_ROWS = [
    {"time": "2026-01-01T09:00:00+00:00", "group": "A", "x": 1.0},
    {"time": "2026-01-01T09:01:00+00:00", "group": "B", "x": 10.0},
    {"time": "2026-01-01T09:03:00+00:00", "group": "A", "x": 2.0},
    {"time": "2026-01-01T09:07:00+00:00", "group": "B", "x": 20.0},
    {"time": "2026-01-01T09:12:00+00:00", "group": "A", "x": 4.0},
    {"time": "2026-01-01T09:20:00+00:00", "group": "B", "x": 40.0},
    {"time": "2026-01-01T09:33:00+00:00", "group": "A", "x": 8.0},
    {"time": "2026-01-01T09:50:00+00:00", "group": "B", "x": 80.0},
]
PANEL_MISSING_ROWS = [dict(row) for row in PANEL_ROWS]
PANEL_MISSING_ROWS[2]["x"] = None
PANEL_MISSING_ROWS[3]["x"] = None
IRREGULAR_ROWS = [
    {"time": "2026-01-01T09:00:00+00:00", "x": 1.0},
    {"time": "2026-01-01T09:02:00+00:00", "x": None},
    {"time": "2026-01-01T09:11:00+00:00", "x": 4.0},
    {"time": "2026-01-01T09:25:00+00:00", "x": None},
    {"time": "2026-01-01T09:55:00+00:00", "x": 10.0},
    {"time": "2026-01-01T10:40:00+00:00", "x": 12.0},
]
MULTI_COLUMN_ROWS = [
    {"time": "2026-01-01T09:00:00+00:00", "x": 1.0, "y": 2.0},
    {"time": "2026-01-01T09:02:00+00:00", "x": 2.0, "y": 4.0},
    {"time": "2026-01-01T09:11:00+00:00", "x": 4.0, "y": 8.0},
    {"time": "2026-01-01T09:25:00+00:00", "x": 8.0, "y": 16.0},
    {"time": "2026-01-01T09:55:00+00:00", "x": 16.0, "y": 32.0},
    {"time": "2026-01-01T10:40:00+00:00", "x": 32.0, "y": 64.0},
]


def _series(rows: Rows) -> pd.Series:
    return pd.Series([row["x"] for row in rows], dtype="float64")


def _normalized(values: pd.Series) -> list[float | None]:
    return [None if pd.isna(value) else round(float(value), 12) for value in values]


def _rolling_mean(rows: Rows) -> list[float | None]:
    return _normalized(_series(rows).rolling(3, min_periods=1).mean())


def _expanding_mean(rows: Rows) -> list[float | None]:
    return _normalized(_series(rows).expanding(min_periods=1).mean())


def _ewm_mean(rows: Rows) -> list[float | None]:
    return _normalized(_series(rows).ewm(alpha=0.5, adjust=False).mean())


def _centered_rolling_mean(rows: Rows) -> list[float | None]:
    return _normalized(
        _series(rows).rolling(3, center=True, min_periods=1).mean()  # nofuture: ignore[SRC003]
    )


def _backfill(rows: Rows) -> list[float | None]:
    return _normalized(_series(rows).bfill())  # nofuture: ignore[SRC002]


def _full_series_center(rows: Rows) -> list[float | None]:
    values = _series(rows)
    return _normalized(values - values.mean())


def _temporal_frame(rows: Rows) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame


def _grouped_expanding_mean(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    values = frame.groupby("group", sort=False)["x"].transform(
        lambda series: series.expanding(min_periods=1).mean()
    )
    return _normalized(values)


def _grouped_ewm_mean(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    values = frame.groupby("group", sort=False)["x"].transform(
        lambda series: series.ewm(alpha=0.5, adjust=False).mean()
    )
    return _normalized(values)


def _grouped_full_mean(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    return _normalized(frame.groupby("group", sort=False)["x"].transform("mean"))


def _grouped_backfill(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    values = frame.groupby("group", sort=False)["x"].bfill()  # nofuture: ignore[SRC002]
    return _normalized(values)


def _irregular_ffill(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows).set_index("time")
    return _normalized(frame["x"].ffill())


def _irregular_time_interpolate(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows).set_index("time")
    return _normalized(
        frame["x"].interpolate(method="time", limit_area="inside")
    )


def _asof_previous_value(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    right = frame[["time", "x"]].rename(columns={"x": "aligned_x"})
    joined = pd.merge_asof(
        frame[["time"]],
        right,
        on="time",
        direction="backward",
        allow_exact_matches=False,
    )
    return _normalized(joined["aligned_x"])


def _asof_next_value(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    right = frame[["time", "x"]].rename(columns={"x": "aligned_x"})
    joined = pd.merge_asof(  # nofuture: ignore[SRC004]
        frame[["time"]],
        right,
        on="time",
        direction="forward",
        allow_exact_matches=False,
    )
    return _normalized(joined["aligned_x"])


def _right_closed_resample_mean(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows).set_index("time")
    aggregate = frame["x"].resample(
        "15min", closed="right", label="right"
    ).mean()
    return _normalized(aggregate.reindex(frame.index, method="ffill"))


def _left_labeled_resample_mean(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows).set_index("time")
    aggregate = frame["x"].resample(  # nofuture: ignore[SRC010]
        "15min", closed="left", label="left"
    ).mean()
    return _normalized(aggregate.reindex(frame.index, method="ffill"))


def _multi_column_stateful_diff(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    deltas = frame[["x", "y"]].diff().fillna(0.0)
    return _normalized(deltas.expanding(min_periods=1).mean().sum(axis=1))


def _multi_column_future_diff(rows: Rows) -> list[float | None]:
    frame = _temporal_frame(rows)
    deltas = frame[["x", "y"]].diff(periods=-1).fillna(0.0)  # nofuture: ignore[SRC005]
    return _normalized(deltas.expanding(min_periods=1).mean().sum(axis=1))


def _future_x_mutator(rows: Rows, point: int) -> list[dict[str, Any]]:
    changed = [dict(row) for row in rows]
    for index in range(point, len(changed)):
        value = changed[index].get("x")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            changed[index]["x"] = value * 2 + 17
    return changed


def _future_xy_mutator(rows: Rows, point: int) -> list[dict[str, Any]]:
    changed = [dict(row) for row in rows]
    for index in range(point, len(changed)):
        changed[index]["x"] = changed[index]["x"] * 2 + 17
        changed[index]["y"] = changed[index]["y"] * 3 + 19
    return changed


def _valid_temporal_rows(rows: Rows) -> bool:
    try:
        times = pd.to_datetime([row["time"] for row in rows], utc=True)
    except (KeyError, TypeError, ValueError):
        return False
    return bool(times.is_monotonic_increasing) and all("x" in row for row in rows)


def _valid_panel_rows(rows: Rows) -> bool:
    return _valid_temporal_rows(rows) and all(
        row.get("group") in {"A", "B"} for row in rows
    )


def _valid_multi_column_rows(rows: Rows) -> bool:
    return _valid_temporal_rows(rows) and all(
        isinstance(row.get(column), (int, float)) and not isinstance(row.get(column), bool)
        for row in rows
        for column in ("x", "y")
    )


CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "pandas-trailing-rolling-mean",
        "kind": "safe",
        "rows": BASE_ROWS,
        "transform": _rolling_mean,
    },
    {
        "id": "pandas-expanding-mean",
        "kind": "safe",
        "rows": BASE_ROWS,
        "transform": _expanding_mean,
    },
    {
        "id": "pandas-ewm-mean",
        "kind": "safe",
        "rows": BASE_ROWS,
        "transform": _ewm_mean,
    },
    {
        "id": "pandas-centered-rolling-mean",
        "kind": "leak",
        "rows": BASE_ROWS,
        "transform": _centered_rolling_mean,
    },
    {
        "id": "pandas-backfill",
        "kind": "leak",
        "rows": MISSING_ROWS,
        "transform": _backfill,
    },
    {
        "id": "pandas-full-series-centering",
        "kind": "leak",
        "rows": BASE_ROWS,
        "transform": _full_series_center,
    },
    {
        "id": "pandas-grouped-expanding-mean",
        "kind": "safe",
        "rows": PANEL_ROWS,
        "transform": _grouped_expanding_mean,
        "mutator": _future_x_mutator,
        "input_validator": _valid_panel_rows,
    },
    {
        "id": "pandas-grouped-ewm-mean",
        "kind": "safe",
        "rows": PANEL_ROWS,
        "transform": _grouped_ewm_mean,
        "mutator": _future_x_mutator,
        "input_validator": _valid_panel_rows,
    },
    {
        "id": "pandas-grouped-full-mean",
        "kind": "leak",
        "rows": PANEL_ROWS,
        "transform": _grouped_full_mean,
        "mutator": _future_x_mutator,
        "input_validator": _valid_panel_rows,
    },
    {
        "id": "pandas-grouped-backfill",
        "kind": "leak",
        "rows": PANEL_MISSING_ROWS,
        "transform": _grouped_backfill,
        "mutator": _future_x_mutator,
        "input_validator": _valid_panel_rows,
    },
    {
        "id": "pandas-irregular-ffill",
        "kind": "safe",
        "rows": IRREGULAR_ROWS,
        "transform": _irregular_ffill,
        "mutator": _future_x_mutator,
        "input_validator": _valid_temporal_rows,
    },
    {
        "id": "pandas-irregular-time-interpolation",
        "kind": "leak",
        "rows": IRREGULAR_ROWS,
        "transform": _irregular_time_interpolate,
        "mutator": _future_x_mutator,
        "input_validator": _valid_temporal_rows,
    },
    {
        "id": "pandas-asof-previous-value",
        "kind": "safe",
        "rows": MULTI_COLUMN_ROWS,
        "transform": _asof_previous_value,
        "mutator": _future_xy_mutator,
        "input_validator": _valid_multi_column_rows,
    },
    {
        "id": "pandas-asof-next-value",
        "kind": "leak",
        "rows": MULTI_COLUMN_ROWS,
        "transform": _asof_next_value,
        "mutator": _future_xy_mutator,
        "input_validator": _valid_multi_column_rows,
    },
    {
        "id": "pandas-right-closed-resample-mean",
        "kind": "safe",
        "rows": MULTI_COLUMN_ROWS,
        "transform": _right_closed_resample_mean,
        "mutator": _future_xy_mutator,
        "input_validator": _valid_multi_column_rows,
    },
    {
        "id": "pandas-left-labeled-resample-mean",
        "kind": "leak",
        "rows": MULTI_COLUMN_ROWS,
        "transform": _left_labeled_resample_mean,
        "mutator": _future_xy_mutator,
        "input_validator": _valid_multi_column_rows,
    },
    {
        "id": "pandas-multicolumn-stateful-diff",
        "kind": "safe",
        "rows": MULTI_COLUMN_ROWS,
        "transform": _multi_column_stateful_diff,
        "mutator": _future_xy_mutator,
        "input_validator": _valid_multi_column_rows,
    },
    {
        "id": "pandas-multicolumn-future-diff",
        "kind": "leak",
        "rows": MULTI_COLUMN_ROWS,
        "transform": _multi_column_future_diff,
        "mutator": _future_xy_mutator,
        "input_validator": _valid_multi_column_rows,
    },
)


def run() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in CASES:
        prefix = prefix_invariance(case["transform"], case["rows"])
        mutation = future_mutation_invariance(
            case["transform"],
            case["rows"],
            mutator=case.get("mutator"),
            input_validator=case.get("input_validator"),
        )
        prefix_detected = not prefix.ok
        mutation_detected = not mutation.ok
        detected = prefix_detected or mutation_detected
        expected_detected = case["kind"] == "leak"
        results.append(
            {
                "id": case["id"],
                "kind": case["kind"],
                "prefix_detected": prefix_detected,
                "mutation_detected": mutation_detected,
                "runtime_union_detected": detected,
                "matches_expected": detected == expected_detected,
            }
        )

    safe_cases = sum(row["kind"] == "safe" for row in results)
    leak_cases = sum(row["kind"] == "leak" for row in results)
    detected_leaks = sum(
        row["kind"] == "leak" and row["runtime_union_detected"] for row in results
    )
    clean_safe = sum(
        row["kind"] == "safe" and not row["runtime_union_detected"] for row in results
    )
    matched = sum(row["matches_expected"] for row in results)
    return {
        "schema_version": "nofuturedata-behavioral-generalization-v3",
        "ok": matched == len(results),
        "pandas_version": pd.__version__,
        "cases": len(results),
        "leak_cases": leak_cases,
        "safe_cases": safe_cases,
        "matched": matched,
        "detected_leaks": detected_leaks,
        "clean_safe_cases": clean_safe,
        "results": results,
        "claim_limit": (
            "This eighteen-case executable pandas transfer experiment tests declared transforms only; "
            "it is not an estimate of behavioral-check recall across arbitrary pipelines."
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
            "NoFutureData behavioral generalization: {} ({}/{}, pandas {})".format(
                state, result["matched"], result["cases"], result["pandas_version"]
            )
        )
        print(
            "runtime-union detected {}/{} leaks; kept {}/{} safe controls clean".format(
                result["detected_leaks"],
                result["leak_cases"],
                result["clean_safe_cases"],
                result["safe_cases"],
            )
        )
        for row in result["results"]:
            print(
                "{:<34} kind={} prefix={} mutation={}".format(
                    row["id"],
                    row["kind"],
                    int(row["prefix_detected"]),
                    int(row["mutation_detected"]),
                )
            )
        print(result["claim_limit"])
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
