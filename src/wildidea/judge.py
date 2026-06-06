"""Independent judge for mapping quality evaluation.

Uses the G.6 Analogy Judge Prompt from Shen et al. 2026 (arXiv:2605.11258).
Runs as a separate LLM call with no context from the generation process.
"""
from __future__ import annotations

import json
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm import LLMClient


_JUDGE_TEMPLATE = string.Template(
    (Path(__file__).parent / "prompts" / "judge.txt").read_text(encoding="utf-8")
)


@dataclass
class JudgeScores:
    structural_depth: int = 0
    domain_distance: int = 0
    applicability: int = 0
    novelty: int = 0
    unexpectedness: int = 0
    non_obviousness: int = 0
    raw: dict = field(default_factory=dict)

    @property
    def sd(self) -> int:
        return self.structural_depth


@dataclass
class JudgeConfig:
    model: str
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    proxy: Optional[str] = None
    sd_threshold: Optional[int] = None
    sd_avg_threshold: Optional[float] = None
    novelty_threshold: int = 7
    applicability_threshold: int = 9


# Threshold lookup by model prefix
THRESHOLD_TABLE = {
    "anthropic/claude-sonnet": (6, 6.0),
    "deepseek/deepseek-v4": (8, 8.0),
    "deepseek/deepseek-r1": (9, 9.0),  # Known inflated, not recommended
}


def get_thresholds(model: str) -> tuple[int, float]:
    """Return (sd淘汰线, sd平均线) for a given model."""
    for prefix, (thr, avg) in THRESHOLD_TABLE.items():
        if model.startswith(prefix):
            return thr, avg
    # Default: assume Claude-level calibration
    return 6, 6.0


class JudgeClient:
    """Independent mapping quality judge. No context from generation."""

    def __init__(self, config: JudgeConfig):
        self.config = config
        self.llm = LLMClient(
            provider=config.provider,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            proxy=config.proxy,
        )
        model_sd_threshold, model_sd_avg_threshold = get_thresholds(config.model)
        self.sd_threshold = config.sd_threshold if config.sd_threshold is not None else model_sd_threshold
        self.sd_avg_threshold = config.sd_avg_threshold if config.sd_avg_threshold is not None else model_sd_avg_threshold
        self.novelty_threshold = config.novelty_threshold
        self.applicability_threshold = config.applicability_threshold

    def evaluate(
        self,
        problem: str,
        source_domain: str,
        target_domain: str,
        proto: str,
        desc: str,
    ) -> JudgeScores:
        """Evaluate a single candidate's mapping quality."""
        object_mappings = f"Source mechanism: {proto[:200]} -> Target application: {desc[:200]}"
        shared_relations = (
            "The structural relationship pattern from the source domain "
            "is preserved in the target domain mapping."
        )

        prompt = _JUDGE_TEMPLATE.substitute(
            problem=problem,
            source_domain=source_domain,
            target_domain=target_domain,
            object_mappings=object_mappings,
            shared_relations=shared_relations,
        )

        parsed = self.llm.chat_json(
            system="You are an independent mapping quality evaluator. You have no knowledge of the generation process.",
            user=prompt,
            temperature=0.0,
            max_tokens=2000,
        )

        scores = JudgeScores(raw=parsed)
        dims = [
            "structural_depth", "domain_distance", "applicability",
            "novelty", "unexpectedness", "non_obviousness",
        ]
        for dim in dims:
            val = parsed.get(dim, {})
            if isinstance(val, dict):
                setattr(scores, dim, int(val.get("score", 0)))
            elif isinstance(val, (int, float)):
                setattr(scores, dim, int(val))
        return scores

    def passes_threshold(self, scores: JudgeScores) -> bool:
        return (
            scores.structural_depth >= self.sd_threshold
            and scores.novelty >= self.novelty_threshold
            and scores.applicability >= self.applicability_threshold
        )
