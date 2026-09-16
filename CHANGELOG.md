# Changelog

All notable changes to NoFutureData are documented here.

## 0.2.0 - 2026-09-16

- Scan Python code cells in Jupyter notebooks.
- Accept multiple paths in `nofuture scan` for pre-commit compatibility.
- Add SARIF 2.1.0 export for GitHub Code Scanning and other SARIF consumers.
- Add a reusable pre-commit hook.
- Extend the GitHub Action with optional SARIF upload while preserving scan exit status.
- Add targeted (`nofuture: ignore[SRCxxx]`) and generic inline suppressions.

## 0.1.0 - 2026-09-16

- Add fail-closed availability auditing with timezone-aware `known_at` and
  `eligible_from` semantics.
- Add `as_of` filtering for historically available records.
- Add Python AST checks for negative shifts, backfill, centered rolling windows,
  and forward/nearest as-of joins.
- Add prefix-invariance and future-mutation runtime tests.
- Add CLI, GitHub Action, CI matrix, examples, and contributor documentation.
