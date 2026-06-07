"""Queue worker for running WildIdea generation jobs outside the API process."""
from __future__ import annotations

import argparse
import logging
import os
import socket
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, init_db
from .models import Run, RunEvent, User, WorkerHeartbeat, utcnow
from .observability import active_run_card_count, add_run_log, run_slot_count
from .runner import execute_run
from .services import refund_run_credit


logger = logging.getLogger(__name__)


def worker_identity(explicit: str | None = None) -> str:
    return explicit or settings.worker_id or f"{socket.gethostname()}:{os.getpid()}"


def update_worker_heartbeat(
    db: Session,
    worker_id: str,
    status: str,
    current_run_id: str | None = None,
    meta: dict | None = None,
) -> WorkerHeartbeat:
    now = utcnow()
    heartbeat = db.get(WorkerHeartbeat, worker_id)
    if not heartbeat:
        heartbeat = WorkerHeartbeat(
            id=worker_id,
            hostname=socket.gethostname(),
            pid=os.getpid(),
            started_at=now,
        )
    heartbeat.hostname = socket.gethostname()
    heartbeat.pid = os.getpid()
    heartbeat.status = status
    heartbeat.current_run_id = current_run_id
    heartbeat.updated_at = now
    heartbeat.meta = meta or {}
    db.add(heartbeat)
    return heartbeat


def recover_stale_worker_runs(db: Session, worker_id: str) -> int:
    """Fail and refund old running jobs that no active worker still owns."""
    cutoff = utcnow() - timedelta(seconds=settings.worker_stale_after_seconds)
    active_heartbeats = db.scalars(
        select(WorkerHeartbeat)
        .where(WorkerHeartbeat.updated_at >= cutoff)
    ).all()
    active_run_ids: set[str] = set()
    for heartbeat in active_heartbeats:
        if heartbeat.current_run_id:
            active_run_ids.add(heartbeat.current_run_id)
        for run_id in (heartbeat.meta or {}).get("active_run_ids") or []:
            if run_id:
                active_run_ids.add(str(run_id))

    query = select(Run).where(
        Run.status == "running",
        or_(Run.started_at.is_(None), Run.started_at < cutoff),
    )
    if active_run_ids:
        query = query.where(Run.id.not_in(active_run_ids))
    stale_runs = db.scalars(query).all()

    recovered = 0
    for run in stale_runs:
        user = db.get(User, run.user_id)
        run.status = "failed"
        run.error = "worker 长时间未上报心跳，任务已自动退回积分"
        run.finished_at = run.finished_at or utcnow()
        if user:
            refund_run_credit(db, user, run, reason="run_worker_stale_refund")
        db.add(RunEvent(run_id=run.id, event_type="error", payload={"message": run.error}))
        db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "failed"}))
        add_run_log(
            db,
            run.id,
            "warning",
            "stale running run recovered",
            {"worker_id": worker_id, "cutoff_seconds": settings.worker_stale_after_seconds},
        )
        recovered += 1
    return recovered


def claim_next_run(db: Session, worker_id: str, *, update_idle: bool = True) -> tuple[str, int] | None:
    run = db.scalar(
        select(Run)
        .where(Run.status == "queued")
        .order_by(Run.created_at, Run.id)
        .limit(1)
    )
    if not run:
        if update_idle:
            update_worker_heartbeat(db, worker_id, "idle", meta={"card_capacity": settings.run_card_capacity})
        return None

    requested_cards = run_slot_count(run)
    running_cards = active_run_card_count(db)
    card_capacity = max(1, settings.run_card_capacity)
    if running_cards + requested_cards > card_capacity:
        if update_idle:
            update_worker_heartbeat(
                db,
                worker_id,
                "capacity_wait",
                meta={
                    "running_cards": running_cards,
                    "next_run_cards": requested_cards,
                    "card_capacity": card_capacity,
                    "next_run_id": run.id,
                },
            )
        return None

    now = utcnow()
    result = db.execute(
        update(Run)
        .where(Run.id == run.id, Run.status == "queued")
        .values(status="running", started_at=now, error=None)
    )
    if result.rowcount != 1:
        db.rollback()
        return None

    update_worker_heartbeat(db, worker_id, "running", current_run_id=run.id)
    db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "running", "worker_id": worker_id}))
    add_run_log(
        db,
        run.id,
        "info",
        "worker claimed run",
        {
            "worker_id": worker_id,
            "slot_count": requested_cards,
            "running_cards_before_claim": running_cards,
            "card_capacity": card_capacity,
        },
    )
    return run.id, requested_cards


def mark_worker_exception(run_id: str, worker_id: str, exc: Exception) -> None:
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if run and run.status == "running":
            user = db.get(User, run.user_id)
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = utcnow()
            if user:
                refund_run_credit(db, user, run, reason="run_worker_exception_refund")
            db.add(RunEvent(run_id=run.id, event_type="error", payload={"message": str(exc)}))
            db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "failed"}))
        add_run_log(db, run_id, "error", "worker exception", {"worker_id": worker_id, "error": str(exc)})
        db.commit()
    finally:
        db.close()


def _execute_claimed_run(run_id: str, worker_id: str) -> None:
    logger.info("worker %s running %s", worker_id, run_id)
    try:
        execute_run(run_id)
    except Exception as exc:  # noqa: BLE001 - keep the worker alive across task failures.
        logger.exception("worker %s failed run %s", worker_id, run_id)
        mark_worker_exception(run_id, worker_id, exc)


def _release_claimed_run(run_id: str, worker_id: str) -> None:
    db = SessionLocal()
    try:
        add_run_log(db, run_id, "info", "worker released run", {"worker_id": worker_id})
        db.commit()
    finally:
        db.close()


def _update_worker_pool_heartbeat(worker_id: str, active_runs: dict[Future, tuple[str, int]]) -> None:
    db = SessionLocal()
    try:
        active_run_ids = [run_id for run_id, _cards in active_runs.values()]
        active_cards = sum(cards for _run_id, cards in active_runs.values())
        update_worker_heartbeat(
            db,
            worker_id,
            "running" if active_runs else "idle",
            current_run_id=active_run_ids[0] if active_run_ids else None,
            meta={
                "active_run_ids": active_run_ids,
                "active_run_count": len(active_run_ids),
                "active_cards": active_cards,
                "card_capacity": settings.run_card_capacity,
            },
        )
        db.commit()
    finally:
        db.close()


def run_worker_once(worker_id: str | None = None) -> bool:
    identity = worker_identity(worker_id)
    db = SessionLocal()
    try:
        recovered = recover_stale_worker_runs(db, identity)
        claimed = claim_next_run(db, identity)
        db.commit()
    finally:
        db.close()

    if not claimed:
        return False

    run_id, _cards = claimed
    try:
        _execute_claimed_run(run_id, identity)
    finally:
        db = SessionLocal()
        try:
            update_worker_heartbeat(db, identity, "idle")
            add_run_log(db, run_id, "info", "worker released run", {"worker_id": identity})
            db.commit()
        finally:
            db.close()
    if recovered:
        logger.warning("worker %s recovered %s stale runs", identity, recovered)
    return True


def run_worker_forever(worker_id: str | None = None, poll_seconds: float | None = None) -> None:
    init_db()
    identity = worker_identity(worker_id)
    poll = poll_seconds if poll_seconds is not None else settings.worker_poll_seconds
    last_idle_log = 0.0
    max_workers = max(1, settings.run_card_capacity)
    logger.info(
        "WildIdea worker %s started; poll=%ss card_capacity=%s",
        identity,
        poll,
        settings.run_card_capacity,
    )
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="wildidea-run") as pool:
        active_runs: dict[Future, tuple[str, int]] = {}
        while True:
            finished = [future for future in active_runs if future.done()]
            for future in finished:
                run_id, _cards = active_runs.pop(future)
                _release_claimed_run(run_id, identity)
                if future.exception():
                    logger.error("worker %s run %s ended with exception", identity, run_id)
            if finished:
                _update_worker_pool_heartbeat(identity, active_runs)

            claimed_any = False
            while sum(cards for _run_id, cards in active_runs.values()) < max(1, settings.run_card_capacity):
                db = SessionLocal()
                try:
                    recovered = recover_stale_worker_runs(db, identity)
                    claimed = claim_next_run(db, identity, update_idle=False)
                    db.commit()
                finally:
                    db.close()
                if not claimed:
                    if recovered:
                        logger.warning("worker %s recovered %s stale runs", identity, recovered)
                    break
                run_id, cards = claimed
                future = pool.submit(_execute_claimed_run, run_id, identity)
                active_runs[future] = (run_id, cards)
                claimed_any = True
                _update_worker_pool_heartbeat(identity, active_runs)

            if active_runs:
                wait(active_runs.keys(), timeout=max(0.5, poll), return_when=FIRST_COMPLETED)
                continue

            db = SessionLocal()
            try:
                update_worker_heartbeat(db, identity, "idle", meta={"card_capacity": settings.run_card_capacity})
                db.commit()
            finally:
                db.close()
            now = time.monotonic()
            if now - last_idle_log >= settings.worker_idle_log_seconds:
                logger.info("worker %s idle", identity)
                last_idle_log = now
            if not claimed_any:
                time.sleep(max(0.5, poll))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the WildIdea queue worker.")
    parser.add_argument("--once", action="store_true", help="Run at most one queued job and exit.")
    parser.add_argument("--worker-id", default=None, help="Stable worker id for monitoring.")
    parser.add_argument("--poll-seconds", type=float, default=None, help="Queue polling interval.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    if args.once:
        run_worker_once(args.worker_id)
    else:
        run_worker_forever(args.worker_id, args.poll_seconds)


if __name__ == "__main__":
    main()
