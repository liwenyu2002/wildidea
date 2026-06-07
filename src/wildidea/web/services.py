"""Domain services for credits, invite codes, auth dependencies, and run ownership."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import (
    AdminAuditLog,
    CreditTransaction,
    InviteCode,
    InviteRedemption,
    Run,
    User,
)
from .security import decode_access_token


def normalize_invite_code(code: str) -> str:
    return code.strip().upper()


def add_credit_transaction(
    db: Session,
    user: User,
    amount: int,
    reason: str,
    run_id: Optional[str] = None,
    invite_code_id: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
) -> CreditTransaction:
    user.credit_balance += amount
    tx = CreditTransaction(
        user_id=user.id,
        amount=amount,
        reason=reason,
        run_id=run_id,
        invite_code_id=invite_code_id,
        meta=meta or {},
    )
    db.add(tx)
    return tx


def grant_signup_bonus(db: Session, user: User) -> None:
    add_credit_transaction(db, user, settings.signup_bonus_credits, "signup_bonus")


def charge_run_credit(db: Session, user: User, run_id: str, amount: int) -> None:
    if user.role == "admin" or amount <= 0:
        return
    if user.credit_balance < amount:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "INSUFFICIENT_CREDITS",
                "message": "积分不足，无法生成",
                "credit_balance": user.credit_balance,
                "required_credits": amount,
            },
        )
    add_credit_transaction(db, user, -amount, "run_charge", run_id=run_id)


def refund_run_credit(db: Session, user: User, run: Run, reason: str = "run_refund") -> None:
    if run.credits_refunded:
        return
    if user.role == "admin":
        run.credits_refunded = True
        return
    raw_amount = (run.config_snapshot or {}).get("credit_cost")
    amount = int(settings.run_credit_cost if raw_amount is None else raw_amount)
    if amount <= 0:
        run.credits_refunded = True
        return
    add_credit_transaction(db, user, amount, reason, run_id=run.id)
    run.credits_refunded = True


def redeem_invite_code(db: Session, user: User, raw_code: str) -> InviteRedemption:
    code = normalize_invite_code(raw_code)
    invite = db.scalar(select(InviteCode).where(InviteCode.code == code))
    if not invite:
        raise HTTPException(status_code=404, detail={"error": "INVALID_INVITE_CODE", "message": "邀请码不存在"})
    if invite.status != "active":
        raise HTTPException(status_code=400, detail={"error": "INVITE_CODE_DISABLED", "message": "邀请码已禁用"})
    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail={"error": "INVITE_CODE_EXPIRED", "message": "邀请码已过期"})
    if invite.max_redemptions is not None and invite.redeemed_count >= invite.max_redemptions:
        raise HTTPException(status_code=400, detail={"error": "INVITE_CODE_FULLY_REDEEMED", "message": "邀请码名额已满"})

    used = db.scalar(select(InviteRedemption).where(InviteRedemption.user_id == user.id))
    if used:
        raise HTTPException(status_code=400, detail={"error": "USER_ALREADY_REDEEMED_INVITE", "message": "你已经兑换过邀请码"})

    redemption = InviteRedemption(invite_code_id=invite.id, user_id=user.id, credits_granted=invite.bonus_credits)
    invite.redeemed_count += 1
    add_credit_transaction(db, user, invite.bonus_credits, "invite_bonus", invite_code_id=invite.id)
    db.add(redemption)
    return redemption


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": "AUTH_REQUIRED", "message": "请先登录"})
    token = authorization.split(" ", 1)[1].strip()
    return get_user_by_access_token(db, token)


def get_user_by_access_token(db: Session, token: str) -> User:
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail={"error": "INVALID_TOKEN", "message": "登录已失效，请重新登录"})
    user = db.get(User, payload.get("sub"))
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail={"error": "USER_INACTIVE", "message": "账号不可用"})
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail={"error": "ADMIN_REQUIRED", "message": "需要管理员权限"})
    return user


def get_owned_run(db: Session, run_id: str, user: User) -> Run:
    run = db.get(Run, run_id)
    if not run or run.status == "deleted":
        raise HTTPException(status_code=404, detail={"error": "RUN_NOT_FOUND", "message": "任务不存在"})
    if user.role != "admin" and run.user_id != user.id:
        raise HTTPException(status_code=403, detail={"error": "RUN_FORBIDDEN", "message": "不能查看其他用户的任务"})
    return run


def audit_admin_action(db: Session, admin: User, action: str, target_type: str, target_id: str, reason: Optional[str] = None) -> None:
    db.add(AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
    ))
