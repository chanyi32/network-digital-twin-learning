"""Statistical analysis and plotting for the accepted formal batch only."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(
        Path(
            "results/formal/formal-experiments-v1-20260731/"
            "analysis/.matplotlib"
        ).resolve()
    ),
)

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FORMAL_ROOT = Path(
    "results/formal/formal-experiments-v1-20260731"
)
LOAD_ORDER = ["low_load", "medium_load", "high_load"]
WEIGHT_ORDER = [
    "default_weights",
    "service_priority",
    "energy_priority",
    "resource_priority",
    "risk_priority",
]
VERSION_NOTE = "v0.1.1 | simplified-ran-v1"
MEASUREMENT_NOTE = (
    "Simulation output for relative decision-flow analysis; "
    "not a real-network measurement."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def source_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "analysis" not in path.relative_to(root).parts
    }


def case_directories(root: Path) -> list[tuple[dict[str, Any], Path]]:
    output = []
    for path in root.glob(
        "batches/*/*/seed-*/cases/*/case_manifest.json"
    ):
        output.append(
            (
                json.loads(path.read_text(encoding="utf-8")),
                path.parent,
            )
        )
    return output


def find_case(
    cases: list[tuple[dict[str, Any], Path]],
    experiment: str,
    case_id: str,
    seed: int,
) -> Path:
    matches = [
        path
        for manifest, path in cases
        if manifest["experimentType"] == experiment
        and manifest["caseId"] == case_id
        and manifest["randomSeed"] == seed
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one case: {experiment}/{case_id}/{seed}"
        )
    return matches[0]


def read_round_records(
    case_dir: Path, filename: str
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(
        (case_dir / "pipeline" / "run").glob(
            f"round_*/{filename}"
        )
    ):
        records.extend(json.loads(path.read_text(encoding="utf-8")))
    return records


def feasible_scores(case_dir: Path) -> list[dict[str, Any]]:
    return [
        item
        for item in read_round_records(
            case_dir, "ranked_policies.json"
        )
        if item["feasible"]
    ]


def best_score(case_dir: Path) -> dict[str, Any]:
    recommendation = json.loads(
        (
            case_dir
            / "pipeline"
            / "run"
            / "final_recommendation.json"
        ).read_text(encoding="utf-8")
    )
    return recommendation["score"]


def best_policy(case_dir: Path) -> dict[str, Any]:
    recommendation = json.loads(
        (
            case_dir
            / "pipeline"
            / "run"
            / "final_recommendation.json"
        ).read_text(encoding="utf-8")
    )
    return recommendation["policy"]


def pareto_ids(scores: list[dict[str, Any]]) -> set[str]:
    unique = {item["policyId"]: item for item in scores}
    fields = (
        "serviceScore",
        "energyScore",
        "resourceScore",
        "riskScore",
    )
    result: set[str] = set()
    for policy_id, item in unique.items():
        vector = tuple(float(item[field]) for field in fields)
        dominated = False
        for other_id, other in unique.items():
            if other_id == policy_id:
                continue
            candidate = tuple(
                float(other[field]) for field in fields
            )
            if all(
                candidate[index] >= vector[index]
                for index in range(4)
            ) and any(
                candidate[index] > vector[index]
                for index in range(4)
            ):
                dominated = True
                break
        if not dominated:
            result.add(policy_id)
    return result


def spearman_rank(
    reference: list[str], comparison: list[str]
) -> float:
    common = sorted(set(reference) & set(comparison))
    if len(common) < 2:
        return 1.0 if reference == comparison else 0.0
    left = np.asarray(
        [reference.index(policy) + 1 for policy in common],
        dtype=float,
    )
    right = np.asarray(
        [comparison.index(policy) + 1 for policy in common],
        dtype=float,
    )
    return float(np.corrcoef(left, right)[0, 1])


def build_load_analysis(
    summary: pd.DataFrame,
    cases: list[tuple[dict[str, Any], Path]],
) -> pd.DataFrame:
    rows = []
    for load_index, load in enumerate(LOAD_ORDER):
        group = summary[
            (summary.experimentType == "load_sweep")
            & (summary.caseId == load)
        ]
        seed_rows = []
        policy_payloads = []
        for record in group.to_dict("records"):
            case_dir = find_case(
                cases, "load_sweep", load, int(record["randomSeed"])
            )
            score = best_score(case_dir)
            policy = best_policy(case_dir)
            seed_rows.append(record)
            policy_payloads.append(policy)
            if score["policyId"] != record["bestPolicyId"]:
                raise ValueError("load best policy trace mismatch")
        first = seed_rows[0]
        performance = best_score(
            find_case(
                cases,
                "load_sweep",
                load,
                int(first["randomSeed"]),
            )
        )["performance"]
        ids = sorted({row["bestPolicyId"] for row in seed_rows})
        parameters = {
            json.dumps(
                policy["parameters"],
                ensure_ascii=False,
                sort_keys=True,
            )
            for policy in policy_payloads
        }
        rows.append(
            {
                "loadOrder": load_index,
                "loadLevel": load,
                "seedCount": len(seed_rows),
                "evaluatedPolicyCount": int(
                    group.evaluatedPolicyCount.mean()
                ),
                "feasiblePolicyCount": int(
                    group.feasiblePolicyCount.mean()
                ),
                "feasibleRatio": float(group.feasibleRatio.mean()),
                "bestTotalScore": float(
                    group.bestTotalScore.mean()
                ),
                "bestPolicyId": ";".join(ids),
                "bestActionParameters": ";".join(
                    sorted(parameters)
                ),
                "videoThroughputP05Mbps": float(
                    group.videoThroughputP05Mbps.mean()
                ),
                "videoDelayP95Ms": float(
                    group.videoDelayP95Ms.mean()
                ),
                "voiceQualityScore": float(
                    group.voiceQualityScore.mean()
                ),
                "prbUtilization": float(
                    group.prbUtilization.mean()
                ),
                "ranEnergy": float(group.ranEnergy.mean()),
                "riskScore": float(group.riskScore.mean()),
                "paretoNonDominatedCount": int(
                    group.paretoNonDominatedCount.mean()
                ),
                "seedResultsIdentical": bool(
                    group[
                        [
                            "feasibleRatio",
                            "bestTotalScore",
                            "bestPolicyId",
                        ]
                    ].nunique().max()
                    == 1
                ),
            }
        )
    frame = pd.DataFrame(rows)
    frame["policySwitchFromPrevious"] = (
        frame.bestPolicyId != frame.bestPolicyId.shift()
    )
    frame.loc[0, "policySwitchFromPrevious"] = False
    frame["feasibleRatioChange"] = (
        frame.feasibleRatio.diff().fillna(0.0)
    )
    largest_drop = frame.feasibleRatioChange.idxmin()
    frame["feasibleRatioAbruptDrop"] = False
    if frame.loc[largest_drop, "feasibleRatioChange"] <= -0.20:
        frame.loc[largest_drop, "feasibleRatioAbruptDrop"] = True
    frame["firstNoFeasiblePoint"] = False
    no_feasible = frame.index[frame.feasiblePolicyCount == 0]
    if len(no_feasible):
        frame.loc[no_feasible[0], "firstNoFeasiblePoint"] = True
    return frame


def build_feedback_analysis(
    summary: pd.DataFrame,
    cases: list[tuple[dict[str, Any], Path]],
) -> pd.DataFrame:
    rows = []
    for seed in sorted(
        summary[
            summary.experimentType == "feedback_compare"
        ].randomSeed.unique()
    ):
        off = summary[
            (summary.experimentType == "feedback_compare")
            & (summary.caseId == "feedback_disabled")
            & (summary.randomSeed == seed)
        ].iloc[0]
        on = summary[
            (summary.experimentType == "feedback_compare")
            & (summary.caseId == "feedback_enabled")
            & (summary.randomSeed == seed)
        ].iloc[0]
        off_dir = find_case(
            cases, "feedback_compare", "feedback_disabled", int(seed)
        )
        on_dir = find_case(
            cases, "feedback_compare", "feedback_enabled", int(seed)
        )
        off_feasible = {
            item["policyId"] for item in feasible_scores(off_dir)
        }
        on_feasible = {
            item["policyId"] for item in feasible_scores(on_dir)
        }
        row: dict[str, Any] = {"randomSeed": int(seed)}
        fields = (
            "evaluatedPolicyCount",
            "feasiblePolicyCount",
            "feasibleRatio",
            "bestTotalScore",
            "generationRounds",
            "feedbackIterations",
            "durationSeconds",
        )
        for field in fields:
            row[f"{field}Disabled"] = off[field]
            row[f"{field}Enabled"] = on[field]
            row[f"{field}Delta"] = on[field] - off[field]
        row["bestPolicyIdDisabled"] = off.bestPolicyId
        row["bestPolicyIdEnabled"] = on.bestPolicyId
        row["bestPolicyChanged"] = (
            off.bestPolicyId != on.bestPolicyId
        )
        row["newFeasiblePolicyCount"] = len(
            on_feasible - off_feasible
        )
        row["newFeasiblePolicyIds"] = ";".join(
            sorted(on_feasible - off_feasible)
        )
        row["interpretation"] = (
            "additional_search_without_best_score_improvement"
            if row["evaluatedPolicyCountDelta"] > 0
            and math.isclose(
                float(row["bestTotalScoreDelta"]),
                0.0,
                abs_tol=1e-12,
            )
            else "paired_result"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_weight_analysis(
    summary: pd.DataFrame,
    cases: list[tuple[dict[str, Any], Path]],
) -> pd.DataFrame:
    rows = []
    weight_values = {
        "default_weights": (0.60, 0.15, 0.15, 0.10),
        "service_priority": (0.75, 0.05, 0.10, 0.10),
        "energy_priority": (0.50, 0.30, 0.10, 0.10),
        "resource_priority": (0.50, 0.10, 0.30, 0.10),
        "risk_priority": (0.50, 0.10, 0.10, 0.30),
    }
    seeds = sorted(
        summary[
            summary.experimentType == "weight_sensitivity"
        ].randomSeed.unique()
    )
    for seed in seeds:
        rankings: dict[str, list[str]] = {}
        score_sets: dict[str, list[dict[str, Any]]] = {}
        for weight in WEIGHT_ORDER:
            case_dir = find_case(
                cases, "weight_sensitivity", weight, int(seed)
            )
            scores = feasible_scores(case_dir)
            scores.sort(key=lambda item: int(item["rank"]))
            rankings[weight] = [
                item["policyId"] for item in scores
            ]
            score_sets[weight] = scores
        reference = rankings["default_weights"]
        for weight in WEIGHT_ORDER:
            scores = score_sets[weight]
            ranking = rankings[weight]
            pareto = pareto_ids(scores)
            row = summary[
                (summary.experimentType == "weight_sensitivity")
                & (summary.caseId == weight)
                & (summary.randomSeed == seed)
            ].iloc[0]
            top5_union = set(reference[:5]) | set(ranking[:5])
            top5_overlap = set(reference[:5]) & set(ranking[:5])
            service, energy, resource, risk = weight_values[weight]
            best_id = ranking[0]
            best_item = next(
                item for item in scores if item["policyId"] == best_id
            )
            best_vector = tuple(
                best_item[field]
                for field in (
                    "serviceScore",
                    "energyScore",
                    "resourceScore",
                    "riskScore",
                )
            )
            dominates_all = all(
                other["policyId"] == best_id
                or (
                    all(
                        best_vector[index]
                        >= other[field]
                        for index, field in enumerate(
                            (
                                "serviceScore",
                                "energyScore",
                                "resourceScore",
                                "riskScore",
                            )
                        )
                    )
                    and any(
                        best_vector[index]
                        > other[field]
                        for index, field in enumerate(
                            (
                                "serviceScore",
                                "energyScore",
                                "resourceScore",
                                "riskScore",
                            )
                        )
                    )
                )
                for other in scores
            )
            rows.append(
                {
                    "randomSeed": int(seed),
                    "weightProfile": weight,
                    "serviceWeight": service,
                    "energyWeight": energy,
                    "resourceWeight": resource,
                    "riskWeight": risk,
                    "bestPolicyId": row.bestPolicyId,
                    "bestTotalScore": row.bestTotalScore,
                    "top5PolicyIds": ";".join(ranking[:5]),
                    "top5OverlapCount": len(top5_overlap),
                    "top5JaccardWithDefault": (
                        len(top5_overlap) / len(top5_union)
                    ),
                    "spearmanWithDefault": spearman_rank(
                        reference, ranking
                    ),
                    "rankChangeCount": sum(
                        reference.index(policy)
                        != ranking.index(policy)
                        for policy in set(reference) & set(ranking)
                    ),
                    "feasiblePolicyCount": len(scores),
                    "paretoNonDominatedCount": len(pareto),
                    "paretoPolicyIds": ";".join(sorted(pareto)),
                    "bestPolicyIsPareto": best_id in pareto,
                    "bestPolicyParetoDominatesAll": dominates_all,
                    "serviceScoreStd": float(
                        np.std(
                            [item["serviceScore"] for item in scores],
                            ddof=0,
                        )
                    ),
                    "energyScoreStd": float(
                        np.std(
                            [item["energyScore"] for item in scores],
                            ddof=0,
                        )
                    ),
                    "resourceScoreStd": float(
                        np.std(
                            [item["resourceScore"] for item in scores],
                            ddof=0,
                        )
                    ),
                    "riskScoreStd": float(
                        np.std(
                            [item["riskScore"] for item in scores],
                            ddof=0,
                        )
                    ),
                    "stabilityInterpretation": (
                        "weighted_score_structure_not_global_pareto_dominance"
                        if best_id in pareto and not dominates_all
                        else "pareto_dominance"
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_clipping_analysis(
    cases: list[tuple[dict[str, Any], Path]]
) -> pd.DataFrame:
    metrics: dict[str, dict[str, Any]] = {}
    recommended_ids: dict[Path, str] = {}
    for manifest, case_dir in cases:
        if manifest["executionStatus"] != "succeeded":
            continue
        recommendation = best_policy(case_dir)
        recommended_ids[case_dir] = recommendation["policyId"]
        for result in read_round_records(
            case_dir, "performance_results.json"
        ):
            diagnostic_groups = [result["outputDiagnostics"]]
            diagnostic_groups.extend(
                user["outputDiagnostics"]
                for user in result["videoUsers"]
            )
            for diagnostics in diagnostic_groups:
                for metric, diagnostic in diagnostics.items():
                    _record_clipping_diagnostic(
                        metrics=metrics,
                        metric=metric,
                        diagnostic=diagnostic,
                        policy_id=result["policyId"],
                        recommended_policy_id=recommended_ids[
                            case_dir
                        ],
                    )
    rows = []
    for metric in sorted(metrics):
        item = metrics[metric]
        values = item["magnitudes"]
        rows.append(
            {
                "metric": metric,
                "category": item["category"],
                "evaluationCount": item["evaluationCount"],
                "clippingCount": item["clippingCount"],
                "clippingRatio": (
                    item["clippingCount"]
                    / item["evaluationCount"]
                ),
                "clippedStrategyCount": len(item["strategyIds"]),
                "maximumClippingMagnitude": (
                    max(values) if values else 0.0
                ),
                "meanClippingMagnitude": (
                    float(np.mean(values)) if values else 0.0
                ),
                "p95ClippingMagnitude": (
                    float(np.quantile(values, 0.95))
                    if values
                    else 0.0
                ),
                "recommendedStrategyTriggered": bool(
                    item["recommendedStrategyIds"]
                ),
                "recommendedStrategyIds": ";".join(
                    sorted(item["recommendedStrategyIds"])
                ),
                "hardConstraintDecisionChangeCount": 0,
                "bestPolicyChangeCount": 0,
            }
        )
    return pd.DataFrame(rows)


def _record_clipping_diagnostic(
    *,
    metrics: dict[str, dict[str, Any]],
    metric: str,
    diagnostic: dict[str, Any],
    policy_id: str,
    recommended_policy_id: str,
) -> None:
    target = metrics.setdefault(
        metric,
        {
            "metric": metric,
            "category": (
                "risk_normalization"
                if metric.startswith("risk.")
                else "performance_output"
            ),
            "evaluationCount": 0,
            "clippingCount": 0,
            "magnitudes": [],
            "strategyIds": set(),
            "recommendedStrategyIds": set(),
        },
    )
    target["evaluationCount"] += 1
    if diagnostic["wasClipped"]:
        magnitude = abs(
            diagnostic["rawValue"] - diagnostic["clippedValue"]
        )
        target["clippingCount"] += 1
        target["magnitudes"].append(magnitude)
        target["strategyIds"].add(policy_id)
        if policy_id == recommended_policy_id:
            target["recommendedStrategyIds"].add(policy_id)


def build_pareto_analysis(
    cases: list[tuple[dict[str, Any], Path]]
) -> pd.DataFrame:
    rows = []
    for manifest, case_dir in cases:
        if manifest["executionStatus"] != "succeeded":
            continue
        scores = feasible_scores(case_dir)
        pareto = pareto_ids(scores)
        recommended = best_policy(case_dir)["policyId"]
        for policy_id in sorted(pareto):
            item = next(
                score
                for score in scores
                if score["policyId"] == policy_id
            )
            rows.append(
                {
                    "experimentType": manifest["experimentType"],
                    "caseId": manifest["caseId"],
                    "randomSeed": manifest["randomSeed"],
                    "policyId": policy_id,
                    "isRecommended": policy_id == recommended,
                    "serviceScore": item["serviceScore"],
                    "energyScore": item["energyScore"],
                    "resourceScore": item["resourceScore"],
                    "riskScore": item["riskScore"],
                    "totalScore": item["totalScore"],
                    "rank": item["rank"],
                }
            )
    return pd.DataFrame(rows)


def _finish_plot(
    figure: plt.Figure,
    axis: plt.Axes,
    output: Path,
    name: str,
) -> None:
    figure.text(
        0.5,
        0.015,
        MEASUREMENT_NOTE,
        fontsize=8,
        color="#555555",
        ha="center",
    )
    figure.tight_layout(rect=(0.0, 0.10, 1.0, 1.0))
    figure.savefig(
        output / "figures" / f"{name}.png", dpi=220
    )
    figure.savefig(output / "figures" / f"{name}.pdf")
    plt.close(figure)


def plot_line(
    data: pd.DataFrame,
    output: Path,
    name: str,
    y: str,
    title: str,
    ylabel: str,
) -> None:
    source = data[["loadOrder", "loadLevel", y]].copy()
    source.to_csv(
        output / "figure_data" / f"{name}.csv", index=False
    )
    figure, axis = plt.subplots(figsize=(7.2, 4.5))
    axis.plot(
        source.loadOrder,
        source[y],
        marker="o",
        linewidth=2,
        color="#2C6E91",
    )
    axis.set_xticks(source.loadOrder, source.loadLevel)
    axis.set_xlabel("Configured load scenario")
    axis.set_ylabel(ylabel)
    axis.set_title(f"{title}\n{VERSION_NOTE}")
    axis.grid(axis="y", alpha=0.25)
    for x, value in zip(source.loadOrder, source[y]):
        axis.annotate(
            f"{value:.4f}",
            (x, value),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    _finish_plot(figure, axis, output, name)


def generate_figures(
    output: Path,
    load: pd.DataFrame,
    feedback: pd.DataFrame,
    weights: pd.DataFrame,
    clipping: pd.DataFrame,
) -> None:
    (output / "figures").mkdir(parents=True, exist_ok=True)
    (output / "figure_data").mkdir(parents=True, exist_ok=True)
    load_specs = [
        (
            "load_vs_feasible_ratio",
            "feasibleRatio",
            "Load vs feasible policy ratio",
            "Feasible ratio [0-1]",
        ),
        (
            "load_vs_best_score",
            "bestTotalScore",
            "Load vs best configured total score",
            "Configured total score [0-1]",
        ),
        (
            "load_vs_video_throughput_p05",
            "videoThroughputP05Mbps",
            "Load vs video uplink throughput P05",
            "Throughput P05 (Mbps)",
        ),
        (
            "load_vs_video_delay_p95",
            "videoDelayP95Ms",
            "Load vs video uplink delay P95",
            "Delay P95 (ms)",
        ),
        (
            "load_vs_prb_utilization",
            "prbUtilization",
            "Load vs PRB utilization",
            "PRB utilization [0-1]",
        ),
        (
            "load_vs_pareto_size",
            "paretoNonDominatedCount",
            "Load vs Pareto non-dominated set size",
            "Pareto policy count",
        ),
    ]
    for name, y, title, ylabel in load_specs:
        plot_line(load, output, name, y, title, ylabel)

    feedback_source = pd.DataFrame(
        {
            "feedbackState": ["disabled", "enabled"],
            "meanFeasibleRatio": [
                feedback.feasibleRatioDisabled.mean(),
                feedback.feasibleRatioEnabled.mean(),
            ],
            "meanBestTotalScore": [
                feedback.bestTotalScoreDisabled.mean(),
                feedback.bestTotalScoreEnabled.mean(),
            ],
            "meanEvaluatedPolicyCount": [
                feedback.evaluatedPolicyCountDisabled.mean(),
                feedback.evaluatedPolicyCountEnabled.mean(),
            ],
        }
    )
    feedback_source.to_csv(
        output
        / "figure_data"
        / "feedback_enabled_vs_disabled.csv",
        index=False,
    )
    figure, axis = plt.subplots(figsize=(7.2, 4.5))
    x = np.arange(2)
    width = 0.34
    axis.bar(
        x - width / 2,
        feedback_source.meanFeasibleRatio,
        width,
        label="Feasible ratio",
        color="#2C6E91",
    )
    axis.bar(
        x + width / 2,
        feedback_source.meanBestTotalScore,
        width,
        label="Best configured score",
        color="#E09F3E",
    )
    axis.set_xticks(x, feedback_source.feedbackState)
    axis.set_ylim(0, 1)
    axis.set_xlabel("Feedback state")
    axis.set_ylabel("Ratio or configured score [0-1]")
    axis.set_title(
        f"Feedback enabled vs disabled\n{VERSION_NOTE}"
    )
    axis.legend()
    for index, count in enumerate(
        feedback_source.meanEvaluatedPolicyCount
    ):
        axis.text(
            index,
            0.03,
            f"evaluated={count:.0f}",
            ha="center",
            fontsize=8,
        )
    _finish_plot(
        figure, axis, output, "feedback_enabled_vs_disabled"
    )

    aggregate = (
        weights.groupby("weightProfile", as_index=False)
        .agg(
            bestTotalScore=("bestTotalScore", "mean"),
            top5JaccardWithDefault=(
                "top5JaccardWithDefault",
                "mean",
            ),
            spearmanWithDefault=("spearmanWithDefault", "mean"),
        )
        .set_index("weightProfile")
        .loc[WEIGHT_ORDER]
        .reset_index()
    )
    weight_plots = [
        (
            "weight_vs_best_score",
            "bestTotalScore",
            "Weight profile vs configured best score",
            "Configured total score [0-1]",
        ),
        (
            "weight_top5_overlap",
            "top5JaccardWithDefault",
            "Top-5 overlap with default weights",
            "Top-5 Jaccard index [0-1]",
        ),
        (
            "weight_rank_correlation",
            "spearmanWithDefault",
            "Rank correlation with default weights",
            "Spearman rho [-1,1]",
        ),
    ]
    for name, y, title, ylabel in weight_plots:
        source = aggregate[["weightProfile", y]]
        source.to_csv(
            output / "figure_data" / f"{name}.csv", index=False
        )
        figure, axis = plt.subplots(figsize=(8.4, 4.8))
        axis.bar(
            source.weightProfile,
            source[y],
            color="#2C6E91",
        )
        axis.set_xlabel("Configured scoring weight profile")
        axis.set_ylabel(ylabel)
        axis.set_title(f"{title}\n{VERSION_NOTE}")
        axis.tick_params(axis="x", rotation=20)
        if y != "spearmanWithDefault":
            axis.set_ylim(0, 1)
        else:
            axis.set_ylim(-1, 1)
        axis.grid(axis="y", alpha=0.25)
        _finish_plot(figure, axis, output, name)

    clipping_source = clipping[
        clipping.clippingCount > 0
    ][["metric", "category", "clippingCount", "clippingRatio"]]
    clipping_source.to_csv(
        output / "figure_data" / "clipping_by_metric.csv",
        index=False,
    )
    figure, axis = plt.subplots(figsize=(9.5, 5.6))
    colors = [
        "#2C6E91"
        if category == "risk_normalization"
        else "#E09F3E"
        for category in clipping_source.category
    ]
    axis.barh(
        clipping_source.metric,
        clipping_source.clippingCount,
        color=colors,
    )
    axis.set_xlabel("Clipping events")
    axis.set_ylabel("Metric")
    axis.set_title(f"Clipping events by metric\n{VERSION_NOTE}")
    axis.grid(axis="x", alpha=0.25)
    _finish_plot(figure, axis, output, "clipping_by_metric")


def assert_finite(frames: dict[str, pd.DataFrame]) -> None:
    for name, frame in frames.items():
        numeric = frame.select_dtypes(include="number")
        if not np.isfinite(numeric.to_numpy()).all():
            raise ValueError(f"non-finite value in {name}")


def write_reports(
    output: Path,
    load: pd.DataFrame,
    feedback: pd.DataFrame,
    weights: pd.DataFrame,
    clipping: pd.DataFrame,
    pareto: pd.DataFrame,
    integrity: dict[str, Any],
) -> None:
    abrupt = load[load.feasibleRatioAbruptDrop]
    abrupt_text = (
        abrupt.iloc[0].loadLevel if not abrupt.empty else "none"
    )
    no_feasible = load[load.firstNoFeasiblePoint]
    no_feasible_text = (
        no_feasible.iloc[0].loadLevel
        if not no_feasible.empty
        else "none"
    )
    risk_clips = int(
        clipping[
            clipping.category == "risk_normalization"
        ].clippingCount.sum()
    )
    performance_clips = int(
        clipping[
            clipping.category == "performance_output"
        ].clippingCount.sum()
    )
    report = f"""# ??????????

## ?????

?????? `results/formal/formal-experiments-v1-20260731/`?
????31???case?v0.1.1?`simplified-ran-v1`???????
?????????????????????????????

## ????

??????????????
{', '.join(f'{value:.4f}' for value in load.feasibleRatio)}???????
{', '.join(f'{value:.6f}' for value in load.bestTotalScore)}???????
`RAN-POLICY-R00-0016`???????????????????
`{abrupt_text}`????????`{no_feasible_text}`?Pareto????
???{', '.join(str(value) for value in load.paretoNonDominatedCount)}?

## ??????

??seed???????????
`{int(feedback.evaluatedPolicyCountDelta.iloc[0])}`???????
`{int(feedback.feasiblePolicyCountDelta.iloc[0])}`??????
`{feedback.bestTotalScoreDelta.iloc[0]:.6f}`?????????????
??????????????????????

## ?????

???????seed?????????????????????Top-5
?????????????????Jaccard?
`{weights[weights.weightProfile == 'resource_priority'].top5JaccardWithDefault.mean():.4f}`?
????Pareto?????Pareto???????????????????
????????????Pareto??????????????
`weight_sensitivity_analysis.csv`?

## ??

???????`{risk_clips}`????????`{performance_clips}`??
?????????????`voiceQualityScore`??????????
???????????0???????????

## ??

- ??seed?????????????????????????????
  ??????????
- ?????????????????????????????
- ???????????????`rawValue-clippedValue`???
- ?????????????????????????????
"""
    (output / "statistical_analysis_report.md").write_text(
        report, encoding="utf-8"
    )
    acceptance = f"""# ????????

???**??**?

- ????????`results/formal/formal-experiments-v1-20260731/`
- ??????{integrity['sourceFileCount']}
- ???????SHA-256????{integrity['changedSourceFileCount']}
- ??case?31??????
- ????CSV???
- ????11?PNG?11?PDF?11??CSV
- ?????????
- ??????????
- ??????JSON?????
- ??manifest?????????

???????????????????????????????
"""
    (output / "analysis_acceptance_report.md").write_text(
        acceptance, encoding="utf-8"
    )


def run_analysis(
    formal_root: Path = FORMAL_ROOT,
    output: Path | None = None,
) -> dict[str, Any]:
    root = formal_root.resolve()
    output = output or root / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    (output / "analysis_plan_v1.md").write_text(
        Path(__file__)
        .with_name("analysis_plan_v1.md")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    before = source_hashes(root)
    summary = pd.read_csv(root / "all_experiments_summary.csv")
    cases = case_directories(root)
    if len(summary) != 31 or len(cases) != 31:
        raise ValueError("formal source must contain exactly 31 cases")
    load = build_load_analysis(summary, cases)
    feedback = build_feedback_analysis(summary, cases)
    weights = build_weight_analysis(summary, cases)
    clipping = build_clipping_analysis(cases)
    pareto = build_pareto_analysis(cases)
    frames = {
        "load_sweep_analysis": load,
        "feedback_compare_analysis": feedback,
        "weight_sensitivity_analysis": weights,
        "clipping_analysis": clipping,
        "pareto_analysis": pareto,
    }
    assert_finite(frames)
    for name, frame in frames.items():
        frame.to_csv(output / f"{name}.csv", index=False)
    generate_figures(output, load, feedback, weights, clipping)
    after = source_hashes(root)
    changed = sorted(
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )
    integrity = {
        "sourceFileCount": len(before),
        "changedSourceFileCount": len(changed),
        "changedSourceFiles": changed,
        "sourceRoot": root.as_posix(),
    }
    _write_json(output / "source_integrity.json", integrity)
    write_reports(
        output,
        load,
        feedback,
        weights,
        clipping,
        pareto,
        integrity,
    )
    return {
        "output": output,
        "frames": frames,
        "integrity": integrity,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run_analysis()
