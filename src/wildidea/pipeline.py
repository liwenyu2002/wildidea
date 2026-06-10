"""Core pipeline: orchestrates slot picking, candidate generation, judging, and rendering."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .core.domain_pool import build_slots, PoolExhausted
from .judge import JudgeClient, JudgeConfig
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
    search_enabled: bool = False  # Deprecated: search dedup is no longer used.
    max_retries: int = 3
    parallel: int = 10  # Number of parallel generation workers (1 = sequential)
    target_count: int = 10


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


def _validate_candidate(candidate: dict, forbid_terms: list[str]) -> list[str]:
    """Basic validation of a candidate dict."""
    errors = []
    for key in ("name", "proto", "advantage", "desc", "fail"):
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


def _slot_id(slot: dict) -> str:
    """Stable enough per-run identifier for progress events."""
    return str(slot.get("id") or slot.get("query") or f"{slot.get('slot', 'slot')}:{slot.get('domain', '?')}")


def _source_phenomenon(slot: dict) -> str:
    """Return a concrete source phenomenon, repairing known truncated anchors when possible."""
    anchor = str(slot.get("anchor") or slot.get("query") or slot.get("domain") or "")
    methods = slot.get("methods") or []
    method = methods[0] if methods else {}
    mechanism = str(method.get("mechanism") or "")
    method_name = str(method.get("name") or "")

    if anchor and mechanism:
        for sep in ("：", ":"):
            if sep in anchor:
                title, detail = anchor.split(sep, 1)
                detail = detail.strip()
                if detail and mechanism.startswith(detail):
                    return f"{title.strip()}: {mechanism}"
        if _has_dangling_tail(anchor):
            return f"{method_name}: {mechanism}" if method_name else mechanism
    return anchor or mechanism


def _has_dangling_tail(text: str) -> bool:
    """Heuristic for pool rows that were cut mid-word during import."""
    stripped = text.strip()
    if len(stripped) < 80:
        return False
    last_word = stripped.rsplit(maxsplit=1)[-1]
    return len(last_word) <= 2 and last_word.isascii() and last_word.isalpha()


def _public_slot(slot: dict) -> dict:
    source_phenomenon = _source_phenomenon(slot)
    return {
        "slot_id": _slot_id(slot),
        "slot": slot.get("slot", "?"),
        "domain": slot.get("domain") or slot.get("slot_name") or slot.get("query") or "?",
        "source": source_phenomenon,
        "source_phenomenon": source_phenomenon,
    }


def _candidate_from_raw(raw: dict, slot: dict) -> Candidate:
    slot_name = slot.get("slot", "?")
    domain = slot.get("domain", "?")
    return Candidate(
        name=raw["name"],
        slot=raw.get("slot", slot_name),
        source=raw.get("source", domain),
        proto=raw.get("proto", ""),
        desc=raw.get("desc", ""),
        fail=raw.get("fail", ""),
        advantage=_normalize_advantage(raw.get("advantage", "")),
    )


def _normalize_advantage(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    prefix = "这种方案的优势在于，"
    if text.startswith(prefix) or text.startswith("这种方案的优势在于"):
        return text
    return f"{prefix}{text}"


def _score_event_payload(candidate: Candidate, judge: JudgeClient, passed: bool) -> dict:
    scores = candidate.scores
    average = _score_average(scores)
    return {
        "name": candidate.name,
        "source": candidate.source,
        "sd": scores.structural_depth if scores else None,
        "dd": scores.domain_distance if scores else None,
        "nv": scores.novelty if scores else None,
        "ap": scores.applicability if scores else None,
        "unexpectedness": scores.unexpectedness if scores else None,
        "non_obviousness": scores.non_obviousness if scores else None,
        "score_average": average,
        "pass": passed,
        "sd_threshold": judge.sd_threshold,
        "novelty_threshold": judge.novelty_threshold,
        "applicability_threshold": judge.applicability_threshold,
    }


def _score_average(scores) -> Optional[float]:
    if not scores:
        return None
    values = [
        scores.structural_depth,
        scores.domain_distance,
        scores.novelty,
        scores.applicability,
    ]
    numeric = [float(value) for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _candidate_ok_payload(slot_id: str, candidate: Candidate, done: int, total: int, attempt: int) -> dict:
    scores = candidate.scores
    quality_status = getattr(candidate, "quality_status", "passed") or "passed"
    refund_credit = bool(getattr(candidate, "refund_credit", False))
    return {
        "slot_id": slot_id,
        "index": done,
        "attempt": attempt,
        "reroll_count": getattr(candidate, "reroll_count", max(0, attempt - 1)),
        "name": candidate.name,
        "slot": candidate.slot,
        "source": candidate.source,
        "proto": candidate.proto,
        "advantage": candidate.advantage,
        "desc": candidate.desc,
        "fail": candidate.fail,
        "quality_status": quality_status,
        "refund_credit": refund_credit,
        "quality_note": getattr(candidate, "quality_note", ""),
        "score_average": _score_average(scores),
        "scores": {
            "structural_depth": scores.structural_depth,
            "domain_distance": scores.domain_distance,
            "applicability": scores.applicability,
            "novelty": scores.novelty,
            "unexpectedness": scores.unexpectedness,
            "non_obviousness": scores.non_obviousness,
            "raw": scores.raw,
        } if scores else {},
        "search": {
            "quality_status": quality_status,
            "refund_credit": refund_credit,
            "quality_note": getattr(candidate, "quality_note", ""),
            "score_average": _score_average(scores),
            "fallback_attempt": getattr(candidate, "fallback_attempt", None),
            "max_retries": getattr(candidate, "max_retries", None),
        },
        "done": done,
        "total": total,
    }


def _build_target_slots(problem_type: str, target_count: int) -> list[dict]:
    """Build approximately target_count slots while preserving the existing quota sampler."""
    target = max(1, min(int(target_count or 10), 30))
    slots: list[dict] = []
    exclude: list[str] = []

    while len(slots) < target:
        batch = build_slots(problem_type, exclude=exclude)
        for slot in batch:
            slots.append(slot)
            sid = slot.get("id")
            if sid:
                exclude.append(sid)
            if len(slots) >= target:
                break
    return slots[:target]


def run(problem: str, config: Config, on_progress=None) -> Result:
    """Execute the full WildIdea pipeline.

    Args:
        problem: The user's problem statement.
        config: Pipeline configuration.
        on_progress: Optional callback(event: str, data: dict) for real-time progress.

    Returns:
        Result with HTML path, candidates, and scores.
    """
    def _emit(event: str, **data):
        if on_progress:
            on_progress(event, data)

    result = Result()
    problem_type = detect_type(problem)
    _emit("type", value=problem_type)

    # Initialize LLM client
    llm = LLMClient(
        provider=config.provider,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        proxy=config.proxy,
    )

    # 1. Pick domain slots
    _emit("slots_start")
    try:
        slots = _build_target_slots(problem_type, config.target_count)
    except PoolExhausted as e:
        result.errors.append(str(e))
        _emit("error", message=str(e))
        return result

    target_count = len(slots)
    _emit("slots_done", count=target_count, target=target_count, slots=[_public_slot(s) for s in slots])

    # 2. Generate candidates (parallel or sequential)
    candidates: list[Candidate] = []
    exclude_ids = []
    slots_todo = list(slots)

    def _try_slot(slot):
        """Try to generate and judge one candidate from a slot."""
        slot_name = slot.get("slot", "?")
        domain = slot.get("domain", "?")
        slot_id = _slot_id(slot)
        judge = JudgeClient(config.judge_config) if config.judge_config else None
        best_failed: Optional[Candidate] = None
        best_failed_attempt = 0
        best_failed_average = -1.0
        for attempt in range(config.max_retries):
            _emit(
                "generating",
                slot_id=slot_id,
                slot=slot_name,
                domain=domain,
                attempt=attempt + 1,
                total=target_count,
                done=len(candidates),
            )
            raw = _generate_candidate(problem, slot, llm)
            if not raw:
                continue
            errors = _validate_candidate(raw, config.forbid_terms)
            if errors:
                _emit("invalid", slot_id=slot_id, slot=slot_name, errors=errors)
                continue
            candidate = _candidate_from_raw(raw, slot)
            if judge:
                try:
                    _emit(
                        "judging",
                        slot_id=slot_id,
                        slot=slot_name,
                        name=candidate.name,
                        attempt=attempt + 1,
                        index=min(len(candidates) + 1, target_count),
                        total=target_count,
                    )
                    candidate.scores = judge.evaluate(
                        problem=problem,
                        source_domain=candidate.source,
                        target_domain=problem,
                        proto=candidate.proto,
                        desc=candidate.desc,
                    )
                    passed = judge.passes_threshold(candidate.scores)
                    score_payload = _score_event_payload(candidate, judge, passed)
                    _emit("judged", slot_id=slot_id, slot=slot_name, **score_payload)
                    if not passed:
                        average = score_payload.get("score_average")
                        if average is not None and float(average) > best_failed_average:
                            best_failed = candidate
                            best_failed_attempt = attempt + 1
                            best_failed_average = float(average)
                        _emit(
                            "threshold_rejected",
                            slot_id=slot_id,
                            slot=slot_name,
                            attempt=attempt + 1,
                            **score_payload,
                        )
                        continue
                except Exception as e:
                    _emit("judge_fail", slot_id=slot_id, slot=slot_name, name=candidate.name, error=str(e))
                    continue
            candidate.reroll_count = max(0, attempt)
            return slot, candidate, attempt + 1
        if best_failed:
            best_failed.reroll_count = max(0, config.max_retries - 1)
            best_failed.quality_status = "fallback_refunded"
            best_failed.refund_credit = True
            best_failed.quality_note = "这张卡触达重抽上限，未通过质量阈值；已展示均分最高版本，并退回该卡积分。"
            best_failed.fallback_attempt = best_failed_attempt
            best_failed.max_retries = config.max_retries
            best_failed.score_average = best_failed_average
            return slot, best_failed, config.max_retries
        return slot, None, config.max_retries

    if config.parallel > 1:
        # Parallel generation
        _emit("parallel_start", workers=config.parallel, total=len(slots_todo))
        try:
            with ThreadPoolExecutor(max_workers=config.parallel) as pool:
                futures = {pool.submit(_try_slot, s): s for s in slots_todo[:config.parallel * 2]}
                for future in as_completed(futures):
                    if len(candidates) >= target_count:
                        break
                    slot, candidate, attempt = future.result()
                    slot_id = _slot_id(slot)
                    if candidate:
                        candidates.append(candidate)
                        exclude_ids.append(slot.get("id", ""))
                        event = "candidate_fallback" if getattr(candidate, "refund_credit", False) else "candidate_ok"
                        _emit(event, **_candidate_ok_payload(slot_id, candidate, len(candidates), target_count, attempt))
                    else:
                        slot_name = slot.get("slot", "?")
                        _emit("gen_fail", slot_id=slot_id, slot=slot_name, reason="exhausted retries")

                # If not enough, fill with sequential
                remaining = [s for s in slots_todo if s.get("id") not in exclude_ids]
                for slot in remaining:
                    if len(candidates) >= target_count:
                        break
                    slot_id = _slot_id(slot)
                    _, candidate, attempt = _try_slot(slot)
                    if candidate:
                        candidates.append(candidate)
                        event = "candidate_fallback" if getattr(candidate, "refund_credit", False) else "candidate_ok"
                        _emit(event, **_candidate_ok_payload(slot_id, candidate, len(candidates), target_count, attempt))
                    else:
                        slot_name = slot.get("slot", "?")
                        _emit("gen_fail", slot_id=slot_id, slot=slot_name, reason="exhausted retries")
        except KeyboardInterrupt:
            _emit("error", message="Interrupted by user")
    else:
        # Sequential generation (original behavior)
        try:
            for slot in slots_todo:
                if len(candidates) >= target_count:
                    break
                slot_id = _slot_id(slot)
                _, candidate, attempt = _try_slot(slot)
                if candidate:
                    candidates.append(candidate)
                    exclude_ids.append(slot.get("id", ""))
                    event = "candidate_fallback" if getattr(candidate, "refund_credit", False) else "candidate_ok"
                    _emit(event, **_candidate_ok_payload(slot_id, candidate, len(candidates), target_count, attempt))
                else:
                    slot_name = slot.get("slot", "?")
                    _emit("gen_fail", slot_id=slot_id, slot=slot_name, reason="empty response")
        except KeyboardInterrupt:
            _emit("error", message="Interrupted by user")

    _emit("candidates_done", count=len(candidates), target=target_count)
    result.candidates = candidates

    # 5. Compute average scores
    scored = [c for c in candidates if c.scores]
    if scored:
        result.avg_scores = {
            "structural_depth": sum(c.scores.structural_depth for c in scored) / len(scored),
            "domain_distance": sum(c.scores.domain_distance for c in scored) / len(scored),
            "novelty": sum(c.scores.novelty for c in scored) / len(scored),
            "applicability": sum(c.scores.applicability for c in scored) / len(scored),
        }

    # 6. Render HTML
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
        _emit("rendered", path=str(result.html_path))

    _emit("done", candidates=len(candidates), scores=result.avg_scores)
    return result
