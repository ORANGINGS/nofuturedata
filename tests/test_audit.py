from __future__ import annotations

import unittest

from nofuturedata import (
    as_of,
    audit_availability,
    audit_python_source,
    future_mutation_invariance,
    prefix_invariance,
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
