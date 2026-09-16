---
layout: default
title: Why temporal leakage deserves a CI guard
permalink: /WHY.html
---

# Why temporal leakage deserves a CI guard

Temporal leakage is not limited to trading. It appears whenever a historical
training row, evaluation, forecast, or decision accidentally uses information
that became available later.

The failure mode is unusually dangerous because it tends to improve offline
metrics. A leaking pipeline can therefore look *more* convincing as it becomes
less valid.

## Evidence that the problem is broader than one framework

- Kapoor and Narayanan's 2023 review, *Leakage and the reproducibility crisis in
  machine-learning-based science*, reports leakage across 294 papers spanning 17
  scientific fields. DOI: https://doi.org/10.1016/j.patter.2023.100804
- scikit-learn provides `TimeSeriesSplit` and a `gap` parameter because ordinary
  shuffled or i.i.d. cross-validation is inappropriate for ordered observations:
  https://scikit-learn.org/stable/modules/cross_validation.html#time-series-split
- Feast makes point-in-time correct historical feature retrieval a core feature
  so future feature values do not leak into model training:
  https://docs.feast.dev/
- Freqtrade ships a dedicated `lookahead-analysis` command because full-dataframe
  backtests can accidentally read future candles and report unrealistic results:
  https://docs.freqtrade.io/en/latest/lookahead-analysis/

These tools address important parts of the problem in their own domains. The
remaining practical gap NoFutureData targets is a small, local guard that can be
added to an ordinary Python/Jupyter repository without adopting a feature store,
backtesting engine, or ML framework.

## Where NoFutureData fits

| Tool | Primary strength | Boundary NoFutureData complements |
| --- | --- | --- |
| scikit-learn `TimeSeriesSplit` | chronological train/test splits and an optional gap | does not encode when revised source data became known or eligible, and does not review arbitrary pipeline source |
| Feast | point-in-time-correct historical feature retrieval inside a feature store | assumes the feature-store workflow rather than acting as a repository-wide source/data contract guard |
| Freqtrade `lookahead-analysis` | behavioral lookahead detection for Freqtrade strategy backtests | is specific to Freqtrade strategies and their backtesting/data workflow |
| NoFutureData | repository-local availability contracts, source review gates, point-in-time joins, and invariance checks | deliberately does not replace model evaluation, a feature store, or a domain-specific backtesting engine |

References: scikit-learn documents why ordinary cross-validation is unsuitable
for ordered observations and exposes a `gap` in `TimeSeriesSplit`:
https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
Feast documents point-in-time-correct joins for historical feature retrieval:
https://docs.feast.dev/getting-started/concepts/point-in-time-joins
Freqtrade documents its strategy-specific `lookahead-analysis` workflow:
https://docs.freqtrade.io/en/latest/lookahead-analysis/

## What NoFutureData makes executable

NoFutureData deliberately combines four checks that are often handled
separately:

1. **Availability semantics** — distinguish when an event happened from when the
   information was actually known and eligible for use.
2. **Dataset temporal contracts** — make event-time, known-at, eligibility,
   timezone, revision, and null-reason assumptions executable in CI.
3. **Source review gates** — flag common future-looking operations in Python and
   Jupyter before they enter a pipeline.
4. **Behavioral invariance** — remove or mutate only future inputs and verify that
   already-produced historical outputs do not change.

The core has no runtime dependency and is exposed as a Python API, CLI,
pre-commit hook, SARIF producer, and GitHub Action. The goal is not to replace
domain-specific validation. It is to make a minimum causal boundary cheap enough
to run on every pull request.

## Scope and limitations

Passing NoFutureData does not prove a model, experiment, or backtest is valid.
Survivorship bias, label leakage, train/test contamination, revised source data,
provider publication semantics, and many domain-specific errors require separate
checks. Static rules are intentionally review gates and support explicit inline
suppressions for legitimate label-building code.

The public planted-leak corpus in `benchmarks/` is a conformance suite for shipped
rules, not a claim of universal leakage recall. New rules should be driven by
minimal real-world reproductions and paired with a safe control.
