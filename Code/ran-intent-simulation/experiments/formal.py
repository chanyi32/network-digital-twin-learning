"""Run the accepted formal-experiments-v1 plan through the frozen pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import stat
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from experiments.config import ExperimentConfig
from experiments.pilot import (
    SUMMARY_COLUMNS,
    _all_finite,
    _configuration_diff,
    _read_json,
    _write_case_outputs,
    _write_json,
)
from experiments.runner import ExperimentRunner


EXTRA_COLUMNS = [
    "feedbackEnabled",
    "clippingMaximumMagnitude",
    "clippingByMetric",
    "paretoNonDominatedCount",
]
FORMAL_COLUMNS = [*SUMMARY_COLUMNS, *EXTRA_COLUMNS]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weights(_Strict):
    service: float = Field(ge=0, le=1)
    energy: float = Field(ge=0, le=1)
    resource: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def sum_is_one(self) -> "Weights":
        if not math.isclose(
            self.service + self.energy + self.resource + self.risk,
            1.0,
            abs_tol=1e-12,
        ):
            raise ValueError("weights must sum to 1")
        return self


class Baseline(_Strict):
    case_id: str
    random_seed: int


class FormalPlan(_Strict):
    schema_version: str
    formal_id: str
    description: str
    output_root: str
    random_seeds: list[int] = Field(min_length=3, max_length=3)
    baseline: Baseline
    load_sweep: dict[str, dict[str, float]]
    feedback_compare: dict[str, bool]
    weight_sensitivity: dict[str, Weights]

    @model_validator(mode="after")
    def exact_design(self) -> "FormalPlan":
        if len(set(self.random_seeds)) != 3:
            raise ValueError("three unique seeds are required")
        count = 1 + 3 * len(self.load_sweep)
        count += 3 * len(self.feedback_compare)
        count += 3 * len(self.weight_sensitivity)
        if count != 31:
            raise ValueError("formal plan must define exactly 31 cases")
        if set(self.feedback_compare.values()) != {False, True}:
            raise ValueError("feedback comparison requires both states")
        return self


def load_formal_plan(path: str | Path) -> FormalPlan:
    with Path(path).open("r", encoding="utf-8") as stream:
        return FormalPlan.model_validate(yaml.safe_load(stream))


def _config(
    name: str, seed: int, root: Path, cases: list[dict[str, Any]]
) -> ExperimentConfig:
    return ExperimentConfig.model_validate(
        {
            "schema_version": "1.1",
            "experiment_name": name,
            "description": f"formal-experiments-v1 {name} seed {seed}",
            "fixed_random_seed": seed,
            "output_root": str(root / name),
            "cases": cases,
        }
    )


def build_configs(
    plan: FormalPlan, formal_root: Path
) -> dict[str, list[tuple[int, ExperimentConfig]]]:
    root = formal_root / "batches"
    output: dict[str, list[tuple[int, ExperimentConfig]]] = defaultdict(list)
    seed = plan.baseline.random_seed
    output["baseline_e2e"].append(
        (
            seed,
            _config(
                "baseline_e2e",
                seed,
                root,
                [
                    {
                        "case_id": plan.baseline.case_id,
                        "description": "Frozen v0.1.1 baseline",
                        "scenario_id": "SCENARIO-HIGH-LOAD",
                    }
                ],
            ),
        )
    )
    for seed in plan.random_seeds:
        output["load_sweep"].append(
            (
                seed,
                _config(
                    "load_sweep",
                    seed,
                    root,
                    [
                        {
                            "case_id": name,
                            "description": f"{name}, seed {seed}",
                            "scenario_id": "SCENARIO-HIGH-LOAD",
                            "simulation_overrides": {
                                "optimization.feedback_enabled": False
                            },
                            "ran_state_overrides": values,
                        }
                        for name, values in plan.load_sweep.items()
                    ],
                ),
            )
        )
        output["feedback_compare"].append(
            (
                seed,
                _config(
                    "feedback_compare",
                    seed,
                    root,
                    [
                        {
                            "case_id": name,
                            "description": f"{name}, seed {seed}",
                            "scenario_id": "SCENARIO-HIGH-LOAD",
                            "simulation_overrides": {
                                "optimization.feedback_enabled": enabled
                            },
                        }
                        for name, enabled in plan.feedback_compare.items()
                    ],
                ),
            )
        )
        output["weight_sensitivity"].append(
            (
                seed,
                _config(
                    "weight_sensitivity",
                    seed,
                    root,
                    [
                        {
                            "case_id": name,
                            "description": f"{name}, seed {seed}",
                            "scenario_id": "SCENARIO-HIGH-LOAD",
                            "simulation_overrides": {
                                "optimization.feedback_enabled": False,
                                "scoring.weights.service": weights.service,
                                "scoring.weights.energy": weights.energy,
                                "scoring.weights.resource": weights.resource,
                                "scoring.weights.risk": weights.risk,
                            },
                        }
                        for name, weights in plan.weight_sensitivity.items()
                    ],
                ),
            )
        )
    return dict(output)


def run_formal(
    plan: FormalPlan,
    *,
    repository_root: Path,
    batch_id: str,
    source_config: Path,
) -> Path:
    root = repository_root / plan.output_root / batch_id
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"formal output exists: {root}")
    root.mkdir(parents=True)
    started = datetime.now(timezone.utc)
    snapshot = root / "config_snapshot" / source_config.name
    snapshot.parent.mkdir()
    shutil.copy2(source_config, snapshot)

    contexts: list[dict[str, Any]] = []
    subbatches: dict[str, list[Path]] = defaultdict(list)
    for experiment_type, items in build_configs(plan, root).items():
        for seed, config in items:
            result = ExperimentRunner(
                config,
                repository_root=repository_root,
                batch_id=f"seed-{seed}",
            ).run(source_config_path=source_config)
            subbatches[experiment_type].append(result.batch_directory)
            for case in config.cases:
                contexts.append(
                    {
                        "type": experiment_type,
                        "seed": seed,
                        "config": config,
                        "case": case,
                        "batch": result.batch_directory,
                        "dir": result.batch_directory
                        / "cases"
                        / case.case_id,
                    }
                )

    summaries = [_summarize(root, context) for context in contexts]
    _csv(root / "all_experiments_summary.csv", summaries)
    for experiment_type, batches in subbatches.items():
        batch_root = root / "batches" / experiment_type
        selected = [
            row for row in summaries if row["experimentType"] == experiment_type
        ]
        _csv(batch_root / "formal_summary.csv", selected)
        _write_json(
            batch_root / "batch_manifest.json",
            {
                "schemaVersion": "1.0",
                "experimentType": experiment_type,
                "caseCount": len(selected),
                "successfulCaseCount": sum(
                    row["executionStatus"] == "succeeded" for row in selected
                ),
                "subbatchManifestPaths": [
                    (batch / "batch_manifest.json").relative_to(root).as_posix()
                    for batch in batches
                ],
                "formalSummaryPath": (
                    f"batches/{experiment_type}/formal_summary.csv"
                ),
            },
        )
        _batch_report(
            batch_root / "formal_experiment_report.md",
            experiment_type,
            selected,
        )

    checks = _validate(root, plan, contexts, summaries)
    reproduction = _repeat(root, repository_root, contexts)
    analysis = _analyse(plan, contexts, summaries)
    ended = datetime.now(timezone.utc)
    manifest = {
        "schemaVersion": "1.0",
        "formalExperimentId": plan.formal_id,
        "batchId": batch_id,
        "startTime": started.isoformat(),
        "endTime": ended.isoformat(),
        "durationSeconds": (ended - started).total_seconds(),
        "caseCount": len(summaries),
        "successfulCaseCount": sum(
            row["executionStatus"] == "succeeded" for row in summaries
        ),
        "codeVersion": sorted({row["codeVersion"] for row in summaries}),
        "baseModelVersion": sorted(
            {row["baseModelVersion"] for row in summaries}
        ),
        "configurationSnapshotPath": snapshot.relative_to(root).as_posix(),
        "configurationSnapshotSha256": _sha(snapshot),
        "validations": checks,
        "reproducibility": reproduction,
        "analysis": analysis,
    }
    _write_json(root / "batch_manifest.json", manifest)
    _acceptance_report(
        root / "formal_experiment_acceptance_report.md",
        summaries,
        checks,
        reproduction,
        analysis,
        manifest,
    )
    try:
        os.chmod(snapshot, stat.S_IREAD)
    except OSError:
        pass
    return root


def _summarize(root: Path, context: dict[str, Any]) -> dict[str, Any]:
    case_dir = context["dir"]
    manifest = _read_json(case_dir / "case_manifest.json")
    if manifest["executionStatus"] != "succeeded":
        row = {column: None for column in FORMAL_COLUMNS}
        for field in (
            "experimentId",
            "caseId",
            "runId",
            "experimentType",
            "executionStatus",
            "codeVersion",
            "baseModelVersion",
            "configurationHash",
            "inputHash",
            "randomSeed",
            "durationSeconds",
            "feedbackEnabled",
        ):
            row[field] = manifest[field]
        _write_json(case_dir / "case_summary.json", row)
        return row
    row = _write_case_outputs(root, context["batch"], case_dir)
    row["feedbackEnabled"] = manifest["feedbackEnabled"]
    clipping: dict[str, dict[str, float]] = {}
    run_dir = root / row["resultDirectory"]
    for path in run_dir.glob("round_*/performance_results.json"):
        for result in _read_json(path):
            for metric, item in result["clippingSummary"].items():
                target = clipping.setdefault(
                    metric, {"count": 0, "maximumMagnitude": 0.0}
                )
                target["count"] += int(item["clippedCount"])
                target["maximumMagnitude"] = max(
                    target["maximumMagnitude"],
                    float(item["maximumClippingMagnitude"]),
                )
    row["clippingByMetric"] = clipping
    row["clippingMaximumMagnitude"] = max(
        (value["maximumMagnitude"] for value in clipping.values()), default=0.0
    )
    row["paretoNonDominatedCount"] = _pareto(run_dir)
    _write_json(case_dir / "case_summary.json", row)
    return row


def _pareto(run_dir: Path) -> int:
    values: list[tuple[float, ...]] = []
    for path in run_dir.glob("round_*/ranked_policies.json"):
        for score in _read_json(path):
            if score["feasible"]:
                values.append(
                    tuple(
                        float(score[name])
                        for name in (
                            "serviceScore",
                            "energyScore",
                            "resourceScore",
                            "riskScore",
                        )
                    )
                )
    return sum(
        not any(
            all(other[i] >= value[i] for i in range(4))
            and any(other[i] > value[i] for i in range(4))
            for j, other in enumerate(values)
            if j != index
        )
        for index, value in enumerate(values)
    )


def _validate(
    root: Path,
    plan: FormalPlan,
    contexts: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: dict[str, list[str]] = defaultdict(list)
    for context in contexts:
        case_dir = context["dir"]
        key = f"{context['type']}/{context['case'].case_id}/{context['seed']}"
        for name in (
            "case_manifest.json",
            "effective_experiment_config.json",
            "case_summary.json",
        ):
            if not (case_dir / name).is_file():
                errors["files"].append(f"{key}:{name}")
        manifest = _read_json(case_dir / "case_manifest.json")
        if manifest["executionStatus"] != "succeeded":
            errors["status"].append(key)
            continue
        run_manifest_path = context["batch"] / manifest["runManifestPath"]
        if not run_manifest_path.is_file():
            errors["paths"].append(key)
            continue
        run_manifest = _read_json(run_manifest_path)
        rounds = sorted(run_manifest_path.parent.glob("round_*"))
        prior: set[str] = set()
        for round_dir in rounds:
            required = {
                "candidate_policies.json",
                "performance_results.json",
                "constraint_checks.csv",
                "policy_scores.csv",
                "ranked_policies.json",
                "round_summary.json",
            }
            if manifest["feedbackEnabled"]:
                required.add("feedback.json")
            for name in required:
                if not (round_dir / name).is_file():
                    errors["files"].append(f"{key}:{round_dir.name}:{name}")
            policies = _read_json(round_dir / "candidate_policies.json")
            for policy in policies:
                if policy["generationRound"] > 0 and (
                    policy["parentPolicyId"] not in prior
                    or not policy["generationReason"].startswith("feedback:")
                ):
                    errors["chain"].append(policy["policyId"])
            prior.update(policy["policyId"] for policy in policies)
            for score in _read_json(round_dir / "ranked_policies.json"):
                if not score["feasible"] and (
                    score["totalScore"] != 0 or score["rank"] is not None
                ):
                    errors["constraint"].append(score["policyId"])
                for field in (
                    "serviceScore",
                    "energyScore",
                    "resourceScore",
                    "riskScore",
                    "totalScore",
                ):
                    if not 0 <= float(score[field]) <= 1:
                        errors["range"].append(f"{score['policyId']}:{field}")
            for path in round_dir.glob("*.json"):
                if not _all_finite(_read_json(path)):
                    errors["finite"].append(str(path))
        if not manifest["feedbackEnabled"] and not (
            len(rounds) == 1
            and run_manifest["feedbackIterations"] == 0
            and run_manifest["generationRounds"] == 1
            and run_manifest["terminationReason"] == "feedback_disabled"
            and not (rounds[0] / "feedback.json").exists()
        ):
            errors["feedbackOff"].append(key)
        if (
            run_manifest["randomSeed"] != manifest["randomSeed"]
            or not manifest["configurationHash"]
            or not manifest["inputHash"]
        ):
            errors["provenance"].append(key)
    _paired_checks(plan, contexts, errors)
    frame = pd.read_csv(root / "all_experiments_summary.csv")
    if len(frame) != len(summaries):
        errors["summary"].append("row count")
    return {
        "expectedCaseCount": 31,
        "actualCaseCount": len(summaries),
        "successfulCaseCount": sum(
            row["executionStatus"] == "succeeded" for row in summaries
        ),
        "allCasesSucceeded": not errors["status"],
        "fileCompleteness": not errors["files"],
        "pathsTraceable": not errors["paths"],
        "summaryMatchesSourceJson": not errors["summary"],
        "allResultsFinite": not errors["finite"],
        "rangesValid": not errors["range"],
        "infeasibleScoreRuleValid": not errors["constraint"],
        "feedbackDisabledSemanticsValid": not errors["feedbackOff"],
        "pairedConfigurationsValid": not errors["pairs"],
        "parentChainsValid": not errors["chain"],
        "provenanceValid": not errors["provenance"],
        "errors": {key: value for key, value in errors.items() if value},
    }


def _paired_checks(
    plan: FormalPlan,
    contexts: list[dict[str, Any]],
    errors: dict[str, list[str]],
) -> None:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for context in contexts:
        groups[(context["type"], context["seed"])].append(context)
    for seed in plan.random_seeds:
        feedback = groups[("feedback_compare", seed)]
        if _configuration_diff(_effective(feedback[0]), _effective(feedback[1])) != [
            "optimization.feedback_enabled"
        ]:
            errors["pairs"].append(f"feedback config {seed}")
        if _round(feedback[0], "candidate_policies.json") != _round(
            feedback[1], "candidate_policies.json"
        ):
            errors["pairs"].append(f"feedback candidates {seed}")
        weights = groups[("weight_sensitivity", seed)]
        for other in weights[1:]:
            diff = _configuration_diff(_effective(weights[0]), _effective(other))
            if not diff or any(
                not field.startswith("scoring.weights.") for field in diff
            ):
                errors["pairs"].append(f"weights config {seed}")
            if _round(weights[0], "candidate_policies.json") != _round(
                other, "candidate_policies.json"
            ) or _round(weights[0], "performance_results.json") != _round(
                other, "performance_results.json"
            ):
                errors["pairs"].append(f"weights artifacts {seed}")
        loads = groups[("load_sweep", seed)]
        if any(
            _configuration_diff(_effective(loads[0]), _effective(item))
            for item in loads[1:]
        ):
            errors["pairs"].append(f"load config {seed}")


def _repeat(
    root: Path, repository: Path, contexts: list[dict[str, Any]]
) -> dict[str, Any]:
    selected = random.Random(20260731).choice(contexts)
    config = selected["config"].model_copy(
        update={"cases": [selected["case"]]}, deep=True
    )
    result = ExperimentRunner(
        config,
        repository_root=repository,
        batch_id="repeat",
        output_root=root / "reproducibility",
    ).run()
    original = selected["dir"] / "pipeline" / "run"
    repeated = (
        result.batch_directory
        / "cases"
        / selected["case"].case_id
        / "pipeline"
        / "run"
    )
    files = [
        path.relative_to(original)
        for path in original.rglob("*")
        if path.is_file()
        and path.name != "run_manifest.json"
        and (
            path.parent.name.startswith("round_")
            or path.name
            in {"final_recommendation.json", "no_feasible_policy.json"}
        )
    ]
    mismatches = [
        path.as_posix()
        for path in files
        if not (repeated / path).is_file()
        or _sha(original / path) != _sha(repeated / path)
    ]
    return {
        "experimentType": selected["type"],
        "caseId": selected["case"].case_id,
        "randomSeed": selected["seed"],
        "comparedArtifactCount": len(files),
        "mismatchCount": len(mismatches),
        "mismatches": mismatches,
        "reproducible": not mismatches,
    }


def _analyse(
    plan: FormalPlan,
    contexts: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    index = {
        (row["experimentType"], row["caseId"], row["randomSeed"]): row
        for row in rows
    }
    loads = {}
    for name in plan.load_sweep:
        selected = [index[("load_sweep", name, seed)] for seed in plan.random_seeds]
        loads[name] = {
            field: sum(float(row[field]) for row in selected) / 3
            for field in (
                "feasibleRatio",
                "bestTotalScore",
                "videoThroughputP05Mbps",
                "videoDelayP95Ms",
                "prbUtilization",
            )
        }
        loads[name]["bestPolicyIds"] = sorted(
            {row["bestPolicyId"] for row in selected}
        )
    feedback = []
    for seed in plan.random_seeds:
        off = index[("feedback_compare", "feedback_disabled", seed)]
        on = index[("feedback_compare", "feedback_enabled", seed)]
        feedback.append(
            {
                "randomSeed": seed,
                "bestScoreDelta": on["bestTotalScore"] - off["bestTotalScore"],
                "feasibleCountDelta": on["feasiblePolicyCount"]
                - off["feasiblePolicyCount"],
                "evaluatedCountDelta": on["evaluatedPolicyCount"]
                - off["evaluatedPolicyCount"],
            }
        )
    weights = {}
    for seed in plan.random_seeds:
        seed_rows = [
            index[("weight_sensitivity", name, seed)]
            for name in plan.weight_sensitivity
        ]
        weights[str(seed)] = {
            "bestPolicyByWeights": {
                row["caseId"]: row["bestPolicyId"] for row in seed_rows
            },
            "uniqueBestPolicyCount": len(
                {row["bestPolicyId"] for row in seed_rows}
            ),
        }
    clipping: dict[str, dict[str, float]] = {}
    for row in rows:
        for metric, item in row.get("clippingByMetric", {}).items():
            target = clipping.setdefault(
                metric, {"count": 0, "maximumMagnitude": 0.0}
            )
            target["count"] += item["count"]
            target["maximumMagnitude"] = max(
                target["maximumMagnitude"], item["maximumMagnitude"]
            )
    return {
        "loadSweep": loads,
        "feedbackCompare": feedback,
        "weightSensitivity": weights,
        "clippingByMetric": clipping,
        "paretoCounts": {
            f"{row['experimentType']}/{row['caseId']}/{row['randomSeed']}": row[
                "paretoNonDominatedCount"
            ]
            for row in rows
        },
    }


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = []
    for row in rows:
        item = {column: row.get(column) for column in FORMAL_COLUMNS}
        item["clippingByMetric"] = json.dumps(
            item["clippingByMetric"], ensure_ascii=False, sort_keys=True
        )
        output.append(item)
    pd.DataFrame(output, columns=FORMAL_COLUMNS).to_csv(path, index=False)


def _batch_report(path: Path, name: str, rows: list[dict[str, Any]]) -> None:
    table = "\n".join(
        f"| {row['caseId']} | {row['randomSeed']} | "
        f"{row['executionStatus']} | {row['feasibleRatio']:.4f} | "
        f"{row['bestTotalScore']:.6f} | {row['clippingCount']} |"
        for row in rows
    )
    path.write_text(
        f"""# {name} ??????

| Case | Seed | ?? | ??? | ??? | ?? |
|---|---:|---|---:|---:|---:|
{table}

??????????? pipeline???????????????
""",
        encoding="utf-8",
    )


def _acceptance_report(
    path: Path,
    rows: list[dict[str, Any]],
    checks: dict[str, Any],
    reproduction: dict[str, Any],
    analysis: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    passed = (
        checks["actualCaseCount"] == 31
        and checks["successfulCaseCount"] == 31
        and not checks["errors"]
        and reproduction["reproducible"]
    )
    check_rows = "\n".join(
        f"| `{key}` | `{value}` |"
        for key, value in checks.items()
        if key != "errors"
    )
    case_rows = "\n".join(
        f"| {row['experimentType']} | {row['caseId']} | "
        f"{row['randomSeed']} | {row['executionStatus']} | "
        f"{row['feasibleRatio']:.4f} | {row['bestTotalScore']:.6f} | "
        f"{row['bestPolicyId']} | {row['paretoNonDominatedCount']} |"
        for row in rows
    )
    path.write_text(
        f"""# ??????????

## ??

**{'??' if passed else '???'}**?31?case??
`{checks['successfulCaseCount']}` ?????
`{manifest['durationSeconds']:.3f}` ??

## ????

| ?? | ?? |
|---|---|
{check_rows}

???? `{reproduction['experimentType']}/{reproduction['caseId']}`?
?? `{reproduction['comparedArtifactCount']}` ?????????
??? `{reproduction['mismatchCount']}` ??

## Case??

| ?? | Case | Seed | ?? | ??? | ??? | ?? | Pareto? |
|---|---|---:|---|---:|---:|---|---:|
{case_rows}

## ????

?????`{json.dumps(analysis['loadSweep'], ensure_ascii=False)}`?

?????`{json.dumps(analysis['feedbackCompare'], ensure_ascii=False)}`?

??????`{json.dumps(analysis['weightSensitivity'], ensure_ascii=False)}`?

???`{json.dumps(analysis['clippingByMetric'], ensure_ascii=False)}`?

???????????????????????????????
`simplified-ran-v1` ????????????????????RAN?
""",
        encoding="utf-8",
    )


def _effective(context: dict[str, Any]) -> dict[str, Any]:
    return _read_json(
        context["dir"] / "effective_experiment_config.json"
    )["simulationConfig"]


def _round(context: dict[str, Any], name: str) -> bytes:
    return (
        context["dir"] / "pipeline" / "run" / "round_000" / name
    ).read_bytes()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent
        / "configs"
        / "formal_experiments_v1.yaml",
    )
    parser.add_argument("--batch-id", required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    output = run_formal(
        load_formal_plan(args.config),
        repository_root=root,
        batch_id=args.batch_id,
        source_config=args.config.resolve(),
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
