"""Background execution bridge from web runs to the existing WildIdea pipeline."""
from __future__ import annotations

import json
import time
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
        parallel=int(snapshot.get("parallel") or 9),
        target_count=int(snapshot.get("slot_count") or 9),
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


_FAKE_SLOT_POOL = [
    {
        "slot": "D3",
        "domain": "建筑/设计",
        "source": "Pattern language 把反复有效的空间问题写成可复用模式",
        "method": "模式语言拆解法",
    },
    {
        "slot": "D4",
        "domain": "产品体验",
        "source": "Undo Send 给用户短暂撤回窗口，降低误操作带来的心理压力",
        "method": "可撤回缓冲窗口",
    },
    {
        "slot": "D2",
        "domain": "生物系统",
        "source": "免疫记忆会在再次遇到相似抗原时快速启动二次响应",
        "method": "相似触发的记忆响应",
    },
    {
        "slot": "D1",
        "domain": "信息论",
        "source": "纠错码把冗余校验位嵌入信息流，接收端可定位并修复噪声",
        "method": "冗余校验纠错机制",
    },
    {
        "slot": "D3",
        "domain": "舞蹈",
        "source": "Laban effort 用重量、时间、空间、流动四维描述动作质感",
        "method": "动作质感四维编码",
    },
    {
        "slot": "D4",
        "domain": "隐私产品",
        "source": "Locked Folder 把敏感内容从搜索、推荐和共享入口整体隐藏",
        "method": "全路径隔离隐藏",
    },
    {
        "slot": "D2",
        "domain": "结构工程",
        "source": "抗震耗能构件允许指定部位先屈服，把破坏集中到可替换部件",
        "method": "可替换损伤吸收",
    },
    {
        "slot": "D1",
        "domain": "排队系统",
        "source": "令牌桶用固定速率补充令牌，突发请求只能消耗已有令牌",
        "method": "速率令牌配额",
    },
    {
        "slot": "D6",
        "domain": "毛选",
        "source": "路线是个纲，纲举目张",
        "method": "主纲牵引分支",
    },
    {
        "slot": "D7",
        "domain": "随机组词",
        "source": "折叠",
        "method": "折叠展开双态",
    },
]


_FAKE_NAMES = [
    "可撤回灵感缓冲器",
    "问题模式语言库",
    "二次响应推荐卡",
    "冗余校验创意流",
    "动作质感标注器",
    "隐私沙箱工作台",
    "可替换风险吸收层",
    "令牌式请求节流器",
    "主纲牵引生成器",
    "折叠式方案预览",
]


def _fake_slots(target_count: int) -> list[dict]:
    slots: list[dict] = []
    for index in range(max(1, target_count)):
        row = _FAKE_SLOT_POOL[index % len(_FAKE_SLOT_POOL)]
        slots.append({
            "slot_id": f"fake-slot-{index + 1}",
            "slot": row["slot"],
            "domain": row["domain"],
            "source": row["source"],
            "source_phenomenon": row["source"],
            "method": row["method"],
        })
    return slots


def _fake_scores(index: int) -> dict:
    structural = 9 if index % 3 else 8
    distance = 9 + (index % 2)
    novelty = 8 + (index % 3 == 1)
    applicability = 9
    return {
        "structural_depth": structural,
        "domain_distance": distance,
        "applicability": applicability,
        "novelty": novelty,
        "unexpectedness": 8,
        "non_obviousness": 9,
        "raw": "fake judge: frontend smoke data",
    }


def _fake_candidate_payload(run: Run, slot: dict, index: int, total: int) -> dict:
    name = _FAKE_NAMES[(index - 1) % len(_FAKE_NAMES)]
    scores = _fake_scores(index)
    score_values = [
        scores["structural_depth"],
        scores["domain_distance"],
        scores["applicability"],
        scores["novelty"],
    ]
    score_average = sum(score_values) / len(score_values)
    problem = run.problem.strip()
    return {
        "slot_id": slot["slot_id"],
        "index": index,
        "attempt": 1,
        "reroll_count": 0,
        "name": name,
        "slot": slot["slot"],
        "source": slot["method"],
        "proto": f"从“{slot['source']}”抽象出一个可复用动作：先把用户问题拆成可观察状态，再给每个状态配置清晰的反馈与下一步动作。",
        "advantage": "这种方案的优势在于，用户能看懂系统正在做什么，等待过程也会变成有节奏的参与感。",
        "desc": f"围绕“{problem}”搭建一个前端可测试的假数据流程：提交后先展示源现象卡面，随后逐步显示分析、评分和通过状态，最终落成一张完整方案卡。真实上线时，这套结构可替换为模型输出，但交互节奏保持一致。",
        "fail": "如果真实模型输出结构差异过大，fake 数据验证过的排版仍可能在长文本或异常字段下被撑开。",
        "quality_status": "passed",
        "refund_credit": False,
        "quality_note": "",
        "score_average": score_average,
        "scores": scores,
        "search": {
            "quality_status": "passed",
            "refund_credit": False,
            "quality_note": "fake frontend smoke data",
            "score_average": score_average,
            "fallback_attempt": None,
            "max_retries": 3,
        },
        "done": index,
        "total": total,
    }


def _execute_fake_run(db, run: Run, user: User) -> None:
    snapshot = run.config_snapshot or {}
    target_count = max(1, int(snapshot.get("slot_count") or 9))
    duration = max(1.0, float(snapshot.get("fake_run_seconds") or settings.fake_run_seconds or 10))
    slots = _fake_slots(target_count)
    started_at = time.monotonic()

    def emit(event: str, payload: dict | None = None) -> None:
        db.refresh(run)
        if run.status == "deleted":
            return
        safe_payload = _json_safe(payload or {})
        db.add(RunEvent(run_id=run.id, event_type=event, payload=safe_payload))
        if event in {"candidate_ok", "candidate_fallback"}:
            _candidate_from_payload(db, run.id, safe_payload)
        if event in {"slots_done", "candidate_ok", "candidate_fallback", "threshold_rejected", "gen_fail", "judge_fail", "invalid"}:
            add_run_log(
                db,
                run.id,
                "info",
                f"fake {_progress_log_message(event, safe_payload)}",
                _progress_log_payload(event, safe_payload),
            )
        db.commit()

    emit("type", {"value": run.problem_type or detect_type(run.problem)})
    emit("slots_start", {})
    time.sleep(min(0.6, duration * 0.08))
    emit("slots_done", {"count": target_count, "target": target_count, "slots": slots})

    remaining = max(0.1, duration - (time.monotonic() - started_at))
    per_slot = remaining / target_count
    for index, slot in enumerate(slots, 1):
        if run.status == "deleted":
            return
        time.sleep(per_slot * 0.22)
        emit("generating", {
            "slot_id": slot["slot_id"],
            "slot": slot["slot"],
            "domain": slot["domain"],
            "attempt": 1,
        })
        candidate = _fake_candidate_payload(run, slot, index, target_count)
        time.sleep(per_slot * 0.22)
        emit("judging", {
            "slot_id": slot["slot_id"],
            "slot": slot["slot"],
            "name": candidate["name"],
            "attempt": 1,
        })
        time.sleep(per_slot * 0.18)
        emit("judged", {
            "slot_id": slot["slot_id"],
            "slot": slot["slot"],
            "name": candidate["name"],
            "pass": True,
            "sd": candidate["scores"]["structural_depth"],
            "nv": candidate["scores"]["novelty"],
            "ap": candidate["scores"]["applicability"],
            "sd_threshold": 8,
            "novelty_threshold": 8,
            "applicability_threshold": 9,
        })
        time.sleep(per_slot * 0.18)
        emit("candidate_ok", candidate)

    elapsed = time.monotonic() - started_at
    if elapsed < duration:
        time.sleep(duration - elapsed)

    db.refresh(run)
    if run.status == "deleted":
        return
    run.avg_scores = {
        "structural_depth": 8.8,
        "domain_distance": 9.4,
        "novelty": 8.7,
        "applicability": 9.0,
    }
    run.finished_at = utcnow()
    run.status = "succeeded"
    run.error = None
    db.add(RunEvent(run_id=run.id, event_type="status", payload={"status": "succeeded", "fake": True}))
    add_run_log(db, run.id, "info", "fake run succeeded", {"candidate_count": target_count, "seconds": duration})
    db.commit()


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

        if settings.fake_runs:
            _execute_fake_run(db, run, user)
            return

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
