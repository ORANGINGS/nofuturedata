import re
from pathlib import Path

import nofuturedata


def test_runtime_version_matches_project_version() -> None:
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    assert match is not None
    assert nofuturedata.__version__ == match.group(1)
