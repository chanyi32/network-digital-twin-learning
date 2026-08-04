# Changelog

## 0.1.1 - 2026-07-31

- Added the configuration flag `optimization.feedback_enabled`.
- The default is `true`; the v0.1.0 decision algorithms, model formulas,
  coefficients, constraints, weights, action space, and enabled-feedback
  behavior are unchanged.
- When set to `false`, the pipeline evaluates and scores generation round 0,
  writes no feedback artifact, creates no later generation, and terminates
  with `feedback_disabled`.
- Added truthful feedback execution metadata to core and experiment manifests
  and aggregate CSV outputs.
- Added the minimal six-case pilot runner and validation summaries.

## 0.1.0 - 2026-07-31

- Frozen initial single-cell RAN intent simulation baseline.
- Frozen `simplified-ran-v1` performance model.
