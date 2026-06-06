"""Best-effort outbound sync for external tables."""
from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .models import Candidate, Feedback, Run, SyncOutbox, User, utcnow


PROVIDER_DINGTALK = "dingtalk"
TARGET_FEEDBACK = "feedback"

DEFAULT_FEEDBACK_FIELD_MAP = {
    "feedback_id": "反馈ID",
    "feedback_type": "反馈类型",
    "rating": "评分",
    "comment": "反馈内容",
    "user_email": "用户邮箱",
    "problem": "任务",
    "run_status": "任务状态",
    "candidate_name": "方案名称",
    "candidate_index": "方案序号",
    "slot": "槽位",
    "domain": "领域",
    "reroll_count": "重抽次数",
    "source_phenomenon": "源现象",
    "source": "抽象方法名",
    "proto": "抽象方法",
    "desc": "落地方案",
    "fail": "失败边界",
    "candidate_id": "候选ID",
    "run_id": "任务ID",
    "created_at": "反馈时间",
}

FEEDBACK_LABELS = {
    "useful": "有用",
    "weak": "没用",
    "weak_obscure": "晦涩难懂",
    "weak_logic": "逻辑混乱",
    "weak_other": "其他",
}


class DingtalkError(RuntimeError):
    """Raised when DingTalk rejects a sync request."""


def dingtalk_sync_enabled() -> bool:
    return settings.dingtalk_sync_enabled


def dingtalk_feedback_configured() -> bool:
    required = [
        settings.dingtalk_app_key,
        settings.dingtalk_app_secret,
        settings.dingtalk_operator_id,
        settings.dingtalk_ai_table_base_id,
        settings.dingtalk_feedback_sheet_id,
    ]
    return dingtalk_sync_enabled() and all((item or "").strip() for item in required)


def _field_map() -> dict[str, str]:
    field_map = dict(DEFAULT_FEEDBACK_FIELD_MAP)
    if not settings.dingtalk_feedback_field_map.strip():
        return field_map
    try:
        custom = json.loads(settings.dingtalk_feedback_field_map)
    except json.JSONDecodeError:
        return field_map
    if isinstance(custom, dict):
        field_map.update({str(key): str(value) for key, value in custom.items() if value})
    return field_map


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _slot_context(candidate: Candidate, run: Run) -> dict[str, str]:
    slots: dict[str, dict] = {}
    candidate_slots: dict[str, str] = {}
    for event in sorted(run.events, key=lambda item: item.id):
        payload = event.payload or {}
        if event.event_type == "slots_done":
            for slot in payload.get("slots") or []:
                slot_id = slot.get("slot_id")
                if slot_id:
                    slots[slot_id] = slot
        elif event.event_type == "candidate_ok" and payload.get("name") and payload.get("slot_id"):
            candidate_slots[payload["name"]] = payload["slot_id"]
    slot = slots.get(candidate_slots.get(candidate.name, ""), {})
    return {
        "domain": slot.get("domain") or "",
        "source_phenomenon": slot.get("source_phenomenon") or slot.get("source") or candidate.source,
    }


def _feedback_fields(feedback: Feedback, candidate: Candidate, run: Run, user: User) -> dict[str, Any]:
    slot_context = _slot_context(candidate, run)
    raw = {
        "feedback_id": feedback.id,
        "feedback_type": FEEDBACK_LABELS.get(feedback.label or "", feedback.label or ""),
        "rating": feedback.rating,
        "comment": _text(feedback.comment),
        "user_email": user.email,
        "problem": run.problem,
        "run_status": run.status,
        "candidate_name": candidate.name,
        "candidate_index": candidate.index,
        "slot": candidate.slot,
        "domain": slot_context["domain"],
        "reroll_count": candidate.reroll_count or 0,
        "source_phenomenon": slot_context["source_phenomenon"],
        "source": candidate.source,
        "proto": candidate.proto,
        "desc": candidate.desc,
        "fail": candidate.fail,
        "candidate_id": candidate.id,
        "run_id": run.id,
        "created_at": feedback.created_at.isoformat(),
    }
    field_map = _field_map()
    return {field_map.get(key, key): value for key, value in raw.items() if value is not None}


def enqueue_feedback_sync(db: Session, feedback: Feedback, candidate: Candidate, run: Run, user: User) -> SyncOutbox | None:
    if not dingtalk_sync_enabled():
        return None
    payload = {
        "fields": _feedback_fields(feedback, candidate, run, user),
        "feedback_id": feedback.id,
    }
    row = db.scalar(
        select(SyncOutbox).where(
            SyncOutbox.provider == PROVIDER_DINGTALK,
            SyncOutbox.target == TARGET_FEEDBACK,
            SyncOutbox.object_type == "feedback",
            SyncOutbox.object_id == feedback.id,
        )
    )
    now = utcnow()
    if row:
        row.payload = payload
        row.status = "pending"
        row.error = None
        row.updated_at = now
    else:
        row = SyncOutbox(
            provider=PROVIDER_DINGTALK,
            target=TARGET_FEEDBACK,
            object_type="feedback",
            object_id=feedback.id,
            payload=payload,
            status="pending",
            updated_at=now,
        )
        db.add(row)
    return row


class DingtalkClient:
    def __init__(self) -> None:
        self.base_url = settings.dingtalk_api_base_url.rstrip("/")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None, token: str | None = None) -> dict:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["x-acs-dingtalk-access-token"] = token
        req = request.Request(f"{self.base_url}{path}", data=payload, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=settings.dingtalk_timeout_seconds) as response:
                text = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise DingtalkError(f"HTTP {exc.code}: {detail[:800]}") from exc
        except error.URLError as exc:
            raise DingtalkError(str(exc.reason)) from exc
        if not text:
            return {}
        data = json.loads(text)
        if isinstance(data, dict):
            error_code = data.get("errcode") or data.get("code")
            if error_code not in (None, 0, "0"):
                message = data.get("errmsg") or data.get("message") or data
                raise DingtalkError(str(message))
        return data

    def access_token(self) -> str:
        data = self._request(
            "POST",
            "/v1.0/oauth2/accessToken",
            {
                "appKey": settings.dingtalk_app_key,
                "appSecret": settings.dingtalk_app_secret,
            },
        )
        token = data.get("accessToken")
        if not token:
            raise DingtalkError("DingTalk access token response has no accessToken")
        return str(token)

    def _records_path(self) -> str:
        base_id = parse.quote(settings.dingtalk_ai_table_base_id or "", safe="")
        sheet_id = parse.quote(settings.dingtalk_feedback_sheet_id or "", safe="")
        query = parse.urlencode({"operatorId": settings.dingtalk_operator_id or ""})
        return f"/v1.0/notable/bases/{base_id}/sheets/{sheet_id}/records?{query}"

    def create_feedback_record(self, fields: dict[str, Any]) -> str | None:
        data = self._request("POST", self._records_path(), {"records": [{"fields": fields}]}, token=self.access_token())
        records = data.get("value") or data.get("records") or []
        if records and isinstance(records[0], dict):
            return records[0].get("id")
        return None

    def update_feedback_record(self, record_id: str, fields: dict[str, Any]) -> str | None:
        data = self._request(
            "PUT",
            self._records_path(),
            {"records": [{"id": record_id, "fields": fields}]},
            token=self.access_token(),
        )
        records = data.get("value") or data.get("records") or []
        if records and isinstance(records[0], dict):
            return records[0].get("id") or record_id
        return record_id


def flush_sync_outbox(limit: int | None = None) -> dict[str, Any]:
    if not dingtalk_sync_enabled():
        return {"synced": 0, "failed": 0, "skipped": True, "reason": "disabled"}
    if not dingtalk_feedback_configured():
        return {"synced": 0, "failed": 0, "skipped": True, "reason": "not_configured"}

    client = DingtalkClient()
    batch_size = limit or settings.dingtalk_sync_batch_size
    synced = 0
    failed = 0
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(SyncOutbox)
            .where(
                SyncOutbox.provider == PROVIDER_DINGTALK,
                SyncOutbox.target == TARGET_FEEDBACK,
                SyncOutbox.status.in_(["pending", "failed"]),
            )
            .order_by(SyncOutbox.created_at)
            .limit(batch_size)
        ).all()
        for row in rows:
            row.attempts += 1
            row.updated_at = utcnow()
            try:
                fields = (row.payload or {}).get("fields") or {}
                if row.external_id:
                    record_id = client.update_feedback_record(row.external_id, fields)
                else:
                    record_id = client.create_feedback_record(fields)
                row.external_id = record_id or row.external_id
                row.status = "synced"
                row.error = None
                row.synced_at = utcnow()
                synced += 1
            except Exception as exc:  # noqa: BLE001 - keep sync failures out of user flow.
                row.status = "failed"
                row.error = str(exc)[:2000]
                failed += 1
            db.commit()
    finally:
        db.close()
    return {"synced": synced, "failed": failed, "skipped": False}


def dingtalk_sync_status(db: Session) -> dict[str, Any]:
    counts = {
        status: count
        for status, count in db.execute(
            select(SyncOutbox.status, func.count())
            .where(SyncOutbox.provider == PROVIDER_DINGTALK, SyncOutbox.target == TARGET_FEEDBACK)
            .group_by(SyncOutbox.status)
        ).all()
    }
    latest_failed = db.scalar(
        select(SyncOutbox)
        .where(
            SyncOutbox.provider == PROVIDER_DINGTALK,
            SyncOutbox.target == TARGET_FEEDBACK,
            SyncOutbox.status == "failed",
        )
        .order_by(desc(SyncOutbox.updated_at))
    )
    return {
        "provider": PROVIDER_DINGTALK,
        "enabled": dingtalk_sync_enabled(),
        "configured": dingtalk_feedback_configured(),
        "target": TARGET_FEEDBACK,
        "base_id": settings.dingtalk_ai_table_base_id or "",
        "sheet_id": settings.dingtalk_feedback_sheet_id or "",
        "counts": {
            "pending": counts.get("pending", 0),
            "synced": counts.get("synced", 0),
            "failed": counts.get("failed", 0),
        },
        "last_error": latest_failed.error if latest_failed else None,
    }
