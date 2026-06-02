"""Judge threshold calibration.

When using a new judge model, run `wildidea calibrate` to determine
how its scores compare to the reference (Claude Sonnet 4.5).

Usage:
    wildidea calibrate                                    # calibrate current judge model
    wildidea calibrate --judge-model deepseek/deepseek-v4-pro  # calibrate specific model
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Optional

from .configure import load_config, save_config
from .llm import LLMClient
from .judge import JudgeClient, JudgeConfig, _JUDGE_TEMPLATE


# Calibration examples: known candidates with reference scores from Claude Sonnet 4.5
# These are real WildIdea outputs evaluated by Claude Sonnet 4.5 (temp=0)
CALIBRATION_EXAMPLES = [
    {
        "problem": "在线教育学生注意力下降的创新干预方法",
        "source_domain": "防火分区（建筑安全）",
        "target_domain": "在线教育注意力",
        "proto": "将大空间切成隔间，用隔断和压差限制局部灾害蔓延，牺牲局部保全整体",
        "desc": "将课程内容切分为独立评估隔间，每个隔间设有认知评估检查点。当学习者在某个模块出现认知过载或分心时，系统自动隔离该模块，防止挫败感蔓延到后续模块。",
        "ref_scores": {"structural_depth": 8, "domain_distance": 9, "novelty": 8, "applicability": 7},
    },
    {
        "problem": "在线教育学生注意力下降的创新干预方法",
        "source_domain": "岛屿生物地理学",
        "target_domain": "在线教育注意力",
        "proto": "MacArthur-Wilson 岛屿平衡模型：迁入率和灭绝率决定岛屿物种数",
        "desc": "将课程中的学习模块视为岛屿，学习者的注意力资源视为物种。高频访问的模块保持丰富互动，低频模块自动精简内容以降低认知灭绝率。",
        "ref_scores": {"structural_depth": 7, "domain_distance": 9, "novelty": 7, "applicability": 6},
    },
    {
        "problem": "杯子的非常规用途方向",
        "source_domain": "V2G 双向电力服务",
        "target_domain": "杯子",
        "proto": "闲置资产被聚合并双向调度，同时满足主用途约束和外部系统需求",
        "desc": "将杯子闲置时段视为可调度资源。杯子底部集成压力传感器，检测闲置时长后自动切换功能模式：短闲置时显示天气/日程，长闲置时进入保温节能模式。",
        "ref_scores": {"structural_depth": 8, "domain_distance": 9, "novelty": 8, "applicability": 9},
    },
]


def calibrate_judge(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    proxy: Optional[str] = None,
) -> dict:
    """Run calibration and return bias dict.

    Returns:
        {
            "model": str,
            "bias": {"structural_depth": float, "domain_distance": float, ...},
            "recommended_thresholds": {"sd淘汰线": int, "sd平均线": float},
            "per_example": [...]
        }
    """
    from .style import section, info, success, warn, score_line, bold, dim

    llm = LLMClient(provider=provider, model=model, api_key=api_key, base_url=base_url, proxy=proxy)

    section(f"Calibrating {bold(model)}")

    # Reference scores from Claude Sonnet 4.5
    ref_dims = ["structural_depth", "domain_distance", "novelty", "applicability"]

    all_biases = {d: [] for d in ref_dims}
    per_example = []

    for i, ex in enumerate(CALIBRATION_EXAMPLES, 1):
        info(f"Example {i}/{len(CALIBRATION_EXAMPLES)}: {ex['source_domain']} → {ex['target_domain']}")

        object_mappings = f"Source mechanism: {ex['proto'][:200]} -> Target application: {ex['desc'][:200]}"
        shared_relations = "The structural relationship pattern from the source domain is preserved in the target domain mapping."

        prompt = _JUDGE_TEMPLATE.substitute(
            problem=ex["problem"],
            source_domain=ex["source_domain"],
            target_domain=ex["target_domain"],
            object_mappings=object_mappings,
            shared_relations=shared_relations,
        )

        try:
            parsed = llm.chat_json(
                system="You are an independent mapping quality evaluator.",
                user=prompt,
                temperature=0.0,
                max_tokens=2000,
            )
        except Exception as e:
            warn(f"Failed: {e}")
            continue

        # Extract scores
        scores = {}
        for dim in ref_dims:
            val = parsed.get(dim, {})
            if isinstance(val, dict):
                scores[dim] = int(val.get("score", 0))
            elif isinstance(val, (int, float)):
                scores[dim] = int(val)

        # Calculate bias
        example_result = {"scores": scores, "ref": ex["ref_scores"], "bias": {}}
        for dim in ref_dims:
            bias = scores.get(dim, 0) - ex["ref_scores"][dim]
            all_biases[dim].append(bias)
            example_result["bias"][dim] = bias

        per_example.append(example_result)

        # Show comparison
        for dim in ref_dims:
            ref_val = ex["ref_scores"][dim]
            test_val = scores.get(dim, 0)
            bias = test_val - ref_val
            sign = "+" if bias > 0 else ""
            print(f"    {dim:<20} ref={ref_val}  test={test_val}  bias={sign}{bias}")

        print()

    if not per_example:
        return {"error": "All calibration examples failed"}

    # Compute average bias per dimension
    avg_bias = {}
    for dim in ref_dims:
        if all_biases[dim]:
            avg_bias[dim] = round(statistics.mean(all_biases[dim]), 2)
        else:
            avg_bias[dim] = 0

    # Compute recommended thresholds
    # Base threshold (Claude) + average bias
    base_sd_threshold = 6
    base_sd_avg = 6.0
    sd_bias = avg_bias.get("structural_depth", 0)
    recommended_sd = max(5, base_sd_threshold + round(sd_bias))
    recommended_avg = max(5.0, base_sd_avg + sd_bias)

    result = {
        "model": model,
        "bias": avg_bias,
        "recommended_thresholds": {
            "sd淘汰线": recommended_sd,
            "sd平均线": recommended_avg,
        },
        "per_example": per_example,
    }

    # Summary
    section("Calibration Results")
    info(f"Reference: Claude Sonnet 4.5 (SD threshold: ≥ {base_sd_threshold})")
    print()
    for dim in ref_dims:
        bias = avg_bias[dim]
        sign = "+" if bias > 0 else ""
        print(f"    {dim:<20} avg bias: {sign}{bias}")
    print()
    info(f"Recommended SD threshold: ≥ {recommended_sd} (base {base_sd_threshold} + bias {sd_bias:+.1f})")

    return result


def save_calibration(result: dict):
    """Save calibration result to config."""
    config = load_config()
    config["judge_calibration"] = {
        "model": result["model"],
        "bias": result["bias"],
        "sd_threshold": result["recommended_thresholds"]["sd淘汰线"],
        "sd_avg_threshold": result["recommended_thresholds"]["sd平均线"],
    }
    save_config(config)
    from .style import success
    success(f"Calibration saved to ~/.wildidea/config.json")


def get_calibrated_thresholds(model: str, config: dict) -> tuple[int, float]:
    """Get thresholds for a model, using calibration if available."""
    cal = config.get("judge_calibration", {})
    if cal.get("model") == model:
        return cal.get("sd_threshold", 6), cal.get("sd_avg_threshold", 6.0)
    # Fall back to default table
    from .judge import get_thresholds
    return get_thresholds(model)
