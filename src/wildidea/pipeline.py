"""Core pipeline: orchestrates slot picking, candidate generation, search, judging, rendering."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .core.domain_pool import build_slots, PoolExhausted
from .core.search import search_sogou
from .judge import JudgeClient, JudgeConfig, JudgeScores
from .llm import LLMClient
from .renderer import Candidate, render

logger = logging.getLogger(__name__)

# Paths relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.txt").read_text(encoding="utf-8")
_TEMPLATE = _PROJECT_ROOT / "templates" / "poster.html"

# Problem type keywords
_TYPE_KEYWORDS = {
    "algorithm": ["算法", "模型", "识别", "预测", "优化", "信号", "控制", "训练", "推理", "network", "model"],
    "research": ["科研", "研究", "实验", "假设", "机制", "hypothesis", "mechanism", "biology", "physics"],
    "product": ["产品", "功能", "体验", "app", "设计", "用户", "交互", "feature", "ux"],
    "strategy": ["策略", "增长", "商业", "运营", "管理", "市场", "growth", "business", "market"],
}


@dataclass
class Config:
    """Pipeline configuration."""
    provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-4.5"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    proxy: Optional[str] = None
    judge_config: Optional[JudgeConfig] = None
    forbid_terms: list[str] = field(default_factory=list)
    output_dir: Path = field(default_factory=lambda: Path("outputs"))
    search_enabled: bool = True
    max_retries: int = 3


@dataclass
class Result:
    """Pipeline output."""
    html_path: Optional[Path] = None
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    avg_scores: dict = field(default_factory=dict)


def detect_type(problem: str) -> str:
    """Auto-detect problem type from keywords."""
    problem_lower = problem.lower()
    scores = {}
    for ptype, keywords in _TYPE_KEYWORDS.items():
        scores[ptype] = sum(1 for kw in keywords if kw in problem_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "product"


def _generate_candidate(
    problem: str,
    slot: dict,
    llm: LLMClient,
) -> Optional[dict]:
    """Generate one candidate from a domain slot."""
    anchor_desc = slot.get("anchor", "")
    if slot.get("methods"):
        m = slot["methods"][0]
        if m.get("mechanism"):
            anchor_desc = m["mechanism"]
        if m.get("key_insight"):
            anchor_desc += f" | Key insight: {m['key_insight']}"

    user_msg = (
        f"User problem: {problem}\n\n"
        f"Domain slot: {slot.get('slot', '?')} ({slot.get('domain', '?')})\n"
        f"Source mechanism: {anchor_desc}\n\n"
        f"Generate ONE candidate following the system prompt rules. "
        f"Output ONLY valid JSON."
    )

    try:
        raw = llm.chat(system=_SYSTEM_PROMPT, user=user_msg, temperature=0.7)
        # Extract JSON
        from .llm import extract_json
        parsed = extract_json(raw)
        if parsed and "name" in parsed and "desc" in parsed:
            # Fill in slot info if missing
            parsed.setdefault("slot", slot.get("slot", "?"))
            parsed.setdefault("source", slot.get("domain", "?"))
            return parsed
    except Exception as e:
        logger.warning(f"Candidate generation failed: {e}")
    return None


def _search_dedup(name: str, desc: str) -> bool:
    """Check if candidate already exists. Returns True if found (should ban)."""
    try:
        results = search_sogou(name, top=3)
        for r in results:
            title = r.get("title", "").lower()
            if name.lower() in title or title in name.lower():
                return True
    except Exception:
        pass  # Search failure is not a ban
    return False


def _validate_candidate(candidate: dict, forbid_terms: list[str]) -> list[str]:
    """Basic validation of a candidate dict."""
    errors = []
    for key in ("name", "proto", "desc", "fail"):
        if not candidate.get(key):
            errors.append(f"Missing field: {key}")

    # De-anchoring check
    import unicodedata
    proto = candidate.get("proto", "")
    proto_norm = unicodedata.normalize("NFKC", proto).casefold()
    for term in forbid_terms:
        term_norm = unicodedata.normalize("NFKC", term).casefold()
        if term_norm and term_norm in proto_norm:
            errors.append(f"Proto leaks user-domain term: {term}")

    return errors


def run(problem: str, config: Config) -> Result:
    """Execute the full WildIdea pipeline.

    Args:
        problem: The user's problem statement.
        config: Pipeline configuration.

    Returns:
        Result with HTML path, candidates, and scores.
    """
    result = Result()
    problem_type = detect_type(problem)
    logger.info(f"Problem type: {problem_type}")

    # Initialize LLM client
    llm = LLMClient(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        proxy=config.proxy,
    )

    # 1. Pick domain slots
    logger.info("Picking domain slots...")
    try:
        slots = build_slots(problem_type)
    except PoolExhausted as e:
        result.errors.append(str(e))
        return result

    logger.info(f"Got {len(slots)} slots")

    # 2. Generate candidates
    candidates: list[Candidate] = []
    exclude_ids = []

    for slot in slots:
        if len(candidates) >= 10:
            break

        for attempt in range(config.max_retries):
            logger.info(f"  Generating candidate for {slot.get('slot','?')} ({slot.get('domain','?')}) attempt {attempt+1}")

            raw = _generate_candidate(problem, slot, llm)
            if not raw:
                continue

            # 3. Search dedup
            if config.search_enabled:
                if _search_dedup(raw.get("name", ""), raw.get("desc", "")):
                    logger.info(f"    Banned by search dedup")
                    continue

            # 4. Validate
            errors = _validate_candidate(raw, config.forbid_terms)
            if errors:
                logger.info(f"    Validation failed: {errors}")
                continue

            candidates.append(Candidate(
                name=raw["name"],
                slot=raw.get("slot", slot.get("slot", "?")),
                source=raw.get("source", slot.get("domain", "?")),
                proto=raw.get("proto", ""),
                desc=raw.get("desc", ""),
                fail=raw.get("fail", ""),
            ))
            exclude_ids.append(slot.get("id", ""))
            break

    logger.info(f"Generated {len(candidates)} candidates")
    result.candidates = candidates

    # 5. Independent judge evaluation
    if candidates and config.judge_config:
        logger.info("Running independent judge evaluation...")
        judge = JudgeClient(config.judge_config)
        for c in candidates:
            try:
                c.scores = judge.evaluate(
                    problem=problem,
                    source_domain=c.source,
                    target_domain=problem,
                    proto=c.proto,
                    desc=c.desc,
                )
                logger.info(f"  {c.name}: SD={c.scores.structural_depth}")
            except Exception as e:
                logger.warning(f"  Judge failed for {c.name}: {e}")

        # 6. Eliminate low scores
        before = len(candidates)
        candidates = [c for c in candidates if c.scores and judge.passes_threshold(c.scores)]
        if len(candidates) < before:
            logger.info(f"Eliminated {before - len(candidates)} candidates below SD threshold")
        result.candidates = candidates

    # 7. Compute average scores
    scored = [c for c in candidates if c.scores]
    if scored:
        result.avg_scores = {
            "structural_depth": sum(c.scores.structural_depth for c in scored) / len(scored),
            "domain_distance": sum(c.scores.domain_distance for c in scored) / len(scored),
            "novelty": sum(c.scores.novelty for c in scored) / len(scored),
            "applicability": sum(c.scores.applicability for c in scored) / len(scored),
        }

    # 8. Render HTML
    if candidates and _TEMPLATE.exists():
        title = problem[:40]
        focus = f"{problem_type} · {len(candidates)} candidates"
        safe_name = re.sub(r"[^\w一-鿿]+", "-", problem[:30]).strip("-")
        output_path = config.output_dir / f"{safe_name}.html"

        stats = ""
        if result.avg_scores:
            stats = f"Avg SD: {result.avg_scores['structural_depth']:.1f} | Avg NV: {result.avg_scores['novelty']:.1f}"

        result.html_path = render(
            candidates=candidates,
            title=title,
            focus=focus,
            template_path=_TEMPLATE,
            output_path=output_path,
            ban_tags=config.forbid_terms[:8],
            stats=stats,
        )
        logger.info(f"HTML saved to {result.html_path}")

    return result
