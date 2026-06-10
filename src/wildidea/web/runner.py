"""Background execution bridge from web runs to the existing WildIdea pipeline."""
from __future__ import annotations

import json
from threading import Lock
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from wildidea.configure import get_config
from wildidea.judge import JudgeConfig
from wildidea.pipeline import Config, detect_type, run as run_pipeline

from .config import settings
from .database import SessionLocal
from .models import Artifact, Candidate, CreditTransaction, Run, RunEvent, User, utcnow
from .observability import add_run_log
from .services import add_credit_transaction, refund_run_credit


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {k: _json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_safe(v) for v in value]
        return str(value)


def _score_payload(scores) -> dict:
    if not scores:
        return {}
    return {
        "structural_depth": scores.structural_depth,
        "domain_distance": scores.domain_distance,
        "applicability": scores.applicability,
        "novelty": scores.novelty,
        "unexpectedness": scores.unexpectedness,
        "non_obviousness": scores.non_obviousness,
        "raw": scores.raw,
    }


def _truncate(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _payload_scores(data: dict) -> dict:
    scores = data.get("scores") or {}
    return _json_safe(scores) if isinstance(scores, dict) else {}


def _quality_meta(data: dict) -> dict:
    search = data.get("search") if isinstance(data.get("search"), dict) else {}
    return {
        **_json_safe(search),
        "quality_status": data.get("quality_status") or search.get("quality_status") or "passed",
        "refund_credit": bool(data.get("refund_credit") or search.get("refund_credit")),
        "quality_note": data.get("quality_note") or search.get("quality_note") or "",
        "score_average": data.get("score_average", search.get("score_average")),
        "fallback_attempt": data.get("fallback_attempt", search.get("fallback_attempt")),
        "max_retries": data.get("max_retries", search.get("max_retries")),
    }


def _candidate_from_payload(db, run_id: str, data: dict) -> Candidate | None:
    index = int(data.get("index") or data.get("done") or 0)
    if index <= 0:
        return None
    candidate = db.scalar(
        select(Candidate).where(Candidate.run_id == run_id, Candidate.index == index)
    )
    if not candidate:
        candidate = Candidate(run_id=run_id, index=index)
    candidate.name = _truncate(data.get("name") or f"方案 {index}", 255)
    candidate.slot = _truncate(data.get("slot") or "?", 40)
    candidate.source = _truncate(data.get("source") or "", 255)
    candidate.proto = str(data.get("proto") or "")
    candidate.advantage = str(data.get("advantage") or "")
    candidate.desc = str(data.get("desc") or "")
    candidate.fail = str(data.get("fail") or "")
    candidate.scores_json = _payload_scores(data)
    candidate.search_json = _quality_meta(data)
    candidate.reroll_count = int(data.get("reroll_count") or 0)
    db.add(candidate)
    return candidate


def _candidate_from_result(db, run_id: str, index: int, item) -> Candidate:
    candidate = db.scalar(
        select(Candidate).where(Candidate.run_id == run_id, Candidate.index == index)
    )
    if not candidate:
        candidate = Candidate(run_id=run_id, index=index)
    candidate.name = _truncate(item.name, 255)
    candidate.slot = _truncate(item.slot, 40)
    candidate.source = _truncate(item.source, 255)
    candidate.proto = item.proto
    candidate.advantage = item.advantage
    candidate.desc = item.desc
    candidate.fail = item.fail
    candidate.scores_json = _score_payload(item.scores)
    candidate.search_json = {
        **(candidate.search_json or {}),
        "quality_status": getattr(item, "quality_status", "passed") or "passed",
        "refund_credit": bool(getattr(item, "refund_credit", False)),
        "quality_note": getattr(item, "quality_note", ""),
        "score_average": getattr(item, "score_average", None),
        "fallback_attempt": getattr(item, "fallback_attempt", None),
        "max_retries": getattr(item, "max_retries", None),
    }
    candidate.reroll_count = int(getattr(item, "reroll_count", 0) or 0)
    db.add(candidate)
    return candidate


def _progress_log_message(event: str, data: dict) -> str:
    if event == "slots_done":
        return f"slots ready: {data.get('count') or len(data.get('slots') or [])}/{data.get('target') or '?'}"
    if event == "candidate_ok":
        return f"candidate passed: {data.get('name') or data.get('index') or '?'}"
    if event == "candidate_fallback":
        return f"candidate fallback refunded: {data.get('name') or data.get('index') or '?'}"
    if event == "threshold_rejected":
        return f"candidate rerolled: {data.get('name') or data.get('slot_id') or '?'}"
    if event == "gen_fail":
        return f"card failed: {data.get('slot_id') or data.get('slot') or '?'}"
    if event == "judge_fail":
        return f"judge retry: {data.get('name') or data.get('slot_id') or '?'}"
    if event == "invalid":
        return f"candidate invalid: {data.get('slot_id') or '?'}"
    return event


def _progress_log_payload(event: str, data: dict) -> dict:
    keys = {
        "slots_done": ("count", "target"),
        "candidate_ok": ("index", "done", "total", "attempt", "reroll_count", "name", "slot", "slot_id", "advantage"),
        "candidate_fallback": (
            "index",
            "done",
            "total",
            "attempt",
            "reroll_count",
            "name",
            "slot",
            "slot_id",
            "quality_status",
            "refund_credit",
            "quality_note",
            "score_average",
        ),
        "threshold_rejected": (
            "attempt",
            "name",
            "slot",
            "slot_id",
            "sd",
            "nv",
            "ap",
            "sd_threshold",
            "novelty_threshold",
            "applicability_threshold",
        ),
        "gen_fail": ("slot", "slot_id", "reason"),
        "judge_fail": ("slot", "slot_id", "name", "error"),
        "invalid": ("slot", "slot_id", "errors"),
    }
    return {key: data.get(key) for key in keys.get(event, ()) if key in data}


def _build_pipeline_config(snapshot: dict, output_dir: Path) -> Config:
    local_config = get_config()
    provider = snapshot.get("provider") or local_config.get("provider") or settings.default_provider
    model = snapshot.get("model") or local_config.get("model") or settings.default_model
    judge_model = snapshot.get("judge_model") or local_config.get("judge_model") or settings.default_judge_model
    api_key = local_config.get("api_key")
    base_url = snapshot.get("base_url") or local_config.get("base_url") or settings.default_base_url
    proxy = snapshot.get("proxy") or local_config.get("proxy") or settings.default_proxy

    judge_config = JudgeConfig(
        model=judge_model,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        proxy=proxy,
    )
    return Config(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        proxy=proxy,
        judge_config=judge_config,
        forbid_terms=snapshot.get("forbid_terms") or [],
        output_dir=output_dir,
        search_enabled=False,
        max_retries=int(snapshot.get("max_retries") or 3),
        parallel=int(snapshot.get("parallel") or 10),
        target_count=int(snapshot.get("slot_count") or 10),
    )


def _charged_amount(db, run_id: str) -> int:
    return int(db.scalar(
        select(func.coalesce(func.sum(-CreditTransaction.amount), 0))
        .where(CreditTransaction.run_id == run_id, CreditTransaction.reason == "run_charge")
    ) or 0)


def _refund_missing_cards(db, user: User, run: Run, generated_count: int, visible_count: int | None = None) -> int:
    snapshot = run.config_snapshot or {}
    charged = _charged_amount(db, run.id)
    if charged <= 0:
        return 0
    earned = max(0, generated_count) * settings.run_credit_cost
    refund_amount = max(0, charged - earned)
    if refund_amount <= 0:
        return 0
    missing_cards = refund_amount // max(1, settings.run_credit_cost)
    add_credit_transaction(
        db,
        user,
        refund_amount,
        "run_partial_refund",
        run_id=run.id,
        meta={
            "requested_slots": snapshot.get("slot_count"),
            "generated_candidates": generated_count,
            "visible_candidates": visible_count if visible_count is not None else generated_count,
            "charged": charged,
            "missing_cards": missing_cards,
            "reason": "reroll_limit_or_quality_gate",
        },
    )
    db.add(RunEvent(
        run_id=run.id,
        event_type="refund",
        payload={
            "credits": refund_amount,
            "reason": "partial_card_refund",
            "missing_cards": missing_cards,
            "generated_candidates": generated_count,
            "visible_candidates": visible_count if visible_count is not None else generated_count,
            "requested_slots": snapshot.get("slot_count"),
        },
    ))
    add_run_log(
        db,
        run.id,
        "warning",
        "partial card refund",
        {
            "credits": refund_amount,
            "missing_cards": missing_cards,
            "generated_candidates": generated_count,
            "visible_candidates": visible_count if visible_count is not None else generated_count,
            "requested_slots": snapshot.get("slot_count"),
        },
    )
    return refund_amount


def _billable_candidate_count(candidates: list) -> int:
    return sum(
        1
        for item in candidates
        if not bool(getattr(item, "refund_credit", False))
        and getattr(item, "quality_status", "passed") != "fallback_refunded"
    )


def execute_run(run_id: str) -> None:
    """Execute a queued run in a background task."""
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run or run.status == "deleted":
            return
        user = db.get(User, run.user_id)
        if not user:
            return

        was_running = run.status == "running"
        run.status = "running"
        run.error = None
        run.started_at = utcnow()
        run.problem_type = detect_type(run.problem)
        if not was_running:
            db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "running"}))
        add_run_log(
            db,
            run.id,
            "info",
            "run execution started",
            {
                "executor": settings.run_executor,
                "slot_count": (run.config_snapshot or {}).get("slot_count"),
                "parallel": (run.config_snapshot or {}).get("parallel"),
            },
        )
        db.commit()

        output_dir = settings.output_dir / run.id
        output_dir.mkdir(parents=True, exist_ok=True)
        config = _build_pipeline_config(run.config_snapshot, output_dir=output_dir)
        progress_lock = Lock()

        def on_progress(event: str, data: dict) -> None:
            with progress_lock:
                event_db = SessionLocal()
                try:
                    safe_data = _json_safe(data)
                    event_db.add(RunEvent(run_id=run.id, event_type=event, payload=safe_data))
                    if event in {"candidate_ok", "candidate_fallback"}:
                        _candidate_from_payload(event_db, run.id, safe_data)
                    if event in {"slots_done", "candidate_ok", "candidate_fallback", "threshold_rejected", "gen_fail", "judge_fail", "invalid"}:
                        add_run_log(
                            event_db,
                            run.id,
                            "warning" if event in {"candidate_fallback", "threshold_rejected", "gen_fail", "judge_fail", "invalid"} else "info",
                            _progress_log_message(event, safe_data),
                            _progress_log_payload(event, safe_data),
                        )
                    event_db.commit()
                finally:
                    event_db.close()

        result = run_pipeline(run.problem, config, on_progress=on_progress)

        db.refresh(run)
        if run.status != "running":
            add_run_log(db, run.id, "warning", "run status changed during execution", {"status": run.status})
            db.commit()
            return

        for idx, item in enumerate(result.candidates, 1):
            _candidate_from_result(db, run.id, idx, item)

        if result.html_path:
            run.html_path = str(result.html_path)
            db.add(Artifact(run_id=run.id, kind="html", path=str(result.html_path)))

        run.avg_scores = result.avg_scores or {}
        run.finished_at = utcnow()
        if result.errors or not result.candidates:
            run.status = "failed"
            run.error = "; ".join(result.errors) if result.errors else "No candidates were generated"
            refund_run_credit(db, user, run)
            db.add(RunEvent(run_id=run.id, event_type="refund", payload={"credits": (run.config_snapshot or {}).get("credit_cost") or settings.run_credit_cost}))
            add_run_log(db, run.id, "error", "run failed and refunded", {"error": run.error})
        else:
            _refund_missing_cards(db, user, run, _billable_candidate_count(result.candidates), visible_count=len(result.candidates))
            run.status = "succeeded"
            run.error = None
            add_run_log(db, run.id, "info", "run succeeded", {"candidate_count": len(result.candidates)})
        db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": run.status}))
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(Run, run_id)
        if run:
            db.refresh(run)
            if run.status == "deleted":
                return
            user = db.get(User, run.user_id)
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            if user:
                refund_run_credit(db, user, run)
            db.add(RunEvent(run_id=run.id, event_type="error", payload={"message": str(exc)}))
            db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "failed"}))
            add_run_log(db, run.id, "error", "run exception and refunded", {"error": str(exc)})
            db.commit()
    finally:
        db.close()
