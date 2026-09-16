"""Public API for nofuturedata."""

from .audit import (
    AuditReport,
    Finding,
    as_of,
    audit_availability,
    audit_python_source,
    future_mutation_invariance,
    prefix_invariance,
)

__all__ = [
    "AuditReport",
    "Finding",
    "as_of",
    "audit_availability",
    "audit_python_source",
    "future_mutation_invariance",
    "prefix_invariance",
]

__version__ = "0.1.0"

