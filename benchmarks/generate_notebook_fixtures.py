"""Regenerate the deterministic Jupyter fixture corpus from its manifest."""

from __future__ import annotations

import json

from run_notebook_corpus import MANIFEST, ROOT, build_notebook


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for case in payload["cases"]:
        path = ROOT / case["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(build_notebook(case), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
