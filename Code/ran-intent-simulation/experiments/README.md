# Automated experiments

This directory is an orchestration layer around the v0.1.1
`ran_intent_simulation` package. It does not change core algorithms or model
parameters. v0.1.1 retains the v0.1.0 baseline behavior by default and adds the
experiment-only `optimization.feedback_enabled` execution control. Every case
creates private input copies before calling the existing `SimulationPipeline`.

## Entry points

Run a default experiment from the repository root:

```powershell
.\.venv\python.exe -m experiments baseline_e2e
.\.venv\python.exe -m experiments load_sweep
.\.venv\python.exe -m experiments feedback_compare
.\.venv\python.exe -m experiments weight_sensitivity
```

Each entry point is also directly runnable:

```powershell
.\.venv\python.exe -m experiments.baseline_e2e
```

Run the accepted 31-case formal plan without changing the frozen core:

```powershell
.\.venv\python.exe -m experiments.formal `
  --batch-id formal-experiments-v1-YYYYMMDD
```

The versioned plan is `experiments/configs/formal_experiments_v1.yaml`.

Use a custom YAML file or output location:

```powershell
.\.venv\python.exe -m experiments load_sweep `
  --config experiments/configs/load_sweep.yaml `
  --batch-id load-study-001 `
  --output-root results/experiments
```

`batch-id` must be unique within an experiment output directory. Omitting it
creates a UTC timestamp identifier.

## YAML model

Schema v1.1 defines one fixed seed and one or more cases. Case overrides use
existing dotted paths in `config/simulation_config.yaml`; unknown paths are
rejected. RAN state overrides use existing CSV column names; unknown columns are
also rejected.

A case can be intentionally skipped with:

```yaml
skip: true
skip_reason: documented reason
```

All alternative loads and weights in the example files are simulation
assumptions, not standards, measurements, or deployment recommendations.

## Output

Each batch writes:

```text
results/experiments/<experiment_name>/<batch_id>/
??? experiment_config.yaml
??? batch_manifest.json
??? cases/
    ??? <case_id>/
        ??? case_manifest.json
        ??? strategy_results.json
        ??? performance_metrics.csv
        ??? scoring_results.csv
        ??? inputs/
        ?   ??? simulation_config.yaml
        ?   ??? ran_state_samples.csv
        ??? pipeline/
            ??? run/
                ??? run_manifest.json
                ??? round_000/
                ??? final_recommendation.json
```

Every successful, failed, or skipped case receives a schema-v1.1
`case_manifest.json`. Its normalized provenance contract includes:

- `experimentId`, `caseId`, `runId`, and `experimentType`;
- `codeVersion` and `baseModelVersion`;
- canonical `configurationHash`;
- aggregate `inputHash` and per-file `inputFileHashes`;
- `randomSeed`, `startTime`, `endTime`, and `durationSeconds`;
- `executionStatus`, error details, and relative artifact paths.

The configuration hash is SHA-256 over canonical JSON for the final effective
configuration after path normalization. The input hash is SHA-256 over sorted
relative input paths and their SHA-256 values.

Every row in `performance_metrics.csv` and `scoring_results.csv` embeds the
same stable provenance fields, including the relative `runManifestPath` and
`resultDirectory`. Failed and skipped cases produce one diagnostic row in both
CSV files. This makes each CSV independently traceable without parsing its
directory name.

Schema-v1.0 manifest fields remain present for backward compatibility. The
pipeline directory retains the complete per-round source artifacts.
