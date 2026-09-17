"""Deterministic checks for temporal data leakage.

The package intentionally separates *event time* from *availability time*.  A row
may describe an event in the past or future; the key causal question is when the
consumer could actually have known the row.
"""

from __future__ import annotations

import ast
import copy
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    row: int | None = None
    line: int | None = None
    column: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)
    rows_scanned: int = 0

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)

    def extend(self, other: "AuditReport") -> None:
        self.findings.extend(other.findings)
        self.rows_scanned += other.rows_scanned

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rows_scanned": self.rows_scanned,
            "finding_count": len(self.findings),
            "findings": [asdict(item) for item in self.findings],
        }


def _aware_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    else:
        raise ValueError(f"{field_name} must be an ISO-8601 string or datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")
    return parsed


def audit_availability(
    records: Iterable[Mapping[str, Any]],
    *,
    known_at: str = "known_at",
    eligible_from: str | None = "eligible_from",
    decision_time: str | None = None,
) -> AuditReport:
    """Audit availability timestamps and optional decision-time causality.

    Rules are deliberately small and general:
    - ``known_at`` must exist and be timezone-aware.
    - when present, ``eligible_from`` cannot precede ``known_at``.
    - when a decision-time column is supplied, the row's availability must not
      be later than the decision.

    ``event_time <= known_at`` is *not* assumed: scheduled future events can be
    legitimately known before they occur.
    """

    report = AuditReport()
    for row_index, record in enumerate(records):
        report.rows_scanned += 1
        try:
            known = _aware_datetime(record.get(known_at), field_name=known_at)
        except (TypeError, ValueError) as exc:
            report.findings.append(
                Finding(
                    "TIME001",
                    "error",
                    str(exc),
                    row=row_index,
                    column=known_at,
                )
            )
            continue

        available = known
        if eligible_from:
            raw_eligible = record.get(eligible_from)
            if raw_eligible not in (None, ""):
                try:
                    eligible = _aware_datetime(
                        raw_eligible, field_name=eligible_from
                    )
                except (TypeError, ValueError) as exc:
                    report.findings.append(
                        Finding(
                            "TIME002",
                            "error",
                            str(exc),
                            row=row_index,
                            column=eligible_from,
                        )
                    )
                    continue
                if eligible < known:
                    report.findings.append(
                        Finding(
                            "TIME003",
                            "error",
                            f"{eligible_from} precedes {known_at}",
                            row=row_index,
                            column=eligible_from,
                            details={
                                known_at: known.isoformat(),
                                eligible_from: eligible.isoformat(),
                            },
                        )
                    )
                available = eligible

        if decision_time:
            try:
                decision = _aware_datetime(
                    record.get(decision_time), field_name=decision_time
                )
            except (TypeError, ValueError) as exc:
                report.findings.append(
                    Finding(
                        "TIME004",
                        "error",
                        str(exc),
                        row=row_index,
                        column=decision_time,
                    )
                )
                continue
            if available > decision:
                report.findings.append(
                    Finding(
                        "LEAK001",
                        "error",
                        "record was not available at decision time",
                        row=row_index,
                        details={
                            "available_at": available.isoformat(),
                            "decision_time": decision.isoformat(),
                        },
                    )
                )
    return report


def as_of(
    records: Iterable[Mapping[str, Any]],
    cutoff: str | datetime,
    *,
    availability: str = "eligible_from",
    fallback: str = "known_at",
) -> list[dict[str, Any]]:
    """Return only rows available on or before ``cutoff``.

    A missing primary availability timestamp falls back to ``known_at``.  If
    neither timestamp exists, the function fails closed instead of guessing.
    """

    boundary = _aware_datetime(cutoff, field_name="cutoff")
    result: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        primary_raw = record.get(availability)
        fallback_raw = record.get(fallback)
        raw = primary_raw
        field_name = availability
        if raw in (None, ""):
            raw = fallback_raw
            field_name = fallback
        if raw in (None, ""):
            raise ValueError(
                f"row {index} has neither {availability!r} nor {fallback!r}"
            )
        available = _aware_datetime(raw, field_name=field_name)
        if (
            primary_raw not in (None, "")
            and fallback_raw not in (None, "")
            and availability != fallback
        ):
            known = _aware_datetime(fallback_raw, field_name=fallback)
            if available < known:
                raise ValueError(
                    f"row {index} has {availability!r} before {fallback!r}"
                )
        if available <= boundary:
            result.append(dict(record))
    return result


class _LeakVisitor(ast.NodeVisitor):
    def __init__(self, source: str, *, temporal_context: str | None = None) -> None:
        self.findings: list[Finding] = []
        self.lines = source.splitlines()
        self.temporal_context = temporal_context

    def _suppressed(self, node: ast.AST, code: str) -> bool:
        line_number = getattr(node, "lineno", None)
        if line_number is None or not (1 <= line_number <= len(self.lines)):
            return False
        line = self.lines[line_number - 1]
        generic = "nofuture: ignore"
        targeted = f"nofuture: ignore[{code}]"
        if targeted in line:
            return True
        # A bare ignore intentionally suppresses every finding emitted on that
        # source line; a targeted ignore suppresses only its rule.
        return generic in line and "nofuture: ignore[" not in line

    def _add(self, node: ast.AST, code: str, message: str) -> None:
        if self._suppressed(node, code):
            return
        self.findings.append(
            Finding(
                code,
                "error",
                message,
                line=getattr(node, "lineno", None),
            )
        )

    @staticmethod
    def _attr_name(node: ast.AST) -> str | None:
        return node.attr if isinstance(node, ast.Attribute) else None

    @staticmethod
    def _argument(node: ast.Call, position: int, keyword_name: str) -> ast.AST | None:
        if len(node.args) > position:
            return node.args[position]
        for keyword in node.keywords:
            if keyword.arg == keyword_name:
                return keyword.value
        return None

    @staticmethod
    def _keyword_argument(node: ast.Call, keyword_name: str) -> ast.AST | None:
        for keyword in node.keywords:
            if keyword.arg == keyword_name:
                return keyword.value
        return None

    @staticmethod
    def _is_negative_number(node: ast.AST | None) -> bool:
        return (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float))
        )

    @staticmethod
    def _literal_string(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value.lower()
        return None

    @staticmethod
    def _resample_rule_defaults_left(rule: str | None) -> bool:
        """Recognize literal frequencies whose pandas resample label defaults left.

        This stays deliberately narrow: dynamic frequencies and month/quarter/
        year/week-end aliases are left to review because their defaults differ.
        """

        if not rule:
            return False
        compact = rule.replace(" ", "").lower()
        if compact.endswith(("w", "me", "ye", "qe", "bme", "bye", "bqe")):
            return False
        return compact.endswith(
            (
                "h",
                "hour",
                "hours",
                "min",
                "minute",
                "minutes",
                "t",
                "s",
                "sec",
                "second",
                "seconds",
                "ms",
                "us",
                "ns",
                "d",
                "day",
                "days",
            )
        )

    @staticmethod
    def _root_name(node: ast.AST | None) -> str | None:
        current = node
        while isinstance(current, (ast.Attribute, ast.Subscript)):
            current = current.value
        return current.id if isinstance(current, ast.Name) else None

    def visit_Assign(self, node: ast.Assign) -> Any:
        # Conservatively gate whole-series aggregates only when they are written
        # back as a feature on the same dataframe object.  This avoids flagging
        # reporting/statistics code such as `summary = series.mean()` and skips
        # windowed/grouped receivers, whose receiver is itself a Call node.
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            aggregate = node.value.func.attr
            receiver = node.value.func.value
            if aggregate in {"mean", "median", "min", "max", "sum", "std", "var"} and isinstance(
                receiver, (ast.Attribute, ast.Subscript)
            ):
                receiver_root = self._root_name(receiver)
                for target in node.targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and receiver_root is not None
                        and self._root_name(target) == receiver_root
                    ):
                        self._add(
                            node.value,
                            "SRC008",
                            "whole-series aggregate assigned back to the same dataframe can use future rows",
                        )
                        break
        return self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        # Negative absolute iloc positions select rows from the end of the full
        # object.  In vectorized feature/backtest code this commonly exposes a
        # future row to earlier decisions.  Dynamic iloc expressions are left to
        # behavioral checks because their direction cannot be inferred safely.
        if (
            isinstance(node.value, ast.Attribute)
            and node.value.attr == "iloc"
            and self._is_negative_number(node.slice)
        ):
            self._add(
                node,
                "SRC009",
                "negative absolute iloc indexing can select a future row from the full dataset",
            )
        return self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        name = node.func.id if isinstance(node.func, ast.Name) else self._attr_name(node.func)
        if self.temporal_context == "time_series":
            if (
                name == "roll"
                and isinstance(node.func, ast.Attribute)
                and self._root_name(node.func) in {"np", "numpy"}
            ):
                shift = self._argument(node, 1, "shift")
                if self._is_negative_number(shift):
                    self._add(
                        node,
                        "SRC012",
                        "negative NumPy roll moves later values into earlier positions in time-series data",
                    )
            if name in {
                "KFold",
                "StratifiedKFold",
                "RepeatedKFold",
                "RepeatedStratifiedKFold",
                "ShuffleSplit",
                "StratifiedShuffleSplit",
                "GroupKFold",
                "GroupShuffleSplit",
            }:
                self._add(
                    node,
                    "SRC011",
                    "generic/random/group cross-validation can train on future observations in time-series evaluation",
                )
            elif name == "train_test_split":
                shuffle = self._keyword_argument(node, "shuffle")
                if shuffle is None or (
                    isinstance(shuffle, ast.Constant) and shuffle.value is True
                ):
                    self._add(
                        node,
                        "SRC011",
                        "shuffled train/test splitting can mix future observations into time-series evaluation",
                    )
            elif name in {
                "cross_val_score",
                "cross_validate",
                "cross_val_predict",
                "learning_curve",
                "validation_curve",
                "permutation_test_score",
                "GridSearchCV",
                "RandomizedSearchCV",
            }:
                cv = self._keyword_argument(node, "cv")
                uses_default_or_integer_cv = cv is None or (
                    isinstance(cv, ast.Constant)
                    and (
                        cv.value is None
                        or (
                            isinstance(cv.value, int)
                            and not isinstance(cv.value, bool)
                            and cv.value >= 2
                        )
                    )
                )
                if uses_default_or_integer_cv:
                    self._add(
                        node,
                        "SRC011",
                        "default/integer cross-validation can use IID folds that train on future observations in time-series evaluation",
                    )
        if name in {
            "mean",
            "median",
            "min",
            "max",
            "sum",
            "std",
            "var",
            "first",
            "last",
            "ohlc",
            "count",
            "size",
            "nunique",
        } and isinstance(node.func, ast.Attribute):
            receiver = node.func.value
            if (
                isinstance(receiver, ast.Call)
                and isinstance(receiver.func, ast.Attribute)
                and receiver.func.attr == "resample"
            ):
                rule = self._literal_string(self._argument(receiver, 0, "rule"))
                label = self._literal_string(self._keyword_argument(receiver, "label"))
                if label == "left" or (
                    label is None and self._resample_rule_defaults_left(rule)
                ):
                    self._add(
                        node,
                        "SRC010",
                        "left-labeled resample aggregation can timestamp later interval values at the interval start",
                    )
        if name == "shift":
            value = self._argument(node, 0, "periods")
            temporal_dimension_shift = any(
                keyword.arg in {"time", "date", "datetime", "timestamp"}
                and self._is_negative_number(keyword.value)
                for keyword in node.keywords
            )
            if self._is_negative_number(value) or temporal_dimension_shift:
                self._add(
                    node,
                    "SRC001",
                    "negative shift can read future rows",
                )
        if name in {"bfill", "backfill"}:
            self._add(
                node,
                "SRC002",
                "backfilling can copy future observations into the past",
            )
        if name == "rolling":
            for keyword in node.keywords:
                if keyword.arg == "center" and isinstance(
                    keyword.value, ast.Constant
                ) and keyword.value.value is True:
                    self._add(
                        node,
                        "SRC003",
                        "centered rolling windows can include future rows",
                    )
        if name == "merge_asof":
            for keyword in node.keywords:
                if keyword.arg == "direction" and isinstance(
                    keyword.value, ast.Constant
                ) and keyword.value.value in {"forward", "nearest"}:
                    self._add(
                        node,
                        "SRC004",
                        "forward/nearest merge_asof may select a future row",
                    )
        if name in {"diff", "pct_change"}:
            periods = self._argument(node, 0, "periods")
            if self._is_negative_number(periods):
                self._add(
                    node,
                    "SRC005",
                    "negative diff/pct_change periods can read future rows",
                )
        if name == "fillna":
            method = self._literal_string(self._keyword_argument(node, "method"))
            if method in {"bfill", "backfill"}:
                self._add(
                    node,
                    "SRC006",
                    "backward fillna can copy future observations into the past",
                )
        if name == "interpolate":
            direction = self._literal_string(
                self._keyword_argument(node, "limit_direction")
            )
            if direction in {"backward", "both"}:
                self._add(
                    node,
                    "SRC007",
                    "backward/both interpolation can use later observations",
                )
        return self.generic_visit(node)


def audit_python_source(
    source: str,
    *,
    filename: str = "<memory>",
    temporal_context: str | None = None,
) -> AuditReport:
    """Statically flag common future-looking pandas patterns.

    This is a heuristic linter.  Runtime invariance checks should be used as the
    stronger test for transformed signals/features.
    """

    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return AuditReport(
            findings=[
                Finding(
                    "SRC000",
                    "error",
                    f"cannot parse Python source: {exc.msg}",
                    line=exc.lineno,
                )
            ],
            rows_scanned=len(source.splitlines()),
        )
    if temporal_context not in {None, "time_series"}:
        raise ValueError("temporal_context must be None or 'time_series'")
    visitor = _LeakVisitor(source, temporal_context=temporal_context)
    visitor.visit(tree)
    return AuditReport(
        findings=visitor.findings,
        rows_scanned=len(source.splitlines()),
    )


def audit_notebook_source(
    source: str,
    *,
    filename: str = "<memory>.ipynb",
    temporal_context: str | None = None,
) -> AuditReport:
    """Scan Python code cells in a Jupyter notebook.

    Notebook findings keep the cell-local line number and add ``cell`` and
    ``path`` metadata so CLI/SARIF consumers can point back to the source.
    Non-Python notebooks are ignored rather than parsed as Python.
    """

    try:
        notebook = json.loads(source)
    except json.JSONDecodeError as exc:
        return AuditReport(
            findings=[
                Finding(
                    "SRC000",
                    "error",
                    f"cannot parse Jupyter notebook JSON: {exc.msg}",
                    line=exc.lineno,
                    details={"path": filename, "source_kind": "notebook"},
                )
            ],
            rows_scanned=len(source.splitlines()),
        )

    language = (
        notebook.get("metadata", {})
        .get("kernelspec", {})
        .get("language", "python")
    )
    if str(language).lower() not in {"python", "python3"}:
        return AuditReport()

    combined = AuditReport()
    for cell_index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        raw_source = cell.get("source", "")
        cell_source = "".join(raw_source) if isinstance(raw_source, list) else str(raw_source)
        cell_source = _normalize_notebook_python(cell_source)
        if cell_source is None:
            continue
        report = audit_python_source(
            cell_source,
            filename=f"{filename}#cell-{cell_index + 1}",
            temporal_context=temporal_context,
        )
        for finding in report.findings:
            finding.details.update(
                {
                    "path": filename,
                    "cell": cell_index + 1,
                    "source_kind": "notebook",
                }
            )
        combined.extend(report)
    return combined


def _normalize_notebook_python(source: str) -> str | None:
    """Return parseable Python while preserving notebook cell line numbers.

    IPython line magics and shell escapes are replaced with blank lines. Common
    Python-executing cell magics keep their body; non-Python cell magics are
    skipped because parsing shell/SQL/R/etc. as Python would create false
    configuration failures.
    """

    lines = source.splitlines(keepends=True)
    first_content: int | None = None
    for index, line in enumerate(lines):
        if line.strip():
            first_content = index
            break

    if first_content is not None:
        stripped = lines[first_content].lstrip()
        if stripped.startswith("%%"):
            magic = stripped[2:].split(None, 1)[0].lower() if stripped[2:].strip() else ""
            if magic not in {"time", "timeit", "capture"}:
                return None
            lines[first_content] = "\n" if lines[first_content].endswith("\n") else ""

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("%") or stripped.startswith("!") or stripped.startswith("?"):
            lines[index] = "\n" if line.endswith("\n") else ""
    return "".join(lines)


def _default_cut_points(length: int) -> list[int]:
    if length < 2:
        return []
    candidates = {1, length // 4, length // 2, (3 * length) // 4, length - 1}
    return sorted(point for point in candidates if 0 < point < length)


def prefix_invariance(
    transform: Callable[[Sequence[Any]], Sequence[Any]],
    rows: Sequence[Any],
    *,
    cut_points: Sequence[int] | None = None,
) -> AuditReport:
    """Check whether historical outputs change when future rows are removed."""

    full = list(transform(rows))
    points = list(cut_points) if cut_points is not None else _default_cut_points(len(rows))
    report = AuditReport(rows_scanned=len(rows))
    for point in points:
        prefix = list(transform(rows[:point]))
        expected = full[:point]
        if prefix != expected:
            report.findings.append(
                Finding(
                    "LEAK101",
                    "error",
                    "prefix output changes when future rows are removed",
                    row=point - 1,
                    details={
                        "prefix_length": point,
                        "expected_length": len(expected),
                        "actual_length": len(prefix),
                    },
                )
            )
    return report


def _mutate_future(rows: Sequence[Any], point: int) -> list[Any]:
    mutated = copy.deepcopy(list(rows))
    for index in range(point, len(mutated)):
        row = mutated[index]
        if not isinstance(row, dict):
            continue
        for key, value in list(row.items()):
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                row[key] = value * 7 + 12345
    return mutated


def future_mutation_invariance(
    transform: Callable[[Sequence[Any]], Sequence[Any]],
    rows: Sequence[Any],
    *,
    cut_points: Sequence[int] | None = None,
    mutator: Callable[[Sequence[Any], int], Sequence[Any]] | None = None,
    input_validator: Callable[[Sequence[Any]], bool] | None = None,
) -> AuditReport:
    """Check whether changing future values alters already-produced outputs.

    ``input_validator`` can encode domain invariants that a mutation must
    preserve (for example probabilities in ``[0, 1]`` or valid OHLC rows).  A
    mutation is rejected rather than interpreted as leakage if it changes the
    historical prefix, changes sequence length, or violates that contract.
    """

    if input_validator is not None and not input_validator(rows):
        raise ValueError("input_validator rejected the original rows")

    full = list(transform(rows))
    points = list(cut_points) if cut_points is not None else _default_cut_points(len(rows))
    change_future = mutator or _mutate_future
    report = AuditReport(rows_scanned=len(rows))
    for point in points:
        changed_rows = list(change_future(rows, point))
        if len(changed_rows) != len(rows):
            raise ValueError(
                f"future mutator changed row count at cut point {point}"
            )
        if changed_rows[:point] != list(rows[:point]):
            raise ValueError(
                f"future mutator changed the historical prefix at cut point {point}"
            )
        if input_validator is not None and not input_validator(changed_rows):
            raise ValueError(
                f"future mutator violated the input contract at cut point {point}"
            )
        changed = list(transform(changed_rows))[:point]
        expected = full[:point]
        if changed != expected:
            report.findings.append(
                Finding(
                    "LEAK102",
                    "error",
                    "historical output changes when only future values are mutated",
                    row=point - 1,
                    details={"prefix_length": point},
                )
            )
    return report


def iter_source_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() in {".py", ".ipynb"}:
            yield path
        return
    ignored = {".git", ".venv", "venv", "build", "dist", "__pycache__"}
    for pattern in ("*.py", "*.ipynb"):
        for candidate in path.rglob(pattern):
            if not any(part in ignored for part in candidate.parts):
                yield candidate


def report_to_sarif(report: AuditReport) -> dict[str, Any]:
    """Convert findings to SARIF 2.1.0 for GitHub Code Scanning."""

    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for finding in report.findings:
        rules.setdefault(
            finding.code,
            {
                "id": finding.code,
                "shortDescription": {"text": finding.message},
                "defaultConfiguration": {
                    "level": "error" if finding.severity == "error" else "warning"
                },
            },
        )
        result: dict[str, Any] = {
            "ruleId": finding.code,
            "level": "error" if finding.severity == "error" else "warning",
            "message": {"text": finding.message},
        }
        path = finding.details.get("path")
        if path:
            physical: dict[str, Any] = {
                "artifactLocation": {"uri": str(path).replace("\\", "/")}
            }
            # A notebook finding's line is cell-local rather than a physical
            # JSON line, so omit a misleading SARIF region for notebooks.
            if finding.line is not None and finding.details.get("source_kind") != "notebook":
                physical["region"] = {"startLine": max(1, finding.line)}
            result["locations"] = [{"physicalLocation": physical}]
        if finding.details.get("cell"):
            result["message"]["text"] += f" (notebook cell {finding.details['cell']})"
        results.append(result)

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "NoFutureData",
                        "informationUri": "https://github.com/ORANGINGS/nofuturedata",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
