"""FastAPI application for WildIdea."""
from __future__ import annotations

import json
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db, init_db
from .emailer import EmailNotConfigured, send_verification_email
from .excel import build_xlsx
from .models import (
    AdminAuditLog,
    Artifact,
    Candidate,
    CreditTransaction,
    EmailVerificationCode,
    Feedback,
    InteractionEvent,
    InviteCode,
    Run,
    RunEvent,
    SyncOutbox,
    User,
    utcnow,
)
from .observability import add_run_log, queue_status
from .runner import execute_run
from .schemas import (
    AdminCreditAdjustmentRequest,
    CreateInviteCodeRequest,
    CreateRunRequest,
    EmailCodeRequest,
    FeedbackRequest,
    InteractionEventRequest,
    LoginRequest,
    RedeemInviteRequest,
    RegisterRequest,
)
from .security import create_access_token, hash_password, verify_password
from .services import (
    add_credit_transaction,
    audit_admin_action,
    charge_run_credit,
    get_current_user,
    get_user_by_access_token,
    get_owned_run,
    grant_signup_bonus,
    normalize_invite_code,
    redeem_invite_code,
    refund_run_credit,
    require_admin,
)
from .sync import dingtalk_sync_status, enqueue_feedback_sync, flush_sync_outbox


STATIC_DIR = Path(__file__).parent / "static"


FEEDBACK_LABELS = {
    "useful": "有用",
    "weak": "没用",
    "weak_obscure": "晦涩难懂",
    "weak_logic": "逻辑混乱",
    "weak_other": "其他",
}

FEEDBACK_EXPORT_COLUMNS = [
    ("created_at", "反馈时间"),
    ("label_text", "反馈类型"),
    ("rating", "评分"),
    ("comment", "反馈内容"),
    ("user_email", "用户邮箱"),
    ("run_problem", "任务"),
    ("run_status", "任务状态"),
    ("run_problem_type", "任务类型"),
    ("candidate_index", "方案序号"),
    ("candidate_name", "方案名称"),
    ("candidate_slot", "槽位"),
    ("candidate_domain", "领域"),
    ("candidate_reroll_count", "重抽次数"),
    ("candidate_source_phenomenon", "源现象"),
    ("candidate_source", "抽象方法名"),
    ("candidate_proto", "抽象方法"),
    ("candidate_desc", "落地方案"),
    ("candidate_fail", "失败边界"),
    ("score_structural_depth", "结构分"),
    ("score_domain_distance", "距离分"),
    ("score_novelty", "新颖分"),
    ("score_applicability", "可用分"),
    ("sync_status", "同步状态"),
    ("sync_error", "同步错误"),
    ("candidate_id", "候选ID"),
    ("run_id", "任务ID"),
    ("id", "反馈ID"),
]


@asynccontextmanager
async def lifespan(app_: FastAPI):
    init_db()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    recover_interrupted_runs()
    yield


app = FastAPI(title="WildIdea Web", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _utc_iso(value: datetime | None) -> str | None:
    """Serialize DB datetimes as explicit UTC so browsers render local time correctly."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def recover_interrupted_runs() -> None:
    if settings.run_executor == "worker":
        return
    db = next(get_db())
    try:
        rows = db.scalars(select(Run).where(Run.status.in_(["queued", "running"]))).all()
        for run in rows:
            user = db.get(User, run.user_id)
            run.status = "failed"
            run.error = "服务重启或任务中断，已自动退回积分"
            run.finished_at = run.finished_at or utcnow()
            if user:
                refund_run_credit(db, user, run, reason="run_interrupted_refund")
            db.add(RunEvent(run_id=run.id, event_type="error", payload={"message": run.error}))
            db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "failed"}))
        db.commit()
    finally:
        db.close()


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "credit_balance": user.credit_balance,
        "improvement_consent": user.improvement_consent,
        "improvement_consent_at": _utc_iso(user.improvement_consent_at),
        "email_verified_at": _utc_iso(user.email_verified_at),
        "created_at": _utc_iso(user.created_at),
    }


def _feedback_payload(feedback: Feedback | None) -> dict | None:
    if not feedback:
        return None
    return {
        "id": feedback.id,
        "rating": feedback.rating,
        "label": feedback.label,
        "comment": feedback.comment,
        "adopted": feedback.adopted,
        "created_at": _utc_iso(feedback.created_at),
    }


def _candidate_payload(candidate: Candidate, feedback: Feedback | None = None) -> dict:
    return {
        "id": candidate.id,
        "index": candidate.index,
        "name": candidate.name,
        "slot": candidate.slot,
        "source": candidate.source,
        "proto": candidate.proto,
        "desc": candidate.desc,
        "fail": candidate.fail,
        "scores": candidate.scores_json or {},
        "search": candidate.search_json or {},
        "reroll_count": candidate.reroll_count or 0,
        "feedback": _feedback_payload(feedback),
    }


def _run_payload(
    run: Run,
    include_candidates: bool = False,
    include_events: bool = False,
    db: Session | None = None,
    viewer_user_id: str | None = None,
) -> dict:
    payload = {
        "id": run.id,
        "user_id": run.user_id,
        "problem": run.problem,
        "problem_type": run.problem_type,
        "status": run.status,
        "config_snapshot": run.config_snapshot or {},
        "opt_in_improvement": run.opt_in_improvement,
        "error": run.error,
        "html_path": run.html_path,
        "avg_scores": run.avg_scores or {},
        "created_at": _utc_iso(run.created_at),
        "started_at": _utc_iso(run.started_at),
        "finished_at": _utc_iso(run.finished_at),
    }
    if include_candidates:
        candidates = sorted(run.candidates, key=lambda item: item.index)
        feedback_by_candidate: dict[str, Feedback] = {}
        if db and viewer_user_id and candidates:
            rows = db.scalars(
                select(Feedback)
                .where(
                    Feedback.user_id == viewer_user_id,
                    Feedback.candidate_id.in_([item.id for item in candidates]),
                )
                .order_by(desc(Feedback.created_at))
            ).all()
            for row in rows:
                feedback_by_candidate.setdefault(row.candidate_id, row)
        payload["candidates"] = [
            _candidate_payload(c, feedback_by_candidate.get(c.id))
            for c in candidates
        ]
    if include_events:
        payload["events"] = [_event_payload(e) for e in sorted(run.events, key=lambda item: item.id)]
    return payload


def _event_payload(event: RunEvent) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "payload": event.payload or {},
        "created_at": _utc_iso(event.created_at),
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.api_route("/favicon.svg", methods=["GET", "HEAD"], include_in_schema=False)
def favicon_svg() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon_ico() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


def _same_timezone_now(value) -> object:
    now = utcnow()
    if value and getattr(value, "tzinfo", None) is None:
        return now.replace(tzinfo=None)
    return now


def _verify_email_code(db: Session, email: str, code: str) -> EmailVerificationCode:
    row = db.scalar(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == "register",
            EmailVerificationCode.consumed_at.is_(None),
        )
        .order_by(desc(EmailVerificationCode.created_at))
    )
    if not row or row.expires_at <= _same_timezone_now(row.expires_at):
        raise HTTPException(status_code=422, detail={"error": "EMAIL_CODE_EXPIRED", "message": "验证码不存在或已过期"})
    if row.attempts >= 5:
        raise HTTPException(status_code=422, detail={"error": "EMAIL_CODE_LOCKED", "message": "验证码错误次数过多，请重新获取"})
    row.attempts += 1
    if not verify_password(code.strip(), row.code_hash):
        db.add(row)
        db.commit()
        raise HTTPException(status_code=422, detail={"error": "EMAIL_CODE_INVALID", "message": "验证码错误"})
    row.consumed_at = utcnow()
    db.add(row)
    return row


@app.post("/api/auth/email-code")
def request_email_code(req: EmailCodeRequest, db: Session = Depends(get_db)) -> dict:
    email = req.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail={"error": "EMAIL_EXISTS", "message": "邮箱已注册"})
    latest = db.scalar(
        select(EmailVerificationCode)
        .where(EmailVerificationCode.email == email, EmailVerificationCode.purpose == "register")
        .order_by(desc(EmailVerificationCode.created_at))
    )
    if latest and latest.created_at + timedelta(seconds=settings.email_code_resend_seconds) > _same_timezone_now(latest.created_at):
        raise HTTPException(status_code=429, detail={"error": "EMAIL_CODE_TOO_FREQUENT", "message": "验证码发送太频繁，请稍后再试"})

    code = f"{secrets.randbelow(1_000_000):06d}"
    row = EmailVerificationCode(
        email=email,
        purpose="register",
        code_hash=hash_password(code),
        expires_at=utcnow() + timedelta(minutes=settings.email_code_ttl_minutes),
    )
    db.add(row)
    try:
        send_verification_email(email, code)
    except EmailNotConfigured as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail={"error": "EMAIL_NOT_CONFIGURED", "message": str(exc)}) from exc
    except Exception as exc:  # noqa: BLE001 - surface mail delivery failures to the user.
        db.rollback()
        raise HTTPException(status_code=502, detail={"error": "EMAIL_SEND_FAILED", "message": f"验证码邮件发送失败：{exc}"}) from exc
    db.commit()
    return {"ok": True, "expires_in_seconds": settings.email_code_ttl_minutes * 60}


@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    email = req.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail={"error": "EMAIL_EXISTS", "message": "邮箱已注册"})
    if not req.opt_in_improvement:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "IMPROVEMENT_CONSENT_REQUIRED",
                "message": "注册需要同意将交互数据用于改进 WildIdea 结果；我们会保护你的隐私，不公开个人身份信息。",
            },
        )
    _verify_email_code(db, email, req.verification_code)
    is_first_user = db.scalar(select(func.count()).select_from(User)) == 0
    now = utcnow()
    user = User(
        email=email,
        password_hash=hash_password(req.password),
        role="admin" if is_first_user else "user",
        improvement_consent=True,
        improvement_consent_at=now,
        email_verified_at=now,
    )
    db.add(user)
    db.flush()
    grant_signup_bonus(db, user)
    if req.invite_code and req.invite_code.strip():
        redeem_invite_code(db, user, req.invite_code)
    db.commit()
    token = create_access_token(user.id)
    return {"access_token": token, "user": _user_payload(user)}


@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == req.email.strip().lower()))
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": "BAD_CREDENTIALS", "message": "邮箱或密码错误"})
    if user.status != "active":
        raise HTTPException(status_code=403, detail={"error": "USER_INACTIVE", "message": "账号不可用"})
    return {"access_token": create_access_token(user.id), "user": _user_payload(user)}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"user": _user_payload(user)}


@app.post("/api/me/invite-code/redeem")
def redeem_invite(req: RedeemInviteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    redemption = redeem_invite_code(db, user, req.code)
    db.commit()
    return {"bonus_credits": redemption.credits_granted, "credit_balance": user.credit_balance}


@app.get("/api/me/credits")
def my_credits(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id)
        .order_by(desc(CreditTransaction.created_at))
        .limit(50)
    ).all()
    return {
        "credit_balance": user.credit_balance,
        "transactions": [
            {
                "id": row.id,
                "amount": row.amount,
                "reason": row.reason,
                "run_id": row.run_id,
                "invite_code_id": row.invite_code_id,
                "metadata": row.meta or {},
                "created_at": _utc_iso(row.created_at),
            }
            for row in rows
        ],
    }


@app.post("/api/runs")
def create_run(
    req: CreateRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    credit_cost = req.slot_count * settings.run_credit_cost
    if settings.run_executor == "worker" and settings.user_active_run_limit > 0:
        active_count = db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.user_id == user.id, Run.status.in_(["queued", "running"]))
        ) or 0
        if active_count >= settings.user_active_run_limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "ACTIVE_RUN_LIMIT_REACHED",
                    "message": "已有任务在排队或生成中，请等当前任务结束后再提交。",
                    "active_runs": active_count,
                    "limit": settings.user_active_run_limit,
                },
            )
    snapshot = {
        "provider": settings.default_provider,
        "model": settings.default_model,
        "judge_model": settings.default_judge_model,
        "base_url": settings.default_base_url,
        "forbid_terms": req.forbid_terms,
        "threshold_reroll": True,
        "max_retries": 3,
        "parallel": 10,
        "slot_count": req.slot_count,
        "credit_cost": credit_cost,
        "opt_in_improvement": user.improvement_consent,
    }
    run = Run(
        user_id=user.id,
        problem=req.problem.strip(),
        status="queued",
        config_snapshot=snapshot,
        opt_in_improvement=user.improvement_consent,
    )
    db.add(run)
    db.flush()
    charge_run_credit(db, user, run.id, amount=credit_cost)
    db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "queued", "credit_cost": credit_cost}))
    add_run_log(
        db,
        run.id,
        "info",
        "run queued",
        {
            "executor": settings.run_executor,
            "credit_cost": credit_cost,
            "slot_count": req.slot_count,
            "user_id": user.id,
        },
    )
    db.commit()
    if settings.run_executor == "worker":
        pass
    else:
        background_tasks.add_task(execute_run, run.id)
    return {"run": _run_payload(run), "credit_balance": user.credit_balance}


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.scalars(
        select(Run)
        .where(Run.user_id == user.id, Run.status != "deleted")
        .order_by(desc(Run.created_at))
        .limit(100)
    ).all()
    return {"runs": [_run_payload(row) for row in rows]}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    run = get_owned_run(db, run_id, user)
    return {"run": _run_payload(run, include_candidates=True, include_events=True, db=db, viewer_user_id=user.id)}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    run = get_owned_run(db, run_id, user)
    run.status = "deleted"
    db.commit()
    return {"ok": True}


@app.get("/api/runs/{run_id}/html")
def get_run_html(run_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    run = get_owned_run(db, run_id, user)
    if not run.html_path:
        raise HTTPException(status_code=404, detail={"error": "RUN_HTML_NOT_FOUND", "message": "结果 HTML 尚未生成"})
    return FileResponse(run.html_path)


def _current_user_from_event_stream_token(db: Session, authorization: Optional[str], token: Optional[str]) -> User:
    if authorization and authorization.lower().startswith("bearer "):
        return get_user_by_access_token(db, authorization.split(" ", 1)[1].strip())
    if token and token.strip():
        return get_user_by_access_token(db, token.strip())
    raise HTTPException(status_code=401, detail={"error": "AUTH_REQUIRED", "message": "请先登录"})


@app.get("/api/runs/{run_id}/events")
def stream_run_events(
    run_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user = _current_user_from_event_stream_token(db, authorization, token)
    get_owned_run(db, run_id, user)

    def event_iter() -> Iterable[str]:
        last_id = 0
        idle_ticks = 0
        while True:
            local_db = next(get_db())
            try:
                run = local_db.get(Run, run_id)
                events = local_db.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.id > last_id)
                    .order_by(RunEvent.id)
                ).all()
                for event in events:
                    last_id = event.id
                    yield f"data: {json.dumps(_event_payload(event), ensure_ascii=False)}\n\n"
                if run and run.status in {"succeeded", "failed", "deleted"} and not events:
                    idle_ticks += 1
                    if idle_ticks >= 2:
                        break
                else:
                    idle_ticks = 0
                time.sleep(1)
            finally:
                local_db.close()

    return StreamingResponse(event_iter(), media_type="text/event-stream")


@app.post("/api/candidates/{candidate_id}/feedback")
def submit_feedback(
    candidate_id: str,
    req: FeedbackRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail={"error": "CANDIDATE_NOT_FOUND", "message": "候选不存在"})
    run = get_owned_run(db, candidate.run_id, user)

    allowed_labels = {"useful", "weak", "weak_obscure", "weak_logic", "weak_other"}
    if req.label not in allowed_labels:
        raise HTTPException(status_code=422, detail={"error": "BAD_FEEDBACK_LABEL", "message": "反馈类型无效"})
    if req.label == "weak_other" and not (req.comment or "").strip():
        raise HTTPException(status_code=422, detail={"error": "FEEDBACK_COMMENT_REQUIRED", "message": "请填写其他原因"})

    existing = db.scalars(
        select(Feedback)
        .where(Feedback.user_id == user.id, Feedback.candidate_id == candidate.id)
        .order_by(desc(Feedback.created_at))
    ).all()
    feedback = existing[0] if existing else Feedback(user_id=user.id, candidate_id=candidate.id)
    for duplicate in existing[1:]:
        db.delete(duplicate)

    is_weak_feedback = req.label != "useful"
    feedback.rating = req.rating if req.rating is not None else (2 if is_weak_feedback else 5)
    feedback.label = req.label
    feedback.comment = req.comment.strip() if req.comment else None
    feedback.adopted = False
    db.add(feedback)
    db.flush()
    db.add(InteractionEvent(
        user_id=user.id,
        run_id=candidate.run_id,
        candidate_id=candidate.id,
        event_type="feedback",
        payload={
            "rating": feedback.rating,
            "label": feedback.label,
            "adopted": feedback.adopted,
            "comment": feedback.comment,
            "mode": "updated" if existing else "created",
        },
    ))
    enqueue_feedback_sync(db, feedback, candidate, run, user)
    db.commit()
    background_tasks.add_task(flush_sync_outbox)
    return {"ok": True, "feedback_id": feedback.id, "feedback": _feedback_payload(feedback)}


@app.post("/api/interaction-events")
def add_interaction_event(
    req: InteractionEventRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if req.run_id:
        get_owned_run(db, req.run_id, user)
    if req.candidate_id:
        candidate = db.get(Candidate, req.candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail={"error": "CANDIDATE_NOT_FOUND", "message": "候选不存在"})
        get_owned_run(db, candidate.run_id, user)
    event = InteractionEvent(
        user_id=user.id,
        run_id=req.run_id,
        candidate_id=req.candidate_id,
        event_type=req.event_type,
        payload=req.payload,
    )
    db.add(event)
    db.commit()
    return {"ok": True, "event_id": event.id}


@app.get("/api/artifacts/{artifact_id}")
def get_artifact(artifact_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FileResponse:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise HTTPException(status_code=404, detail={"error": "ARTIFACT_NOT_FOUND", "message": "文件不存在"})
    get_owned_run(db, artifact.run_id, user)
    return FileResponse(artifact.path)


@app.get("/api/admin/users")
def admin_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    rows = db.scalars(select(User).order_by(desc(User.created_at)).limit(200)).all()
    audit_admin_action(db, admin, "list_users", "users", "*")
    db.commit()
    return {"users": [_user_payload(row) for row in rows]}


@app.get("/api/admin/runs")
def admin_runs(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    rows = db.scalars(select(Run).order_by(desc(Run.created_at)).limit(200)).all()
    audit_admin_action(db, admin, "list_runs", "runs", "*")
    db.commit()
    return {"runs": [_run_payload(row) for row in rows]}


@app.get("/api/admin/metrics")
def admin_metrics(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    status_counts = dict(db.execute(select(Run.status, func.count()).group_by(Run.status)).all())
    users_count = db.scalar(select(func.count()).select_from(User))
    feedback_count = db.scalar(select(func.count()).select_from(Feedback))
    total_credits = db.scalar(select(func.coalesce(func.sum(User.credit_balance), 0)))
    audit_admin_action(db, admin, "view_metrics", "metrics", "*")
    db.commit()
    return {
        "users": users_count,
        "runs_by_status": status_counts,
        "feedback": feedback_count,
        "total_credit_balance": total_credits,
    }


@app.get("/api/admin/queue")
def admin_queue(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    status = queue_status(db)
    audit_admin_action(db, admin, "view_queue_status", "queue", "*")
    db.commit()
    return {"queue": status}


def _admin_feedback_rows(db: Session, limit: int = 200) -> list[dict]:
    rows = db.scalars(select(Feedback).order_by(desc(Feedback.created_at)).limit(limit)).all()
    sync_rows = {
        row.object_id: row
        for row in db.scalars(
            select(SyncOutbox).where(
                SyncOutbox.provider == "dingtalk",
                SyncOutbox.target == "feedback",
                SyncOutbox.object_id.in_({item.id for item in rows}),
            )
        ).all()
    } if rows else {}
    users = {
        row.id: row
        for row in db.scalars(
            select(User).where(User.id.in_({item.user_id for item in rows}))
        ).all()
    } if rows else {}
    candidates = {
        row.id: row
        for row in db.scalars(
            select(Candidate).where(Candidate.id.in_({item.candidate_id for item in rows}))
        ).all()
    } if rows else {}
    runs = {
        row.id: row
        for row in db.scalars(
            select(Run).where(Run.id.in_({item.run_id for item in candidates.values()}))
        ).all()
    } if candidates else {}
    slot_contexts: dict[str, dict] = {}
    if runs:
        events = db.scalars(
            select(RunEvent)
            .where(
                RunEvent.run_id.in_(runs.keys()),
                RunEvent.event_type.in_(["slots_done", "candidate_ok"]),
            )
            .order_by(RunEvent.id)
        ).all()
        for event in events:
            context = slot_contexts.setdefault(event.run_id, {"slots": {}, "candidate_slots": {}})
            payload = event.payload or {}
            if event.event_type == "slots_done":
                for slot in payload.get("slots") or []:
                    slot_id = slot.get("slot_id")
                    if slot_id:
                        context["slots"][slot_id] = slot
            elif event.event_type == "candidate_ok" and payload.get("name") and payload.get("slot_id"):
                context["candidate_slots"][payload["name"]] = payload["slot_id"]

    def candidate_context(candidate: Candidate | None) -> dict:
        if not candidate:
            return {}
        context = slot_contexts.get(candidate.run_id, {})
        slot_id = (context.get("candidate_slots") or {}).get(candidate.name)
        slot = (context.get("slots") or {}).get(slot_id, {})
        return {
            "domain": slot.get("domain") or "",
            "source_phenomenon": slot.get("source_phenomenon") or slot.get("source") or candidate.source,
        }

    result = []
    for item in rows:
        candidate = candidates.get(item.candidate_id)
        run = runs.get(candidate.run_id) if candidate else None
        context = candidate_context(candidate)
        scores = candidate.scores_json if candidate else {}
        sync_row = sync_rows.get(item.id)
        result.append({
            "id": item.id,
            "user_email": users.get(item.user_id).email if users.get(item.user_id) else "",
            "run_id": candidate.run_id if candidate else None,
            "run_problem": run.problem if run else "",
            "run_status": run.status if run else "",
            "run_problem_type": run.problem_type if run else "",
            "candidate_id": item.candidate_id,
            "candidate_index": candidate.index if candidate else None,
            "candidate_name": candidate.name if candidate else "",
            "candidate_slot": candidate.slot if candidate else "",
            "candidate_domain": context.get("domain", ""),
            "candidate_reroll_count": candidate.reroll_count if candidate else 0,
            "candidate_source_phenomenon": context.get("source_phenomenon", ""),
            "candidate_source": candidate.source if candidate else "",
            "candidate_proto": candidate.proto if candidate else "",
            "candidate_desc": candidate.desc if candidate else "",
            "candidate_fail": candidate.fail if candidate else "",
            "candidate_scores": scores,
            "candidate_search": candidate.search_json if candidate else {},
            "candidate_created_at": _utc_iso(candidate.created_at) if candidate else None,
            "score_structural_depth": scores.get("structural_depth"),
            "score_domain_distance": scores.get("domain_distance"),
            "score_novelty": scores.get("novelty"),
            "score_applicability": scores.get("applicability"),
            "label": item.label,
            "label_text": FEEDBACK_LABELS.get(item.label or "", item.label or ""),
            "rating": item.rating,
            "comment": item.comment,
            "sync_status": sync_row.status if sync_row else None,
            "sync_error": sync_row.error if sync_row else None,
            "sync_external_id": sync_row.external_id if sync_row else None,
            "created_at": _utc_iso(item.created_at),
        })
    return result


@app.get("/api/admin/feedback")
def admin_feedback(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    rows = _admin_feedback_rows(db)
    audit_admin_action(db, admin, "list_feedback", "feedback", "*")
    db.commit()
    return {"feedback": rows}


@app.get("/api/admin/feedback.xlsx")
def admin_feedback_excel(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> Response:
    rows = _admin_feedback_rows(db, limit=5000)
    headers = [label for _, label in FEEDBACK_EXPORT_COLUMNS]
    sheet_rows = [[row.get(key, "") for key, _ in FEEDBACK_EXPORT_COLUMNS] for row in rows]
    content = build_xlsx("反馈数据", headers, sheet_rows)
    audit_admin_action(db, admin, "export_feedback_excel", "feedback", "*")
    db.commit()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="wildidea-feedback.xlsx"'},
    )


@app.get("/api/admin/sync")
def admin_sync_status(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    audit_admin_action(db, admin, "view_sync_status", "sync", "dingtalk")
    status = dingtalk_sync_status(db)
    db.commit()
    return {"sync": status}


@app.post("/api/admin/sync/flush")
def admin_flush_sync(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    audit_admin_action(db, admin, "flush_sync", "sync", "dingtalk")
    db.commit()
    result = flush_sync_outbox()
    status_db = next(get_db())
    try:
        status = dingtalk_sync_status(status_db)
    finally:
        status_db.close()
    return {"ok": True, "result": result, "sync": status}


@app.get("/api/admin/invite-codes")
def admin_invite_codes(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    rows = db.scalars(select(InviteCode).order_by(desc(InviteCode.created_at)).limit(200)).all()
    return {
        "invite_codes": [
            {
                "id": row.id,
                "code": row.code,
                "bonus_credits": row.bonus_credits,
                "max_redemptions": row.max_redemptions,
                "redeemed_count": row.redeemed_count,
                "expires_at": _utc_iso(row.expires_at),
                "status": row.status,
                "created_at": _utc_iso(row.created_at),
            }
            for row in rows
        ]
    }


@app.post("/api/admin/invite-codes")
def admin_create_invite_code(
    req: CreateInviteCodeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    code = normalize_invite_code(req.code or secrets.token_urlsafe(8))
    if db.scalar(select(InviteCode).where(InviteCode.code == code)):
        raise HTTPException(status_code=409, detail={"error": "INVITE_CODE_EXISTS", "message": "邀请码已存在"})
    invite = InviteCode(
        code=code,
        bonus_credits=req.bonus_credits,
        max_redemptions=req.max_redemptions,
        expires_at=req.expires_at,
        created_by_admin_id=admin.id,
    )
    db.add(invite)
    audit_admin_action(db, admin, "create_invite_code", "invite_code", code)
    db.commit()
    return {"invite_code": {"id": invite.id, "code": invite.code, "bonus_credits": invite.bonus_credits}}


@app.post("/api/admin/invite-codes/{invite_code_id}/disable")
def admin_disable_invite_code(invite_code_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    invite = db.get(InviteCode, invite_code_id)
    if not invite:
        raise HTTPException(status_code=404, detail={"error": "INVITE_CODE_NOT_FOUND", "message": "邀请码不存在"})
    invite.status = "disabled"
    audit_admin_action(db, admin, "disable_invite_code", "invite_code", invite.id)
    db.commit()
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/credits")
def admin_adjust_credits(
    user_id: str,
    req: AdminCreditAdjustmentRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail={"error": "USER_NOT_FOUND", "message": "用户不存在"})
    add_credit_transaction(db, target, req.amount, "admin_adjustment", meta={"reason": req.reason, "admin_id": admin.id})
    audit_admin_action(db, admin, "adjust_credits", "user", user_id, req.reason)
    db.commit()
    return {"user": _user_payload(target)}


@app.get("/api/admin/audit-logs")
def admin_audit_logs(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    rows = db.scalars(select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at)).limit(200)).all()
    return {
        "audit_logs": [
            {
                "id": row.id,
                "admin_user_id": row.admin_user_id,
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "reason": row.reason,
                "created_at": _utc_iso(row.created_at),
            }
            for row in rows
        ]
    }


def main() -> None:
    uvicorn.run("wildidea.web.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
