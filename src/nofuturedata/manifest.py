"""Dataset-level temporal contract validation."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .audit import AuditReport, Finding, audit_availability


MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class _DatasetContract:
    raw_path: str
    data_format: str
    event_time: str
    event_time_semantics: str
    known_at: str
    known_at_semantics: str
    eligible_from: str | None
    eligible_policy: str
    decision_time: str | None
    revision_policy: str
    revision_key: tuple[str, ...]
    null_policy: str
    null_reason: str | None
    null_value_columns: tuple[str, ...]


def _finding(
    code: str,
    message: str,
    *,
    path: Path,
    details: dict[str, Any] | None = None,
) -> Finding:
    payload: dict[str, Any] = {"path": str(path), "source_kind": "manifest"}
    if details:
        payload.update(details)
    return Finding(code, "error", message, details=payload)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _contract_error(
    report: AuditReport,
    message: str,
    *,
    manifest_path: Path,
    dataset_index: int,
) -> None:
    report.findings.append(
        _finding(
            "MAN004",
            message,
            path=manifest_path,
            details={"dataset_index": dataset_index},
        )
    )


def _parse_contract(
    spec: Mapping[str, Any],
    *,
    manifest_path: Path,
    dataset_index: int,
    report: AuditReport,
) -> _DatasetContract | None:
    raw_path = _text(spec.get("path"))
    if raw_path is None:
        _contract_error(
            report,
            "dataset path must be a non-empty string",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None

    data_format = _text(spec.get("format", "csv"))
    if data_format is None:
        _contract_error(
            report,
            "format must be a non-empty string",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    data_format = data_format.lower()
    if data_format != "csv":
        report.findings.append(
            _finding(
                "MAN006",
                f"unsupported dataset format: {data_format}",
                path=manifest_path,
                details={"dataset_index": dataset_index},
            )
        )
        return None

    event = spec.get("event_time")
    if not isinstance(event, Mapping):
        _contract_error(
            report,
            "event_time must define column and semantics",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    event_time = _text(event.get("column"))
    event_semantics = _text(event.get("semantics"))
    if event_time is None or event_semantics is None:
        _contract_error(
            report,
            "event_time.column and event_time.semantics are required",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None

    known = spec.get("known_at")
    if not isinstance(known, Mapping):
        _contract_error(
            report,
            "known_at must define column and semantics",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    known_at = _text(known.get("column"))
    known_semantics = _text(known.get("semantics"))
    if known_at is None or known_semantics is None:
        _contract_error(
            report,
            "known_at.column and known_at.semantics are required",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None

    if spec.get("timezone") != "offset-aware":
        _contract_error(
            report,
            "timezone must be 'offset-aware'",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None

    eligible = spec.get("eligible_from")
    if not isinstance(eligible, Mapping):
        _contract_error(
            report,
            "eligible_from must define a policy",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    eligible_policy = _text(eligible.get("policy"))
    if eligible_policy not in {"explicit_column", "known_at"}:
        _contract_error(
            report,
            "eligible_from.policy must be 'explicit_column' or 'known_at'",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    eligible_from = _text(eligible.get("column"))
    if eligible_policy == "explicit_column" and eligible_from is None:
        _contract_error(
            report,
            "eligible_from.column is required for explicit_column policy",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    if eligible_policy == "known_at":
        eligible_from = None

    decision_time: str | None = None
    decision = spec.get("decision_time")
    if decision is not None:
        if not isinstance(decision, Mapping):
            _contract_error(
                report,
                "decision_time must be an object with a column",
                manifest_path=manifest_path,
                dataset_index=dataset_index,
            )
            return None
        decision_time = _text(decision.get("column"))
        if decision_time is None:
            _contract_error(
                report,
                "decision_time.column must be a non-empty string",
                manifest_path=manifest_path,
                dataset_index=dataset_index,
            )
            return None

    revision = spec.get("revision")
    if not isinstance(revision, Mapping):
        _contract_error(
            report,
            "revision must define a policy",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    revision_policy = _text(revision.get("policy"))
    if revision_policy not in {"append_only_vintages", "none"}:
        _contract_error(
            report,
            "revision.policy must be 'append_only_vintages' or 'none'",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    raw_revision_key = revision.get("key", [])
    if revision_policy == "append_only_vintages":
        if not isinstance(raw_revision_key, list) or not raw_revision_key:
            _contract_error(
                report,
                "revision.key must be a non-empty list for append_only_vintages",
                manifest_path=manifest_path,
                dataset_index=dataset_index,
            )
            return None
        revision_key = tuple(_text(item) or "" for item in raw_revision_key)
        if any(not item for item in revision_key) or event_time not in revision_key:
            _contract_error(
                report,
                "revision.key must contain non-empty columns including event_time.column",
                manifest_path=manifest_path,
                dataset_index=dataset_index,
            )
            return None
    else:
        revision_key = ()

    null_reason = spec.get("null_reason")
    if not isinstance(null_reason, Mapping):
        _contract_error(
            report,
            "null_reason must define a policy",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    null_policy = _text(null_reason.get("policy"))
    if null_policy not in {"required_when_value_missing", "not_applicable"}:
        _contract_error(
            report,
            "null_reason.policy must be 'required_when_value_missing' or 'not_applicable'",
            manifest_path=manifest_path,
            dataset_index=dataset_index,
        )
        return None
    null_reason_column: str | None = None
    null_value_columns: tuple[str, ...] = ()
    if null_policy == "required_when_value_missing":
        null_reason_column = _text(null_reason.get("column"))
        raw_value_columns = null_reason.get("value_columns")
        if null_reason_column is None or not isinstance(raw_value_columns, list) or not raw_value_columns:
            _contract_error(
                report,
                "null_reason column and value_columns are required when null reasons are enforced",
                manifest_path=manifest_path,
                dataset_index=dataset_index,
            )
            return None
        null_value_columns = tuple(_text(item) or "" for item in raw_value_columns)
        if any(not item for item in null_value_columns):
            _contract_error(
                report,
                "null_reason.value_columns must contain non-empty column names",
                manifest_path=manifest_path,
                dataset_index=dataset_index,
            )
            return None

    return _DatasetContract(
        raw_path=raw_path,
        data_format=data_format,
        event_time=event_time,
        event_time_semantics=event_semantics,
        known_at=known_at,
        known_at_semantics=known_semantics,
        eligible_from=eligible_from,
        eligible_policy=eligible_policy,
        decision_time=decision_time,
        revision_policy=revision_policy,
        revision_key=revision_key,
        null_policy=null_policy,
        null_reason=null_reason_column,
        null_value_columns=null_value_columns,
    )


def _required_columns(contract: _DatasetContract) -> list[str]:
    columns = [contract.event_time, contract.known_at]
    if contract.eligible_from:
        columns.append(contract.eligible_from)
    if contract.decision_time:
        columns.append(contract.decision_time)
    columns.extend(contract.revision_key)
    if contract.null_reason:
        columns.append(contract.null_reason)
    columns.extend(contract.null_value_columns)
    return list(dict.fromkeys(columns))


def _audit_dataset(
    spec: Mapping[str, Any],
    *,
    manifest_path: Path,
    dataset_index: int,
) -> AuditReport:
    report = AuditReport()
    contract = _parse_contract(
        spec,
        manifest_path=manifest_path,
        dataset_index=dataset_index,
        report=report,
    )
    if contract is None:
        return report

    dataset_path = Path(contract.raw_path)
    if not dataset_path.is_absolute():
        dataset_path = manifest_path.parent / dataset_path
    dataset_path = dataset_path.resolve()
    if not dataset_path.is_file():
        report.findings.append(
            _finding(
                "MAN005",
                "dataset file does not exist",
                path=dataset_path,
                details={"dataset_index": dataset_index},
            )
        )
        return report

    with dataset_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in _required_columns(contract) if column not in fieldnames]
        if missing:
            report.findings.append(
                _finding(
                    "MAN007",
                    f"dataset is missing required column(s): {', '.join(missing)}",
                    path=dataset_path,
                    details={"dataset_index": dataset_index, "columns": missing},
                )
            )
            return report
        rows = list(reader)

    if contract.eligible_policy == "explicit_column" and contract.eligible_from:
        for row_index, row in enumerate(rows):
            if _blank(row.get(contract.eligible_from)):
                report.findings.append(
                    Finding(
                        "TIME005",
                        "error",
                        "explicit eligible_from value is missing",
                        row=row_index,
                        column=contract.eligible_from,
                        details={
                            "path": str(dataset_path),
                            "source_kind": "dataset",
                            "dataset_index": dataset_index,
                        },
                    )
                )

    availability = audit_availability(
        rows,
        known_at=contract.known_at,
        eligible_from=contract.eligible_from,
        decision_time=contract.decision_time,
    )
    for finding in availability.findings:
        finding.details.setdefault("path", str(dataset_path))
        finding.details.setdefault("source_kind", "dataset")
        finding.details.setdefault("dataset_index", dataset_index)
    report.extend(availability)

    if contract.revision_policy == "append_only_vintages":
        seen: dict[tuple[str, ...], set[str]] = {}
        for row_index, row in enumerate(rows):
            missing_key_columns = [
                column for column in contract.revision_key if _blank(row.get(column))
            ]
            if missing_key_columns:
                report.findings.append(
                    Finding(
                        "REV002",
                        "error",
                        "logical observation has a missing revision key value",
                        row=row_index,
                        column=missing_key_columns[0],
                        details={
                            "path": str(dataset_path),
                            "source_kind": "dataset",
                            "dataset_index": dataset_index,
                            "revision_key": list(contract.revision_key),
                            "missing_key_columns": missing_key_columns,
                        },
                    )
                )
                continue
            key = tuple(row[column] for column in contract.revision_key)
            known = row.get(contract.known_at, "")
            known_values = seen.setdefault(key, set())
            if known in known_values:
                report.findings.append(
                    Finding(
                        "REV001",
                        "error",
                        "logical observation has duplicate revision availability time",
                        row=row_index,
                        details={
                            "path": str(dataset_path),
                            "source_kind": "dataset",
                            "dataset_index": dataset_index,
                            "revision_key": list(contract.revision_key),
                            "key": list(key),
                            "known_at": known,
                        },
                    )
                )
            known_values.add(known)

    if contract.null_policy == "required_when_value_missing" and contract.null_reason:
        for row_index, row in enumerate(rows):
            missing_values = [
                column for column in contract.null_value_columns if _blank(row.get(column))
            ]
            if missing_values and _blank(row.get(contract.null_reason)):
                report.findings.append(
                    Finding(
                        "NULL001",
                        "error",
                        "missing value requires a null reason",
                        row=row_index,
                        column=contract.null_reason,
                        details={
                            "path": str(dataset_path),
                            "source_kind": "dataset",
                            "dataset_index": dataset_index,
                            "missing_value_columns": missing_values,
                        },
                    )
                )
    return report


def audit_manifest(path: str | Path) -> AuditReport:
    """Validate a JSON temporal-contract manifest and referenced CSV datasets."""

    manifest_path = Path(path)
    report = AuditReport()
    if not manifest_path.is_file():
        report.findings.append(
            _finding("MAN001", "manifest file does not exist", path=manifest_path)
        )
        return report

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.findings.append(
            _finding(
                "MAN001", f"cannot parse manifest JSON: {exc}", path=manifest_path
            )
        )
        return report

    if not isinstance(payload, dict):
        report.findings.append(
            _finding("MAN001", "manifest root must be a JSON object", path=manifest_path)
        )
        return report
    if payload.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        report.findings.append(
            _finding(
                "MAN002",
                f"schema_version must be {MANIFEST_SCHEMA_VERSION}",
                path=manifest_path,
            )
        )
        return report

    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        report.findings.append(
            _finding("MAN003", "datasets must be a non-empty list", path=manifest_path)
        )
        return report

    for index, spec in enumerate(datasets):
        if not isinstance(spec, dict):
            report.findings.append(
                _finding(
                    "MAN004",
                    "each dataset entry must be a JSON object",
                    path=manifest_path,
                    details={"dataset_index": index},
                )
            )
            continue
        report.extend(
            _audit_dataset(spec, manifest_path=manifest_path, dataset_index=index)
        )
    return report
