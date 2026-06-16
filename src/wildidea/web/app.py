"""FastAPI application for WildIdea."""
from __future__ import annotations

import json
import re
import secrets
import socket
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
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
    User,
    utcnow,
)
from .observability import add_run_log, queue_status, run_queue_status
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


STATIC_DIR = Path(__file__).parent / "static"


FEEDBACK_LABELS = {
    "useful": "有用",
    "weak": "没用",
    "weak_obscure": "晦涩难懂",
    "weak_off_topic": "不够相关",
    "weak_too_common": "太常规",
    "weak_unusable": "不可落地",
    "weak_other": "其他",
}

DATA_EXPORT_COLUMNS = [
    ("row_type", "数据类型"),
    ("user_email", "用户邮箱"),
    ("user_id", "用户ID"),
    ("run_problem", "任务"),
    ("run_status", "任务状态"),
    ("run_problem_type", "任务类型"),
    ("run_created_at", "任务创建时间"),
    ("run_started_at", "任务开始时间"),
    ("run_finished_at", "任务完成时间"),
    ("run_error", "任务错误"),
    ("run_opt_in_improvement", "允许用于改进"),
    ("slot_count", "槽位数"),
    ("credit_cost", "消耗积分"),
    ("candidate_index", "方案序号"),
    ("candidate_name", "方案名称"),
    ("candidate_slot", "槽位"),
    ("candidate_domain", "领域"),
    ("candidate_reroll_count", "重抽次数"),
    ("candidate_source_phenomenon", "源现象"),
    ("candidate_source", "抽象方法名"),
    ("candidate_proto", "抽象方法"),
    ("candidate_advantage", "优势"),
    ("candidate_desc", "落地方案"),
    ("candidate_fail", "失败边界"),
    ("score_structural_depth", "结构分"),
    ("score_domain_distance", "距离分"),
    ("score_novelty", "新颖分"),
    ("score_applicability", "可用分"),
    ("candidate_search", "搜索数据"),
    ("candidate_created_at", "卡片创建时间"),
    ("has_feedback", "是否有反馈"),
    ("feedback_created_at", "反馈时间"),
    ("label_text", "反馈类型"),
    ("rating", "评分"),
    ("comment", "反馈内容"),
    ("run_config_snapshot", "任务配置"),
    ("run_avg_scores", "任务平均分"),
    ("candidate_id", "候选ID"),
    ("run_id", "任务ID"),
    ("feedback_id", "反馈ID"),
]

EMAIL_BASIC_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)
_RATE_BUCKETS: dict[str, deque[float]] = {}


@asynccontextmanager
async def lifespan(app_: FastAPI):
    init_db()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    recover_interrupted_runs()
    yield


app = FastAPI(title="WildIdea Web", version="1.4", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    return response


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
    search = candidate.search_json or {}
    return {
        "id": candidate.id,
        "index": candidate.index,
        "name": candidate.name,
        "slot": candidate.slot,
        "source": candidate.source,
        "proto": candidate.proto,
        "advantage": candidate.advantage,
        "desc": candidate.desc,
        "fail": candidate.fail,
        "scores": candidate.scores_json or {},
        "search": search,
        "quality_status": search.get("quality_status", "passed"),
        "refund_credit": bool(search.get("refund_credit")),
        "quality_note": search.get("quality_note", ""),
        "score_average": search.get("score_average"),
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
    if db:
        payload["queue"] = run_queue_status(db, run)
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


@app.get("/privacy", include_in_schema=False)
def privacy() -> FileResponse:
    return FileResponse(STATIC_DIR / "privacy.html")


@app.get("/terms", include_in_schema=False)
def terms() -> FileResponse:
    return FileResponse(STATIC_DIR / "terms.html")


@app.get("/design-lab", include_in_schema=False)
def design_lab() -> FileResponse:
    return FileResponse(STATIC_DIR / "design-lab.html")


@app.get("/robots.txt", include_in_schema=False)
def robots_txt() -> Response:
    return Response(
        "User-agent: *\nDisallow: /\n",
        media_type="text/plain; charset=utf-8",
        headers={"X-Robots-Tag": "noindex, nofollow"},
    )


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


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.client.host if request.client else "unknown"


def _rate_limit(key: str, limit: int, window_seconds: int, message: str) -> None:
    if limit <= 0:
        return
    now = time.monotonic()
    bucket = _RATE_BUCKETS.setdefault(key, deque())
    cutoff = now - window_seconds
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        retry_after = max(1, int(window_seconds - (now - bucket[0])))
        raise HTTPException(
            status_code=429,
            detail={"error": "RATE_LIMITED", "message": message, "retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
    bucket.append(now)


def _validate_email_can_receive(email: str) -> None:
    if not EMAIL_BASIC_RE.match(email):
        raise HTTPException(status_code=422, detail={"error": "EMAIL_INVALID", "message": "请输入有效的邮箱地址"})
    domain = email.rsplit("@", 1)[1]
    try:
        domain_ascii = domain.encode("idna").decode("ascii")
        socket.getaddrinfo(domain_ascii, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "EMAIL_DOMAIN_INVALID",
                "message": "邮箱域名无法解析，请检查邮箱地址是否填写正确",
            },
        ) from exc
    except UnicodeError as exc:
        raise HTTPException(status_code=422, detail={"error": "EMAIL_INVALID", "message": "请输入有效的邮箱地址"}) from exc


@app.post("/api/auth/email-code")
def request_email_code(req: EmailCodeRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    email = req.email.strip().lower()
    _validate_email_can_receive(email)
    ip = _client_ip(request)
    _rate_limit(
        f"email-code:ip:{ip}",
        settings.email_code_ip_limit_per_hour,
        3600,
        "验证码请求过于频繁，请稍后再试",
    )
    _rate_limit(
        f"email-code:email:{email}",
        settings.email_code_address_limit_per_hour,
        3600,
        "这个邮箱验证码请求过于频繁，请稍后再试",
    )
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
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    email = req.email.strip().lower()
    ip = _client_ip(request)
    _rate_limit(
        f"login:ip:{ip}",
        settings.login_ip_limit_per_15m,
        900,
        "登录尝试过于频繁，请稍后再试",
    )
    _rate_limit(
        f"login:email:{email}",
        settings.login_address_limit_per_15m,
        900,
        "这个邮箱登录尝试过于频繁，请稍后再试",
    )
    user = db.scalar(select(User).where(User.email == email))
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
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _rate_limit(
        f"run-create:user:{user.id}",
        settings.run_create_user_limit_per_10m,
        600,
        "提交生成任务过于频繁，请稍后再试",
    )
    if req.slot_count > settings.user_run_card_limit:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "USER_CARD_LIMIT_EXCEEDED",
                "message": f"单次最多生成 {settings.user_run_card_limit} 张卡片",
                "requested_cards": req.slot_count,
                "limit": settings.user_run_card_limit,
            },
        )
    if settings.user_active_run_limit > 0:
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
    credit_cost = 0 if user.role == "admin" else req.slot_count * settings.run_credit_cost
    snapshot = {
        "provider": settings.default_provider,
        "model": settings.default_model,
        "judge_model": settings.default_judge_model,
        "base_url": settings.default_base_url,
        "forbid_terms": req.forbid_terms,
        "threshold_reroll": True,
        "max_retries": 3,
        "parallel": min(req.slot_count, settings.user_run_card_limit),
        "slot_count": req.slot_count,
        "credit_cost": credit_cost,
        "opt_in_improvement": user.improvement_consent,
        "fake_runs": settings.fake_runs,
        "fake_run_seconds": settings.fake_run_seconds,
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
            "executor": "fake" if settings.fake_runs else settings.run_executor,
            "credit_cost": credit_cost,
            "slot_count": req.slot_count,
            "user_id": user.id,
        },
    )
    db.commit()
    if settings.run_executor == "worker" and not settings.fake_runs:
        pass
    else:
        background_tasks.add_task(execute_run, run.id)
    return {"run": _run_payload(run, db=db), "credit_balance": user.credit_balance}


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.scalars(
        select(Run)
        .where(Run.user_id == user.id, Run.status != "deleted")
        .order_by(desc(Run.created_at))
        .limit(100)
    ).all()
    return {"runs": [_run_payload(row, db=db) for row in rows]}


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
        queue_tick = 0
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
                if run and run.status == "queued" and not events:
                    queue_tick += 1
                    if queue_tick >= 5:
                        queue_tick = 0
                        payload = {
                            "id": last_id,
                            "event_type": "queue_tick",
                            "payload": {"status": "queued"},
                            "created_at": _utc_iso(utcnow()),
                        }
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail={"error": "CANDIDATE_NOT_FOUND", "message": "候选不存在"})
    run = get_owned_run(db, candidate.run_id, user)

    allowed_labels = {
        "useful",
        "weak_obscure",
        "weak_off_topic",
        "weak_too_common",
        "weak_unusable",
        "weak_other",
    }
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
    db.commit()
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


def _slot_contexts_for_runs(db: Session, run_ids: set[str]) -> dict[str, dict]:
    slot_contexts: dict[str, dict] = {}
    if not run_ids:
        return slot_contexts
    events = db.scalars(
        select(RunEvent)
        .where(
            RunEvent.run_id.in_(run_ids),
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
    return slot_contexts


def _candidate_export_context(slot_contexts: dict[str, dict], candidate: Candidate | None) -> dict:
    if not candidate:
        return {}
    context = slot_contexts.get(candidate.run_id, {})
    slot_id = (context.get("candidate_slots") or {}).get(candidate.name)
    slot = (context.get("slots") or {}).get(slot_id, {})
    return {
        "domain": slot.get("domain") or "",
        "source_phenomenon": slot.get("source_phenomenon") or slot.get("source") or candidate.source,
    }


def _json_export(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _admin_feedback_rows(db: Session, limit: int = 200) -> list[dict]:
    rows = db.scalars(select(Feedback).order_by(desc(Feedback.created_at)).limit(limit)).all()
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
    slot_contexts = _slot_contexts_for_runs(db, set(runs.keys()))

    result = []
    for item in rows:
        candidate = candidates.get(item.candidate_id)
        run = runs.get(candidate.run_id) if candidate else None
        context = _candidate_export_context(slot_contexts, candidate)
        scores = candidate.scores_json if candidate else {}
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
            "candidate_advantage": candidate.advantage if candidate else "",
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
            "created_at": _utc_iso(item.created_at),
        })
    return result


def _admin_card_log_rows(db: Session, page: int, page_size: int) -> dict:
    safe_page = max(1, page)
    safe_page_size = max(1, min(20, page_size))
    total = int(db.scalar(select(func.count()).select_from(Candidate)) or 0)
    candidates = db.scalars(
        select(Candidate)
        .order_by(desc(Candidate.created_at), desc(Candidate.id))
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
    ).all()
    if not candidates:
        return {
            "items": [],
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "total_pages": max(1, (total + safe_page_size - 1) // safe_page_size),
        }

    run_ids = {item.run_id for item in candidates}
    runs = {
        row.id: row
        for row in db.scalars(select(Run).where(Run.id.in_(run_ids))).all()
    }
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_({run.user_id for run in runs.values()}))).all()
    } if runs else {}
    feedback_by_candidate: dict[str, Feedback] = {}
    candidate_ids = {item.id for item in candidates}
    feedback_rows = db.scalars(
        select(Feedback)
        .where(Feedback.candidate_id.in_(candidate_ids))
        .order_by(desc(Feedback.created_at))
    ).all()
    for feedback in feedback_rows:
        feedback_by_candidate.setdefault(feedback.candidate_id, feedback)
    slot_contexts = _slot_contexts_for_runs(db, run_ids)

    items = []
    for candidate in candidates:
        run = runs.get(candidate.run_id)
        user = users.get(run.user_id) if run else None
        feedback = feedback_by_candidate.get(candidate.id)
        context = _candidate_export_context(slot_contexts, candidate)
        search = candidate.search_json or {}
        scores = candidate.scores_json or {}
        items.append({
            "candidate_id": candidate.id,
            "candidate_index": candidate.index,
            "candidate_name": candidate.name,
            "candidate_slot": candidate.slot,
            "candidate_domain": context.get("domain", ""),
            "candidate_source_phenomenon": context.get("source_phenomenon", ""),
            "candidate_source": candidate.source,
            "candidate_advantage": candidate.advantage,
            "candidate_desc": candidate.desc,
            "candidate_reroll_count": candidate.reroll_count or 0,
            "candidate_created_at": _utc_iso(candidate.created_at),
            "quality_status": search.get("quality_status", "passed"),
            "refund_credit": bool(search.get("refund_credit")),
            "score_average": search.get("score_average"),
            "score_applicability": scores.get("applicability"),
            "run_id": candidate.run_id,
            "run_problem": run.problem if run else "",
            "run_status": run.status if run else "",
            "user_email": user.email if user else "",
            "feedback": _feedback_payload(feedback),
            "feedback_label_text": FEEDBACK_LABELS.get(feedback.label or "", feedback.label or "") if feedback else "",
        })
    return {
        "items": items,
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
        "total_pages": max(1, (total + safe_page_size - 1) // safe_page_size),
    }


def _admin_export_rows(db: Session) -> list[dict]:
    runs = db.scalars(select(Run).order_by(desc(Run.created_at), desc(Run.id))).all()
    if not runs:
        return []

    run_ids = {run.id for run in runs}
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_({run.user_id for run in runs}))).all()
    }
    candidates = db.scalars(
        select(Candidate)
        .where(Candidate.run_id.in_(run_ids))
        .order_by(Candidate.run_id, Candidate.index, Candidate.created_at)
    ).all()
    candidates_by_run: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        candidates_by_run.setdefault(candidate.run_id, []).append(candidate)

    feedback_by_candidate: dict[str, Feedback] = {}
    candidate_ids = {candidate.id for candidate in candidates}
    if candidate_ids:
        feedback_rows = db.scalars(
            select(Feedback)
            .where(Feedback.candidate_id.in_(candidate_ids))
            .order_by(desc(Feedback.created_at))
        ).all()
        for feedback in feedback_rows:
            feedback_by_candidate.setdefault(feedback.candidate_id, feedback)

    slot_contexts = _slot_contexts_for_runs(db, run_ids)

    def export_row(run: Run, candidate: Candidate | None, feedback: Feedback | None) -> dict:
        user = users.get(run.user_id)
        scores = candidate.scores_json if candidate else {}
        config = run.config_snapshot or {}
        context = _candidate_export_context(slot_contexts, candidate)
        return {
            "row_type": "卡片" if candidate else "任务",
            "user_email": user.email if user else "",
            "user_id": run.user_id,
            "run_problem": run.problem,
            "run_status": run.status,
            "run_problem_type": run.problem_type or "",
            "run_created_at": _utc_iso(run.created_at),
            "run_started_at": _utc_iso(run.started_at),
            "run_finished_at": _utc_iso(run.finished_at),
            "run_error": run.error or "",
            "run_opt_in_improvement": "是" if run.opt_in_improvement else "否",
            "slot_count": config.get("slot_count", ""),
            "credit_cost": config.get("credit_cost", ""),
            "candidate_index": candidate.index if candidate else "",
            "candidate_name": candidate.name if candidate else "",
            "candidate_slot": candidate.slot if candidate else "",
            "candidate_domain": context.get("domain", ""),
            "candidate_reroll_count": candidate.reroll_count if candidate else "",
            "candidate_source_phenomenon": context.get("source_phenomenon", ""),
            "candidate_source": candidate.source if candidate else "",
            "candidate_proto": candidate.proto if candidate else "",
            "candidate_advantage": candidate.advantage if candidate else "",
            "candidate_desc": candidate.desc if candidate else "",
            "candidate_fail": candidate.fail if candidate else "",
            "score_structural_depth": scores.get("structural_depth", ""),
            "score_domain_distance": scores.get("domain_distance", ""),
            "score_novelty": scores.get("novelty", ""),
            "score_applicability": scores.get("applicability", ""),
            "candidate_search": _json_export(candidate.search_json if candidate else {}),
            "candidate_created_at": _utc_iso(candidate.created_at) if candidate else "",
            "has_feedback": "是" if feedback else "否",
            "feedback_created_at": _utc_iso(feedback.created_at) if feedback else "",
            "label_text": FEEDBACK_LABELS.get(feedback.label or "", feedback.label or "") if feedback else "",
            "rating": feedback.rating if feedback else "",
            "comment": feedback.comment if feedback else "",
            "run_config_snapshot": _json_export(config),
            "run_avg_scores": _json_export(run.avg_scores or {}),
            "candidate_id": candidate.id if candidate else "",
            "run_id": run.id,
            "feedback_id": feedback.id if feedback else "",
        }

    result: list[dict] = []
    for run in runs:
        run_candidates = sorted(candidates_by_run.get(run.id, []), key=lambda item: item.index)
        if not run_candidates:
            result.append(export_row(run, None, None))
            continue
        for candidate in run_candidates:
            result.append(export_row(run, candidate, feedback_by_candidate.get(candidate.id)))
    return result


@app.get("/api/admin/feedback")
def admin_feedback(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> dict:
    rows = _admin_feedback_rows(db)
    audit_admin_action(db, admin, "list_feedback", "feedback", "*")
    db.commit()
    return {"feedback": rows}


@app.get("/api/admin/card-logs")
def admin_card_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=20),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    result = _admin_card_log_rows(db, page=page, page_size=page_size)
    audit_admin_action(db, admin, "list_card_logs", "cards", f"page:{result['page']}")
    db.commit()
    return result


@app.get("/api/admin/feedback.xlsx")
def admin_feedback_excel(db: Session = Depends(get_db), admin: User = Depends(require_admin)) -> Response:
    rows = _admin_export_rows(db)
    headers = [label for _, label in DATA_EXPORT_COLUMNS]
    sheet_rows = [[row.get(key, "") for key, _ in DATA_EXPORT_COLUMNS] for row in rows]
    content = build_xlsx("全量数据", headers, sheet_rows)
    audit_admin_action(db, admin, "export_all_data_excel", "data", "*")
    db.commit()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="wildidea-data.xlsx"'},
    )


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
