"""Show how one future feature can inflate chronological holdout metrics.

This is a deterministic synthetic impact demonstration, not an estimate of how
much leakage inflates metrics in real projects.  The same linear model and the
same chronological split are evaluated twice: once with causal lag/current
features and once with the next observation exposed as an unavailable feature.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np

from nofuturedata import audit_python_source


SEED = 20260917
OBSERVATIONS = 2400
TRAIN_ROWS = 1600
AR_COEFFICIENT = 0.8
TARGET_NOISE = 0.15


def _fit_ols(features: np.ndarray, target: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(features)), features])
    coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
    return coefficients


def _predict(features: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(features)), features])
    return design @ coefficients


def _metrics(target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    residual = target - prediction
    mse = float(np.mean(residual**2))
    denominator = float(np.sum((target - np.mean(target)) ** 2))
    r2 = 1.0 - float(np.sum(residual**2)) / denominator
    return {"rmse": float(np.sqrt(mse)), "r2": r2}


def run() -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    series = np.empty(OBSERVATIONS + 2, dtype=float)
    series[0] = 0.0
    innovations = rng.normal(0.0, 1.0, size=OBSERVATIONS + 1)
    for index in range(1, len(series)):
        series[index] = AR_COEFFICIENT * series[index - 1] + innovations[index - 1]

    lag = series[:OBSERVATIONS]
    current = series[1 : OBSERVATIONS + 1]
    future = series[2 : OBSERVATIONS + 2]
    target = future + rng.normal(0.0, TARGET_NOISE, size=OBSERVATIONS)

    causal_features = np.column_stack([lag, current])
    leaking_features = np.column_stack([lag, current, future])

    train = slice(0, TRAIN_ROWS)
    test = slice(TRAIN_ROWS, OBSERVATIONS)
    causal_coefficients = _fit_ols(causal_features[train], target[train])
    leaking_coefficients = _fit_ols(leaking_features[train], target[train])

    causal_metrics = _metrics(
        target[test], _predict(causal_features[test], causal_coefficients)
    )
    leaking_metrics = _metrics(
        target[test], _predict(leaking_features[test], leaking_coefficients)
    )
    r2_inflation = leaking_metrics["r2"] - causal_metrics["r2"]
    rmse_ratio = leaking_metrics["rmse"] / causal_metrics["rmse"]

    safe_source = "lag = series.shift(1)\n"
    leaking_source = "future = series.shift(-1)\n"
    safe_scan = audit_python_source(safe_source)
    leaking_scan = audit_python_source(leaking_source)
    leaking_codes = [finding.code for finding in leaking_scan.findings]

    checks = {
        "chronological_holdout_nonempty": TRAIN_ROWS < OBSERVATIONS,
        "safe_source_stays_clean": safe_scan.ok,
        "future_shift_is_detected": leaking_codes == ["SRC001"],
        "causal_model_is_nontrivial": 0.45 <= causal_metrics["r2"] <= 0.80,
        "leaked_model_is_near_perfect": leaking_metrics["r2"] >= 0.98,
        "r2_inflation_is_material": r2_inflation >= 0.20,
        "leaked_rmse_collapses": rmse_ratio <= 0.30,
    }

    return {
        "schema_version": "nofuturedata-downstream-impact-v1",
        "seed": SEED,
        "numpy_version": np.__version__,
        "observations": OBSERVATIONS,
        "train_rows": TRAIN_ROWS,
        "test_rows": OBSERVATIONS - TRAIN_ROWS,
        "data_generating_process": {
            "ar_coefficient": AR_COEFFICIENT,
            "target_noise_std": TARGET_NOISE,
            "target": "next latent observation plus independent noise",
        },
        "causal_features": ["lag", "current"],
        "leaking_features": ["lag", "current", "future"],
        "causal_metrics": causal_metrics,
        "leaking_metrics": leaking_metrics,
        "r2_inflation": r2_inflation,
        "rmse_ratio_leak_over_causal": rmse_ratio,
        "scanner": {
            "safe_codes": [finding.code for finding in safe_scan.findings],
            "leaking_codes": leaking_codes,
        },
        "checks": checks,
        "ok": all(checks.values()),
        "claim_limit": (
            "This fixed-seed synthetic experiment demonstrates a mechanism by which a future "
            "feature can inflate chronological holdout metrics. It is not an estimate of "
            "real-world metric inflation or model performance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(
            "NoFutureData downstream metric inflation: {} "
            "(causal R2={:.3f}, leaked R2={:.3f}, delta={:.3f})".format(
                state,
                result["causal_metrics"]["r2"],
                result["leaking_metrics"]["r2"],
                result["r2_inflation"],
            )
        )
        print(
            "causal RMSE={:.3f}; leaked RMSE={:.3f}; ratio={:.3f}".format(
                result["causal_metrics"]["rmse"],
                result["leaking_metrics"]["rmse"],
                result["rmse_ratio_leak_over_causal"],
            )
        )
        print(result["claim_limit"])
        for name, passed in result["checks"].items():
            print(f"{'PASS' if passed else 'FAIL':4} {name}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
