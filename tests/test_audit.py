from __future__ import annotations

import json
import unittest

import pandas as pd

from nofuturedata import (
    as_of,
    audit_availability,
    audit_notebook_source,
    audit_python_source,
    future_mutation_invariance,
    point_in_time_join,
    prefix_invariance,
    report_to_sarif,
)


class AvailabilityTests(unittest.TestCase):
    def test_future_record_is_rejected_at_decision_time(self) -> None:
        rows = [
            {
                "known_at": "2026-09-16T09:00:00+00:00",
                "eligible_from": "2026-09-16T09:01:00+00:00",
                "decision_time": "2026-09-16T09:00:30+00:00",
            }
        ]
        report = audit_availability(rows, decision_time="decision_time")
        self.assertFalse(report.ok)
        self.assertEqual(report.findings[0].code, "LEAK001")

    def test_scheduled_future_event_does_not_fail_merely_for_event_time(self) -> None:
        rows = [
            {
                "event_time": "2026-09-20T12:00:00+00:00",
                "known_at": "2026-09-16T09:00:00+00:00",
                "eligible_from": "2026-09-16T09:00:00+00:00",
                "decision_time": "2026-09-16T10:00:00+00:00",
            }
        ]
        self.assertTrue(
            audit_availability(rows, decision_time="decision_time").ok
        )

    def test_as_of_fails_closed_and_filters_by_availability(self) -> None:
        rows = [
            {"id": 1, "known_at": "2026-09-16T09:00:00+00:00"},
            {"id": 2, "known_at": "2026-09-16T10:00:00+00:00"},
        ]
        result = as_of(rows, "2026-09-16T09:30:00+00:00")
        self.assertEqual([row["id"] for row in result], [1])

    def test_as_of_rejects_eligibility_before_known_at(self) -> None:
        rows = [
            {
                "id": 1,
                "known_at": "2026-09-16T10:00:00+00:00",
                "eligible_from": "2026-09-16T09:59:59+00:00",
            }
        ]
        with self.assertRaisesRegex(ValueError, "before 'known_at'"):
            as_of(rows, "2026-09-16T11:00:00+00:00")


class PointInTimeJoinTests(unittest.TestCase):
    def test_revised_vintage_is_visible_only_after_it_is_known(self) -> None:
        left = pd.DataFrame(
            {
                "series": ["CPI", "CPI"],
                "event_time": ["2026-01-01", "2026-01-01"],
                "decision_time": [
                    "2026-02-15T12:00:00+00:00",
                    "2026-03-15T12:00:00+00:00",
                ],
            }
        )
        right = pd.DataFrame(
            {
                "series": ["CPI", "CPI"],
                "event_time": ["2026-01-01", "2026-01-01"],
                "known_at": [
                    "2026-02-01T08:30:00+00:00",
                    "2026-03-01T08:30:00+00:00",
                ],
                "value": [100.0, 101.0],
            }
        )

        joined = point_in_time_join(
            left,
            right,
            decision_time="decision_time",
            by=["series", "event_time"],
        )

        self.assertEqual(joined["value"].tolist(), [100.0, 101.0])

    def test_planted_future_row_is_not_joined(self) -> None:
        left = pd.DataFrame(
            {
                "series": ["CPI"],
                "decision_time": ["2026-02-15T12:00:00+00:00"],
            }
        )
        right = pd.DataFrame(
            {
                "series": ["CPI"],
                "known_at": ["2026-03-01T08:30:00+00:00"],
                "value": [999.0],
            }
        )

        joined = point_in_time_join(
            left,
            right,
            decision_time="decision_time",
            by="series",
        )

        self.assertTrue(pd.isna(joined.loc[0, "value"]))

    def test_eligible_from_delays_a_known_row(self) -> None:
        left = pd.DataFrame(
            {
                "decision_time": [
                    "2026-02-01T08:31:00+00:00",
                    "2026-02-01T08:36:00+00:00",
                ]
            }
        )
        right = pd.DataFrame(
            {
                "known_at": ["2026-02-01T08:30:00+00:00"],
                "eligible_from": ["2026-02-01T08:35:00+00:00"],
                "value": [100.0],
            }
        )

        joined = point_in_time_join(left, right, decision_time="decision_time")

        self.assertTrue(pd.isna(joined.loc[0, "value"]))
        self.assertEqual(joined.loc[1, "value"], 100.0)

    def test_naive_timestamp_fails_closed(self) -> None:
        left = pd.DataFrame({"decision_time": ["2026-02-01 08:31:00"]})
        right = pd.DataFrame(
            {"known_at": ["2026-02-01T08:30:00+00:00"], "value": [1]}
        )
        with self.assertRaisesRegex(ValueError, "timezone offset"):
            point_in_time_join(left, right, decision_time="decision_time")

    def test_eligibility_before_known_at_fails_closed(self) -> None:
        left = pd.DataFrame(
            {"decision_time": ["2026-02-01T09:00:00+00:00"]}
        )
        right = pd.DataFrame(
            {
                "known_at": ["2026-02-01T08:30:00+00:00"],
                "eligible_from": ["2026-02-01T08:29:59+00:00"],
            }
        )
        with self.assertRaisesRegex(ValueError, "before 'known_at'"):
            point_in_time_join(left, right, decision_time="decision_time")

    def test_ambiguous_duplicate_right_keys_fail_closed(self) -> None:
        left = pd.DataFrame(
            {
                "series": ["CPI"],
                "decision_time": ["2026-02-01T09:00:00+00:00"],
            }
        )
        right = pd.DataFrame(
            {
                "series": ["CPI", "CPI"],
                "known_at": [
                    "2026-02-01T08:30:00+00:00",
                    "2026-02-01T08:30:00+00:00",
                ],
                "value": [1, 2],
            }
        )
        with self.assertRaisesRegex(ValueError, "ambiguous duplicate"):
            point_in_time_join(
                left,
                right,
                decision_time="decision_time",
                by="series",
            )


class StaticScanTests(unittest.TestCase):
    def test_flags_common_future_looking_pandas_patterns(self) -> None:
        source = """
def features(df):
    a = df.x.shift(-1)
    a2 = df.x.shift(periods=-2)
    b = df.x.bfill()
    c = df.x.rolling(5, center=True).mean()
    d = df.x.diff(-1)
    e = df.x.pct_change(periods=-2)
    f = df.x.fillna(method='bfill')
    g = df.x.interpolate(limit_direction='both')
    df['global_mean'] = df.x.mean()
    h = df.iloc[-1]['x']
    i = df.resample('1h').last()
    return df.merge_asof(df, on='t', direction='forward')
"""
        findings = audit_python_source(source).findings
        codes = {item.code for item in findings}
        self.assertEqual(
            codes,
            {"SRC001", "SRC002", "SRC003", "SRC004", "SRC005", "SRC006", "SRC007", "SRC008", "SRC009", "SRC010"},
        )
        self.assertEqual(sum(item.code == "SRC001" for item in findings), 2)
        self.assertEqual(sum(item.code == "SRC005" for item in findings), 2)

    def test_safe_trailing_patterns_pass(self) -> None:
        source = """
def features(df):
    a = df.x.shift(1).rolling(5).mean()
    b = df.x.diff(1)
    c = df.x.pct_change(periods=2)
    d = df.x.fillna(method='ffill')
    e = df.x.interpolate(limit_direction='forward')
    summary = df.x.mean()
    df['rolling_mean'] = df.x.rolling(12).mean()
    first = df.iloc[0]['x']
    hourly = df.resample('1h', label='right').last()
    monthly = df.resample('1ME').last()
    return a + b + c + d + e + summary + first
"""
        self.assertTrue(audit_python_source(source).ok)

    def test_temporal_dimension_shift_is_gated_narrowly(self) -> None:
        self.assertEqual(
            [
                item.code
                for item in audit_python_source(
                    "future = array.shift(time=-1)\n"
                ).findings
            ],
            ["SRC001"],
        )
        self.assertTrue(audit_python_source("lag = array.shift(time=1)\n").ok)
        self.assertTrue(audit_python_source("other = array.shift(axis=-1)\n").ok)

    def test_whole_series_aggregate_requires_same_dataframe_feature_assignment(self) -> None:
        self.assertFalse(audit_python_source("df['m'] = df.x.mean()\n").ok)
        self.assertTrue(audit_python_source("summary = df.x.mean()\n").ok)
        self.assertTrue(audit_python_source("df['m'] = other.x.mean()\n").ok)
        self.assertTrue(audit_python_source("df['m'] = df.x.rolling(12).mean()\n").ok)

    def test_negative_absolute_iloc_is_gated_but_nonnegative_is_clean(self) -> None:
        self.assertFalse(audit_python_source("last = df.iloc[-1]['x']\n").ok)
        self.assertTrue(audit_python_source("first = df.iloc[0]['x']\n").ok)

    def test_left_labeled_fixed_interval_resample_is_gated_narrowly(self) -> None:
        self.assertFalse(audit_python_source("hourly = df.resample('1h').last()\n").ok)
        self.assertFalse(
            audit_python_source("bars = df.resample('15min', label='left').max()\n").ok
        )
        self.assertTrue(
            audit_python_source("hourly = df.resample('1h', label='right').last()\n").ok
        )
        self.assertTrue(audit_python_source("monthly = df.resample('1ME').last()\n").ok)
        self.assertTrue(audit_python_source("dynamic = df.resample(freq).last()\n").ok)

    def test_time_series_context_gates_random_cv_without_global_false_positive(self) -> None:
        random_kfold = "cv = KFold(n_splits=5, shuffle=True, random_state=42)\n"
        grouped_cv = [
            "cv = GroupKFold(n_splits=5)\n",
            "cv = GroupShuffleSplit(n_splits=5, random_state=42)\n",
        ]
        random_split = "train, test = train_test_split(X, test_size=0.2)\n"
        default_cv_helpers = [
            "scores = cross_val_score(model, X, y)\n",
            "scores = cross_validate(model, X, y, cv=None)\n",
            "pred = cross_val_predict(model, X, y, cv=5)\n",
            "sizes, train, test = learning_curve(model, X, y, cv=5)\n",
            "train, test = validation_curve(model, X, y, param_name='alpha', param_range=[0.1, 1.0])\n",
            "score, perm, p = permutation_test_score(model, X, y, cv=None)\n",
            "search = GridSearchCV(model, params, cv=None)\n",
            "search = RandomizedSearchCV(model, params, cv=5)\n",
        ]
        chronological_split = (
            "train, test = train_test_split(X, test_size=0.2, shuffle=False)\n"
        )
        time_series_split = "cv = TimeSeriesSplit(n_splits=5, gap=48)\n"
        temporal_cv_helper = (
            "scores = cross_val_score(model, X, y, "
            "cv=TimeSeriesSplit(n_splits=5, gap=48))\n"
        )
        temporal_search_cv = (
            "search = GridSearchCV(model, params, "
            "cv=TimeSeriesSplit(n_splits=5, gap=48))\n"
        )
        temporal_curve_helpers = [
            "sizes, train, test = learning_curve(model, X, y, cv=TimeSeriesSplit(n_splits=5, gap=48))\n",
            "train, test = validation_curve(model, X, y, param_name='alpha', param_range=[0.1, 1.0], cv=TimeSeriesSplit(n_splits=5, gap=48))\n",
            "score, perm, p = permutation_test_score(model, X, y, cv=TimeSeriesSplit(n_splits=5, gap=48))\n",
        ]
        unresolved_cv_helper = "scores = cross_val_score(model, X, y, cv=cv)\n"

        self.assertTrue(audit_python_source(random_kfold).ok)
        self.assertEqual(
            [
                item.code
                for item in audit_python_source(
                    random_kfold, temporal_context="time_series"
                ).findings
            ],
            ["SRC011"],
        )
        for source in grouped_cv:
            with self.subTest(source=source):
                self.assertTrue(audit_python_source(source).ok)
                self.assertEqual(
                    [
                        item.code
                        for item in audit_python_source(
                            source, temporal_context="time_series"
                        ).findings
                    ],
                    ["SRC011"],
                )
        self.assertFalse(
            audit_python_source(random_split, temporal_context="time_series").ok
        )
        for source in default_cv_helpers:
            with self.subTest(source=source):
                self.assertTrue(audit_python_source(source).ok)
                self.assertFalse(
                    audit_python_source(source, temporal_context="time_series").ok
                )
        self.assertTrue(
            audit_python_source(
                chronological_split, temporal_context="time_series"
            ).ok
        )
        self.assertTrue(
            audit_python_source(
                time_series_split, temporal_context="time_series"
            ).ok
        )
        self.assertTrue(
            audit_python_source(
                temporal_cv_helper, temporal_context="time_series"
            ).ok
        )
        self.assertTrue(
            audit_python_source(
                temporal_search_cv, temporal_context="time_series"
            ).ok
        )
        for source in temporal_curve_helpers:
            with self.subTest(source=source):
                self.assertTrue(
                    audit_python_source(source, temporal_context="time_series").ok
                )
        self.assertTrue(
            audit_python_source(
                unresolved_cv_helper, temporal_context="time_series"
            ).ok
        )

    def test_time_series_context_gates_negative_numpy_roll_narrowly(self) -> None:
        negative_roll = "future = np.roll(values, -1)\n"
        keyword_negative_roll = "future = numpy.roll(values, shift=-2)\n"
        positive_roll = "lag = np.roll(values, 1)\nlag[0] = np.nan\n"
        unrelated_roll = "future = custom.roll(values, -1)\n"

        self.assertTrue(audit_python_source(negative_roll).ok)
        self.assertEqual(
            [
                item.code
                for item in audit_python_source(
                    negative_roll, temporal_context="time_series"
                ).findings
            ],
            ["SRC012"],
        )
        self.assertEqual(
            [
                item.code
                for item in audit_python_source(
                    keyword_negative_roll, temporal_context="time_series"
                ).findings
            ],
            ["SRC012"],
        )
        self.assertTrue(
            audit_python_source(positive_roll, temporal_context="time_series").ok
        )
        self.assertTrue(
            audit_python_source(unrelated_roll, temporal_context="time_series").ok
        )

    def test_unknown_temporal_context_fails_explicitly(self) -> None:
        with self.assertRaisesRegex(ValueError, "temporal_context"):
            audit_python_source("x = 1\n", temporal_context="unknown")

    def test_inline_suppression_can_be_targeted_or_generic(self) -> None:
        targeted = "x = df.x.shift(-1)  # nofuture: ignore[SRC001]\n"
        generic = "x = df.x.bfill()  # nofuture: ignore\n"
        wrong_code = "x = df.x.shift(-1)  # nofuture: ignore[SRC002]\n"
        self.assertTrue(audit_python_source(targeted).ok)
        self.assertTrue(audit_python_source(generic).ok)
        self.assertFalse(audit_python_source(wrong_code).ok)

    def test_scans_python_notebook_cells(self) -> None:
        notebook = {
            "metadata": {"kernelspec": {"language": "python"}},
            "cells": [
                {"cell_type": "markdown", "source": ["# demo"]},
                {"cell_type": "code", "source": ["x = df.x.shift(-1)\n"]},
            ],
        }
        report = audit_notebook_source(json.dumps(notebook), filename="demo.ipynb")
        self.assertFalse(report.ok)
        self.assertEqual(report.findings[0].code, "SRC001")
        self.assertEqual(report.findings[0].details["cell"], 2)
        self.assertEqual(report.findings[0].details["path"], "demo.ipynb")

    def test_notebook_ipython_magics_do_not_break_python_scan(self) -> None:
        notebook = {
            "metadata": {"kernelspec": {"language": "python"}},
            "cells": [
                {
                    "cell_type": "code",
                    "source": [
                        "%matplotlib inline\n",
                        "!echo setup\n",
                        "x = df.x.shift(-1)\n",
                    ],
                },
                {
                    "cell_type": "code",
                    "source": ["%%time\n", "safe = df.x.shift(1)\n"],
                },
                {
                    "cell_type": "code",
                    "source": ["%%bash\n", "echo shift(-1)\n"],
                },
            ],
        }
        report = audit_notebook_source(json.dumps(notebook), filename="magics.ipynb")
        self.assertFalse(report.ok)
        self.assertEqual([item.code for item in report.findings], ["SRC001"])
        self.assertEqual(report.findings[0].line, 3)
        self.assertEqual(report.findings[0].details["cell"], 1)

    def test_sarif_contains_rule_and_location(self) -> None:
        report = audit_python_source("x = df.x.shift(-1)\n", filename="feature.py")
        report.findings[0].details["path"] = "feature.py"
        sarif = report_to_sarif(report)
        result = sarif["runs"][0]["results"][0]
        self.assertEqual(result["ruleId"], "SRC001")
        self.assertEqual(
            result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
            "feature.py",
        )


class InvarianceTests(unittest.TestCase):
    @staticmethod
    def safe_transform(rows):
        total = 0
        out = []
        for row in rows:
            total += row["x"]
            out.append(total)
        return out

    @staticmethod
    def leaking_transform(rows):
        total = sum(row["x"] for row in rows)
        return [total for _ in rows]

    def test_prefix_invariance_distinguishes_safe_and_leaking(self) -> None:
        rows = [{"x": value} for value in range(1, 9)]
        self.assertTrue(prefix_invariance(self.safe_transform, rows).ok)
        self.assertFalse(prefix_invariance(self.leaking_transform, rows).ok)

    def test_future_mutation_invariance_distinguishes_safe_and_leaking(self) -> None:
        rows = [{"x": value} for value in range(1, 9)]
        self.assertTrue(future_mutation_invariance(self.safe_transform, rows).ok)
        self.assertFalse(
            future_mutation_invariance(self.leaking_transform, rows).ok
        )

    def test_future_mutation_rejects_invalid_interventions(self) -> None:
        rows = [{"p": value} for value in (0.1, 0.2, 0.3, 0.4)]

        def valid_probabilities(candidate_rows):
            return all(0.0 <= row["p"] <= 1.0 for row in candidate_rows)

        def safe_probability_transform(candidate_rows):
            return [row["p"] * 2 for row in candidate_rows]

        with self.assertRaisesRegex(ValueError, "input contract"):
            future_mutation_invariance(
                safe_probability_transform,
                rows,
                cut_points=[2],
                input_validator=valid_probabilities,
            )

        def changes_past(candidate_rows, point):
            changed = [dict(row) for row in candidate_rows]
            changed[0]["p"] = 0.9
            return changed

        with self.assertRaisesRegex(ValueError, "historical prefix"):
            future_mutation_invariance(
                safe_probability_transform,
                rows,
                cut_points=[2],
                mutator=changes_past,
                input_validator=valid_probabilities,
            )

    def test_domain_valid_future_mutator_preserves_safe_and_detects_leak(self) -> None:
        rows = [{"p": value} for value in (0.1, 0.2, 0.3, 0.4)]

        def valid_probabilities(candidate_rows):
            return all(0.0 <= row["p"] <= 1.0 for row in candidate_rows)

        def bounded_mutator(candidate_rows, point):
            changed = [dict(row) for row in candidate_rows]
            for index in range(point, len(changed)):
                changed[index]["p"] = 1.0 - changed[index]["p"]
            return changed

        def safe_transform(candidate_rows):
            return [row["p"] for row in candidate_rows]

        def leaking_transform(candidate_rows):
            future_mean = sum(row["p"] for row in candidate_rows) / len(candidate_rows)
            return [future_mean for _ in candidate_rows]

        self.assertTrue(
            future_mutation_invariance(
                safe_transform,
                rows,
                cut_points=[2],
                mutator=bounded_mutator,
                input_validator=valid_probabilities,
            ).ok
        )
        self.assertFalse(
            future_mutation_invariance(
                leaking_transform,
                rows,
                cut_points=[2],
                mutator=bounded_mutator,
                input_validator=valid_probabilities,
            ).ok
        )


if __name__ == "__main__":
    unittest.main()
