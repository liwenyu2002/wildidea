"""Operational logging and queue status helpers for the web app."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Run, RunLog, WorkerHeartbeat, utcnow

QUEUE_CARD_ESTIMATE_SECONDS = 90


def utc_iso(value: Any) -> str | None:
    """Serialize datetimes with an explicit UTC suffix for the frontend."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, datetime):
            return utc_iso(value)
        if isinstance(value, dict):
            return {str(k): json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [json_safe(v) for v in value]
        return str(value)


def add_run_log(
    db: Session,
    run_id: str | None,
    level: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> RunLog:
    row = RunLog(
        run_id=run_id,
        level=level,
        message=message,
        payload=json_safe(payload or {}),
    )
    db.add(row)
    return row


def _age_seconds(value: datetime | None) -> int | None:
    if not value:
        return None
    now = utcnow()
    if value.tzinfo is None:
        now = now.replace(tzinfo=None)
    return max(0, int((now - value).total_seconds()))


def _run_slot_count(run: Run) -> int:
    try:
        return max(1, int((run.config_snapshot or {}).get("slot_count") or 10))
    except (TypeError, ValueError):
        return 10


def _run_estimated_seconds(run: Run) -> int:
    return max(QUEUE_CARD_ESTIMATE_SECONDS, _run_slot_count(run) * QUEUE_CARD_ESTIMATE_SECONDS)


def _elapsed_seconds_since(value: datetime | None) -> int:
    if not value:
        return 0
    now = utcnow()
    if value.tzinfo is None:
        now = now.replace(tzinfo=None)
    return max(0, int((now - value).total_seconds()))


def _active_worker_capacity(db: Session) -> tuple[int, bool]:
    if settings.run_executor != "worker":
        return 1, True
    workers = db.scalars(select(WorkerHeartbeat).order_by(desc(WorkerHeartbeat.updated_at)).limit(50)).all()
    active_workers = [
        worker
        for worker in workers
        if (_age_seconds(worker.updated_at) or 10**9) <= settings.worker_stale_after_seconds
    ]
    return max(1, len(active_workers)), bool(active_workers)


def run_queue_status(db: Session, run: Run) -> dict[str, Any] | None:
    if run.status not in {"queued", "running"}:
        return None

    worker_capacity, worker_online = _active_worker_capacity(db)
    if run.status == "running":
        return {
            "status": "running",
            "queue_position": 0,
            "queued_ahead": 0,
            "running_ahead": 0,
            "tasks_ahead": 0,
            "users_ahead": 0,
            "estimated_wait_seconds": 0,
            "worker_capacity": worker_capacity,
            "worker_online": worker_online,
            "estimate_card_seconds": QUEUE_CARD_ESTIMATE_SECONDS,
            "calculated_at": utc_iso(utcnow()),
        }

    queued_before = db.scalars(
        select(Run)
        .where(
            Run.status == "queued",
            or_(
                Run.created_at < run.created_at,
                and_(Run.created_at == run.created_at, Run.id < run.id),
            ),
        )
        .order_by(Run.created_at, Run.id)
    ).all()
    running_runs = db.scalars(
        select(Run)
        .where(Run.status == "running")
        .order_by(Run.started_at, Run.created_at, Run.id)
    ).all()

    lane_finish_seconds = [0] * worker_capacity
    for item in running_runs:
        estimate = _run_estimated_seconds(item)
        elapsed = _elapsed_seconds_since(item.started_at or item.created_at)
        remaining = max(60, estimate - elapsed)
        lane = lane_finish_seconds.index(min(lane_finish_seconds))
        lane_finish_seconds[lane] += remaining
    for item in queued_before:
        lane = lane_finish_seconds.index(min(lane_finish_seconds))
        lane_finish_seconds[lane] += _run_estimated_seconds(item)

    ahead_runs = [*running_runs, *queued_before]
    users_ahead = {item.user_id for item in ahead_runs if item.user_id != run.user_id}
    return {
        "status": "queued",
        "queue_position": len(queued_before) + 1,
        "queued_ahead": len(queued_before),
        "running_ahead": len(running_runs),
        "tasks_ahead": len(ahead_runs),
        "users_ahead": len(users_ahead),
        "estimated_wait_seconds": int(min(lane_finish_seconds) if lane_finish_seconds else 0),
        "worker_capacity": worker_capacity,
        "worker_online": worker_online,
        "estimate_card_seconds": QUEUE_CARD_ESTIMATE_SECONDS,
        "calculated_at": utc_iso(utcnow()),
    }


def queue_status(db: Session) -> dict[str, Any]:
    status_counts = dict(db.execute(select(Run.status, func.count()).group_by(Run.status)).all())
    queued = int(status_counts.get("queued") or 0)
    running = int(status_counts.get("running") or 0)
    oldest_queued_at = db.scalar(select(func.min(Run.created_at)).where(Run.status == "queued"))

    workers = db.scalars(
        select(WorkerHeartbeat)
        .order_by(desc(WorkerHeartbeat.updated_at))
        .limit(20)
    ).all()
    active_cutoff = settings.worker_stale_after_seconds

    recent_logs = db.scalars(
        select(RunLog)
        .order_by(desc(RunLog.created_at))
        .limit(30)
    ).all()
    run_ids = {row.run_id for row in recent_logs if row.run_id}
    runs = {
        row.id: row
        for row in db.scalars(select(Run).where(Run.id.in_(run_ids))).all()
    } if run_ids else {}

    return {
        "executor": settings.run_executor,
        "worker_poll_seconds": settings.worker_poll_seconds,
        "worker_stale_after_seconds": settings.worker_stale_after_seconds,
        "user_active_run_limit": settings.user_active_run_limit,
        "counts": status_counts,
        "queued": queued,
        "running": running,
        "active": queued + running,
        "oldest_queued_at": utc_iso(oldest_queued_at),
        "workers": [
            {
                "id": worker.id,
                "hostname": worker.hostname,
                "pid": worker.pid,
                "status": worker.status,
                "current_run_id": worker.current_run_id,
                "started_at": utc_iso(worker.started_at),
                "updated_at": utc_iso(worker.updated_at),
                "age_seconds": _age_seconds(worker.updated_at),
                "active": (_age_seconds(worker.updated_at) or 10**9) <= active_cutoff,
                "meta": worker.meta or {},
            }
            for worker in workers
        ],
        "recent_logs": [
            {
                "id": row.id,
                "run_id": row.run_id,
                "run_problem": runs[row.run_id].problem if row.run_id in runs else None,
                "run_status": runs[row.run_id].status if row.run_id in runs else None,
                "level": row.level,
                "message": row.message,
                "payload": row.payload or {},
                "created_at": utc_iso(row.created_at),
            }
            for row in recent_logs
        ],
    }
