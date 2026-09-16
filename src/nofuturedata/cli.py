"""Command line interface for nofuturedata."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Sequence

from .audit import (
    AuditReport,
    audit_availability,
    audit_notebook_source,
    audit_python_source,
    iter_source_files,
    report_to_sarif,
)


def _print_report(report: AuditReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return
    status = "PASS" if report.ok else "FAIL"
    print(f"{status}: {len(report.findings)} finding(s), {report.rows_scanned} row/line(s) scanned")
    for item in report.findings:
        where = []
        if item.details.get("path"):
            where.append(str(item.details["path"]))
        if item.details.get("cell"):
            where.append(f"cell {item.details['cell']}")
        if item.line is not None:
            where.append(f"line {item.line}")
        if item.row is not None:
            where.append(f"row {item.row}")
        suffix = f" ({', '.join(where)})" if where else ""
        print(f"[{item.code}] {item.message}{suffix}")


def _scan(paths: Sequence[Path]) -> AuditReport:
    combined = AuditReport()
    seen: set[Path] = set()
    for path in paths:
        for file_path in iter_source_files(path):
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            text = file_path.read_text(encoding="utf-8")
            if file_path.suffix.lower() == ".ipynb":
                report = audit_notebook_source(text, filename=str(file_path))
            else:
                report = audit_python_source(text, filename=str(file_path))
                for finding in report.findings:
                    finding.details["path"] = str(file_path)
                    finding.details["source_kind"] = "python"
            combined.extend(report)
    return combined


def _audit_csv(args: argparse.Namespace) -> AuditReport:
    with args.csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return audit_availability(
        rows,
        known_at=args.known_at,
        eligible_from=args.eligible_from,
        decision_time=args.decision_time,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nofuture",
        description="Fail-closed temporal leakage checks for data and Python code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser(
        "scan",
        help="scan Python/Jupyter source for suspicious future-looking patterns",
    )
    scan.add_argument("path", type=Path, nargs="+")
    scan.add_argument("--json", action="store_true")
    scan.add_argument(
        "--sarif",
        type=Path,
        default=None,
        help="also write SARIF 2.1.0 output for code-scanning tools",
    )

    csv_cmd = sub.add_parser("audit-csv", help="audit availability timestamps in a CSV file")
    csv_cmd.add_argument("csv", type=Path)
    csv_cmd.add_argument("--known-at", default="known_at")
    csv_cmd.add_argument("--eligible-from", default="eligible_from")
    csv_cmd.add_argument("--decision-time", default=None)
    csv_cmd.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "scan":
        report = _scan(args.path)
        if args.sarif is not None:
            args.sarif.parent.mkdir(parents=True, exist_ok=True)
            args.sarif.write_text(
                json.dumps(report_to_sarif(report), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
    elif args.command == "audit-csv":
        report = _audit_csv(args)
    else:  # pragma: no cover - argparse prevents this
        raise AssertionError(args.command)
    _print_report(report, as_json=args.json)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
