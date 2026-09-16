"""Optional pandas helpers for fail-closed point-in-time joins."""

from __future__ import annotations

from datetime import timezone
from typing import Any, Sequence

from .audit import _aware_datetime


def _load_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - depends on caller environment
        raise ImportError(
            "point_in_time_join requires the optional pandas extra; "
            "install with `python -m pip install 'nofuturedata[pandas]'` "
            "or install pandas>=2.1 alongside NoFutureData"
        ) from exc
    return pd


def _normalize_by(by: str | Sequence[str] | None) -> list[str]:
    if by is None:
        return []
    if isinstance(by, str):
        return [by]
    columns = list(by)
    if not all(isinstance(column, str) and column for column in columns):
        raise TypeError("by must contain only non-empty column names")
    return columns


def _require_columns(frame: Any, columns: Sequence[str], *, side: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        joined = ", ".join(repr(column) for column in missing)
        raise ValueError(f"{side} frame is missing required column(s): {joined}")


def _temporary_column_name(left: Any, right: Any, stem: str) -> str:
    name = stem
    counter = 2
    while name in left.columns or name in right.columns:
        name = f"{stem}_{counter}"
        counter += 1
    return name


def _is_missing(value: Any, pd: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    missing = pd.isna(value)
    return bool(missing) if isinstance(missing, bool) else False


def _parse_timestamp_series(
    series: Any,
    *,
    field_name: str,
    side: str,
    pd: Any,
) -> Any:
    parsed = []
    for position, raw in enumerate(series.tolist()):
        if _is_missing(raw, pd):
            raise ValueError(f"{side} row {position} has missing {field_name!r}")
        try:
            value = _aware_datetime(raw, field_name=field_name)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{side} row {position}: {exc}") from None
        parsed.append(value.astimezone(timezone.utc))
    return pd.to_datetime(parsed, utc=True)


def point_in_time_join(
    left: Any,
    right: Any,
    *,
    decision_time: str,
    known_at: str = "known_at",
    eligible_from: str | None = "eligible_from",
    by: str | Sequence[str] | None = None,
    suffixes: tuple[str, str] = ("_x", "_right"),
) -> Any:
    """Join each decision row to the latest right row available at that time.

    The function is intentionally backward-only: a right-side row is eligible
    only when its availability timestamp is less than or equal to the left-side
    decision timestamp. ``eligible_from`` is used when present and falls back to
    ``known_at`` for rows without an explicit eligibility timestamp.

    All decision and availability timestamps must be timezone-aware. When both
    availability fields are present, ``eligible_from`` must not precede
    ``known_at``. Duplicate right rows with the same ``by`` keys and availability
    time are rejected because silently choosing one would make revision/vintage
    behavior dependent on row order.

    ``by`` columns are exact-match keys. For revised observations, include the
    stable observation identity (for example ``["series", "event_time"]``) so
    later vintages can replace earlier vintages only after they become available.

    pandas is imported lazily and remains an optional dependency of NoFutureData.
    The input frames are copied and are never mutated.
    """

    pd = _load_pandas()
    if not isinstance(left, pd.DataFrame) or not isinstance(right, pd.DataFrame):
        raise TypeError("left and right must both be pandas.DataFrame objects")
    if not isinstance(decision_time, str) or not decision_time:
        raise TypeError("decision_time must be a non-empty column name")
    if not isinstance(known_at, str) or not known_at:
        raise TypeError("known_at must be a non-empty column name")
    if eligible_from is not None and (
        not isinstance(eligible_from, str) or not eligible_from
    ):
        raise TypeError("eligible_from must be a non-empty column name or None")
    if (
        not isinstance(suffixes, tuple)
        or len(suffixes) != 2
        or not all(isinstance(item, str) for item in suffixes)
    ):
        raise TypeError("suffixes must be a two-item tuple of strings")

    by_columns = _normalize_by(by)
    _require_columns(left, [decision_time, *by_columns], side="left")
    _require_columns(right, [known_at, *by_columns], side="right")

    left_work = left.copy()
    right_work = right.copy()

    for side, frame in (("left", left_work), ("right", right_work)):
        if by_columns and frame[by_columns].isna().any(axis=None):
            raise ValueError(f"{side} frame contains missing values in by columns")

    decision_key = _temporary_column_name(
        left_work, right_work, "__nofuture_decision_time"
    )
    availability_key = _temporary_column_name(
        left_work, right_work, "__nofuture_available_at"
    )
    order_key = _temporary_column_name(left_work, right_work, "__nofuture_left_order")

    left_work[decision_key] = _parse_timestamp_series(
        left_work[decision_time],
        field_name=decision_time,
        side="left",
        pd=pd,
    )
    left_work[order_key] = range(len(left_work))

    known_values = _parse_timestamp_series(
        right_work[known_at],
        field_name=known_at,
        side="right",
        pd=pd,
    )
    availability_values = known_values.copy()

    if eligible_from and eligible_from in right_work.columns:
        parsed_availability = []
        for position, (raw, known) in enumerate(
            zip(right_work[eligible_from].tolist(), known_values.tolist())
        ):
            if _is_missing(raw, pd):
                parsed_availability.append(known)
                continue
            try:
                eligible = _aware_datetime(raw, field_name=eligible_from).astimezone(
                    timezone.utc
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"right row {position}: {exc}") from None
            known_python = known.to_pydatetime()
            if eligible < known_python:
                raise ValueError(
                    f"right row {position} has {eligible_from!r} before {known_at!r}"
                )
            parsed_availability.append(eligible)
        availability_values = pd.to_datetime(parsed_availability, utc=True)

    right_work[availability_key] = availability_values

    duplicate_keys = [*by_columns, availability_key]
    duplicate_mask = right_work.duplicated(subset=duplicate_keys, keep=False)
    if duplicate_mask.any():
        sample = right_work.loc[duplicate_mask, duplicate_keys].iloc[0].to_dict()
        raise ValueError(
            "right frame has ambiguous duplicate availability keys; "
            f"first duplicate: {sample!r}"
        )

    left_sorted = left_work.sort_values(
        [decision_key, *by_columns], kind="mergesort"
    )
    right_sorted = right_work.sort_values(
        [availability_key, *by_columns], kind="mergesort"
    )

    result = pd.merge_asof(
        left_sorted,
        right_sorted,
        left_on=decision_key,
        right_on=availability_key,
        by=by_columns or None,
        direction="backward",
        allow_exact_matches=True,
        suffixes=suffixes,
    )
    result = result.sort_values(order_key, kind="mergesort")
    result = result.drop(columns=[decision_key, availability_key, order_key])
    result.index = left.index.copy()
    return result
