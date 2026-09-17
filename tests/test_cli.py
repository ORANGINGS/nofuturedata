from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from nofuturedata.cli import main


class CliTests(unittest.TestCase):
    def test_scan_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "feature.py"
            path.write_text("x = df.value.shift(-1)\n", encoding="utf-8")
            self.assertEqual(main(["scan", str(path)]), 1)
            path.write_text("x = df.value.shift(1)\n", encoding="utf-8")
            self.assertEqual(main(["scan", str(path)]), 0)

    def test_scan_multiple_paths_and_write_sarif(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            safe = root / "safe.py"
            leaking = root / "leaking.py"
            sarif_path = root / "out" / "nofuture.sarif"
            safe.write_text("x = df.value.shift(1)\n", encoding="utf-8")
            leaking.write_text("x = df.value.bfill()\n", encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        "scan",
                        str(safe),
                        str(leaking),
                        "--sarif",
                        str(sarif_path),
                    ]
                ),
                1,
            )
            payload = json.loads(sarif_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], "2.1.0")
            self.assertEqual(payload["runs"][0]["results"][0]["ruleId"], "SRC002")

    def test_scan_missing_path_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "missing"
            self.assertEqual(main(["scan", str(missing)]), 1)

    def test_scan_empty_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(main(["scan", folder]), 1)

    def test_time_series_scan_context_is_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cv.py"
            path.write_text(
                "cv = KFold(n_splits=5, shuffle=True, random_state=42)\n",
                encoding="utf-8",
            )
            self.assertEqual(main(["scan", str(path)]), 0)
            self.assertEqual(main(["scan", str(path), "--time-series"]), 1)

            path.write_text(
                "cv = TimeSeriesSplit(n_splits=5, gap=48)\n",
                encoding="utf-8",
            )
            self.assertEqual(main(["scan", str(path), "--time-series"]), 0)


if __name__ == "__main__":
    unittest.main()
