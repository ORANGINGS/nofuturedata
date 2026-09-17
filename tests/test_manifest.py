from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from nofuturedata import audit_manifest
from nofuturedata.cli import main


FIXTURES = Path(__file__).parent / "fixtures" / "manifest"


class ManifestTests(unittest.TestCase):
    def _write_contract(self, root: Path, *, schema_version: int = 1) -> Path:
        data = root / "data.csv"
        data.write_text(
            "event_time,known_at\n"
            "2026-01-01,2026-01-02T00:00:00+00:00\n",
            encoding="utf-8",
        )
        manifest = root / "contract.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": schema_version,
                    "datasets": [
                        {
                            "path": "data.csv",
                            "event_time": {
                                "column": "event_time",
                                "semantics": "observation_period",
                            },
                            "known_at": {
                                "column": "known_at",
                                "semantics": "first_observed_by_consumer",
                            },
                            "eligible_from": {"policy": "known_at"},
                            "timezone": "offset-aware",
                            "revision": {"policy": "none"},
                            "null_reason": {"policy": "not_applicable"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_valid_fixture_passes_and_cli_returns_zero(self) -> None:
        manifest = FIXTURES / "valid_contract.json"
        report = audit_manifest(manifest)
        self.assertTrue(report.ok)
        self.assertEqual(report.rows_scanned, 3)
        self.assertEqual(main(["audit-manifest", str(manifest)]), 0)

    def test_invalid_fixture_catches_revision_and_null_reason(self) -> None:
        report = audit_manifest(FIXTURES / "invalid_contract.json")
        codes = {item.code for item in report.findings}
        self.assertIn("REV001", codes)
        self.assertIn("NULL001", codes)

    def test_unsupported_schema_version_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manifest = self._write_contract(Path(folder), schema_version=999)
            report = audit_manifest(manifest)
            self.assertEqual([item.code for item in report.findings], ["MAN002"])

    def test_known_at_policy_does_not_require_eligible_column(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manifest = self._write_contract(Path(folder))
            self.assertTrue(audit_manifest(manifest).ok)

    def test_explicit_eligible_value_cannot_be_blank(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data.csv").write_text(
                "event_time,known_at,eligible_from\n"
                "2026-01-01,2026-01-02T00:00:00+00:00,\n",
                encoding="utf-8",
            )
            payload = {
                "schema_version": 1,
                "datasets": [
                    {
                        "path": "data.csv",
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
                        "revision": {"policy": "none"},
                        "null_reason": {"policy": "not_applicable"},
                    }
                ],
            }
            manifest = root / "contract.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            codes = {item.code for item in audit_manifest(manifest).findings}
            self.assertIn("TIME005", codes)

    def test_revision_key_must_include_event_time(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self._write_contract(root)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["datasets"][0]["revision"] = {
                "policy": "append_only_vintages",
                "key": ["series_id"],
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIn(
                "MAN004", [item.code for item in audit_manifest(manifest).findings]
            )

    def test_revision_key_row_values_must_not_be_blank(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self._write_contract(root)
            (root / "data.csv").write_text(
                "series_id,event_time,known_at\n"
                ",2026-01-01,2026-01-02T00:00:00+00:00\n",
                encoding="utf-8",
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["datasets"][0]["revision"] = {
                "policy": "append_only_vintages",
                "key": ["series_id", "event_time"],
            }
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            codes = [item.code for item in audit_manifest(manifest).findings]
            self.assertIn("REV002", codes)
            self.assertNotIn("REV001", codes)

    def test_portable_json_schema_is_valid_json(self) -> None:
        schema = (
            Path(__file__).parents[1]
            / "schemas"
            / "temporal-contract.schema.json"
        )
        payload = json.loads(schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
        self.assertEqual(
            payload["$schema"], "https://json-schema.org/draft/2020-12/schema"
        )
        self.assertEqual(payload["properties"]["schema_version"]["const"], 1)

        valid_contract = json.loads(
            (FIXTURES / "valid_contract.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(payload).validate(valid_contract)

        invalid_contract = json.loads(
            (FIXTURES / "invalid_schema_contract.json").read_text(encoding="utf-8")
        )
        with self.assertRaises(ValidationError):
            Draft202012Validator(payload).validate(invalid_contract)


if __name__ == "__main__":
    unittest.main()
