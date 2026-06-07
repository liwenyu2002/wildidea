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
    candidate.desc = str(data.get("desc") or "")
    candidate.fail = str(data.get("fail") or "")
    candidate.scores_json = _payload_scores(data)
    candidate.search_json = _json_safe(data.get("search") or {})
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
    candidate.desc = item.desc
    candidate.fail = item.fail
    candidate.scores_json = _score_payload(item.scores)
    candidate.reroll_count = int(getattr(item, "reroll_count", 0) or 0)
    db.add(candidate)
    return candidate


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


def _refund_missing_cards(db, user: User, run: Run, generated_count: int) -> int:
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
            "requested_slots": snapshot.get("slot_count"),
        },
    ))
    return refund_amount


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

        run.status = "running"
        run.error = None
        run.started_at = utcnow()
        run.problem_type = detect_type(run.problem)
        db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "running"}))
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
                    if event == "candidate_ok":
                        _candidate_from_payload(event_db, run.id, safe_data)
                    event_db.commit()
                finally:
                    event_db.close()

        result = run_pipeline(run.problem, config, on_progress=on_progress)

        db.refresh(run)
        if run.status != "running":
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
        else:
            _refund_missing_cards(db, user, run, len(result.candidates))
            run.status = "succeeded"
            run.error = None
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
            db.commit()
    finally:
        db.close()
