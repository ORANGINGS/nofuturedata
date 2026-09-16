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
    return df.merge_asof(df, on='t', direction='forward')
"""
        findings = audit_python_source(source).findings
        codes = {item.code for item in findings}
        self.assertEqual(codes, {"SRC001", "SRC002", "SRC003", "SRC004"})
        self.assertEqual(sum(item.code == "SRC001" for item in findings), 2)

    def test_safe_trailing_patterns_pass(self) -> None:
        source = """
def features(df):
    return df.x.shift(1).rolling(5).mean()
"""
        self.assertTrue(audit_python_source(source).ok)

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


if __name__ == "__main__":
    unittest.main()
