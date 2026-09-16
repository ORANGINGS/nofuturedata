from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()

