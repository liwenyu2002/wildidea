"""Web API tests for auth, invite codes, and credits."""
from __future__ import annotations

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

os.environ["WILDIDEA_DATABASE_URL"] = "sqlite:////tmp/wildidea-test-web.db"
Path("/tmp/wildidea-test-web.db").unlink(missing_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

import wildidea.web.app as webapp  # noqa: E402
from wildidea.web.emailer import _build_verification_message  # noqa: E402


def request_email_code(client: TestClient, email: str) -> str:
    sent: dict[str, str] = {}
    original = webapp.send_verification_email

    def fake_send(target_email: str, code: str) -> None:
        sent[target_email] = code

    webapp.send_verification_email = fake_send
    try:
        response = client.post("/api/auth/email-code", json={"email": email})
    finally:
        webapp.send_verification_email = original
    assert response.status_code == 200, response.text
    return sent[email]


def register_user(client: TestClient, email: str, password: str = "secret12", **extra):
    code = request_email_code(client, email)
    payload = {"email": email, "password": password, "verification_code": code, "opt_in_improvement": True}
    payload.update(extra)
    return client.post("/api/auth/register", json=payload)


def test_verification_email_has_html_and_plaintext_parts():
    message = _build_verification_message("new-user@example.com", "123456", "no-reply@example.com")

    assert message.is_multipart()
    assert message["Subject"] == "WildIdea 注册验证码"
    assert message["To"] == "new-user@example.com"
    assert message["Date"]
    assert message["Message-ID"]
    plain = message.get_body(preferencelist=("plain",))
    html = message.get_body(preferencelist=("html",))
    assert plain is not None
    assert html is not None
    assert "你的 WildIdea 注册验证码是：123456" in plain.get_content()
    html_content = html.get_content()
    assert "WildIdea" in html_content
    assert "邮箱验证" in html_content
    assert "123456" in html_content
    assert "分钟内有效" in html_content


def test_homepage_exposes_favicon():
    with TestClient(webapp.app) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "/static/favicon.svg" in home.text

        favicon = client.get("/favicon.ico")
        assert favicon.status_code == 200
        assert "image/svg+xml" in favicon.headers["content-type"]
        assert b"WildIdea" in favicon.content

        favicon_head = client.head("/favicon.ico")
        assert favicon_head.status_code == 200


def test_register_invite_redeem_and_run_charge():
    webapp.execute_run = lambda run_id: None

    with TestClient(webapp.app) as client:
        admin_resp = register_user(client, "admin@example.com")
        assert admin_resp.status_code == 200
        assert admin_resp.json()["user"]["role"] == "admin"
        assert admin_resp.json()["user"]["credit_balance"] == 30
        assert admin_resp.json()["user"]["improvement_consent"] is True
        assert admin_resp.json()["user"]["improvement_consent_at"]
        admin_headers = {"Authorization": f"Bearer {admin_resp.json()['access_token']}"}

        invite_resp = client.post(
            "/api/admin/invite-codes",
            headers=admin_headers,
            json={"code": "MORE20", "bonus_credits": 20, "max_redemptions": 10},
        )
        assert invite_resp.status_code == 200

        user_resp = register_user(client, "user@example.com", opt_in_improvement=True)
        assert user_resp.status_code == 200
        assert user_resp.json()["user"]["role"] == "user"
        assert user_resp.json()["user"]["credit_balance"] == 30
        assert user_resp.json()["user"]["improvement_consent"] is True
        assert user_resp.json()["user"]["improvement_consent_at"]
        user_headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

        redeem_resp = client.post(
            "/api/me/invite-code/redeem",
            headers=user_headers,
            json={"code": "MORE20"},
        )
        assert redeem_resp.status_code == 200
        assert redeem_resp.json()["credit_balance"] == 50

        run_resp = client.post(
            "/api/runs",
            headers=user_headers,
            json={"problem": "给相册 App 找非常规设计思路", "slot_count": 6},
        )
        assert run_resp.status_code == 200
        assert run_resp.json()["credit_balance"] == 44
        assert run_resp.json()["run"]["status"] == "queued"
        assert run_resp.json()["run"]["config_snapshot"]["slot_count"] == 6
        assert run_resp.json()["run"]["config_snapshot"]["credit_cost"] == 6
        assert run_resp.json()["run"]["config_snapshot"]["opt_in_improvement"] is True
        assert run_resp.json()["run"]["opt_in_improvement"] is True
        run_id = run_resp.json()["run"]["id"]

        from wildidea.web.database import SessionLocal
        from wildidea.web.models import Candidate, Run

        db = SessionLocal()
        try:
            db.add(Candidate(
                run_id=run_id,
                index=1,
                name="保留方案",
                slot="D1",
                source="保留来源",
                proto="保留机制",
                desc="保留描述",
                fail="保留边界",
            ))
            db.commit()
        finally:
            db.close()

        delete_resp = client.delete(f"/api/runs/{run_id}", headers=user_headers)
        assert delete_resp.status_code == 200
        list_after_delete = client.get("/api/runs", headers=user_headers)
        assert run_id not in {item["id"] for item in list_after_delete.json()["runs"]}

        db = SessionLocal()
        try:
            deleted_run = db.get(Run, run_id)
            assert deleted_run.status == "deleted"
            assert deleted_run.candidates[0].name == "保留方案"
        finally:
            db.close()


def test_registration_requires_email_code_and_smtp_configuration():
    with TestClient(webapp.app) as client:
        missing_code = client.post(
            "/api/auth/register",
            json={"email": "needs-code@example.com", "password": "secret12"},
        )
        assert missing_code.status_code == 422

        original_send = webapp.send_verification_email
        webapp.send_verification_email = lambda email, code: (_ for _ in ()).throw(
            webapp.EmailNotConfigured("邮件服务未配置，请设置 SMTP 环境变量")
        )
        try:
            no_smtp = client.post("/api/auth/email-code", json={"email": "no-smtp@example.com"})
        finally:
            webapp.send_verification_email = original_send
        assert no_smtp.status_code == 503
        assert no_smtp.json()["detail"]["error"] == "EMAIL_NOT_CONFIGURED"

        code = request_email_code(client, "verified-user@example.com")
        wrong_code = "000000" if code != "000000" else "111111"
        wrong = client.post(
            "/api/auth/register",
            json={
                "email": "verified-user@example.com",
                "password": "secret12",
                "verification_code": wrong_code,
                "opt_in_improvement": True,
            },
        )
        assert wrong.status_code == 422
        assert wrong.json()["detail"]["error"] == "EMAIL_CODE_INVALID"

        ok = client.post(
            "/api/auth/register",
            json={
                "email": "verified-user@example.com",
                "password": "secret12",
                "verification_code": code,
                "opt_in_improvement": True,
            },
        )
        assert ok.status_code == 200
        assert ok.json()["user"]["email_verified_at"]


def test_registration_requires_improvement_consent_before_consuming_email_code():
    with TestClient(webapp.app) as client:
        code = request_email_code(client, "privacy-consent@example.com")
        no_consent = client.post(
            "/api/auth/register",
            json={
                "email": "privacy-consent@example.com",
                "password": "secret12",
                "verification_code": code,
                "opt_in_improvement": False,
            },
        )
        assert no_consent.status_code == 422
        assert no_consent.json()["detail"]["error"] == "IMPROVEMENT_CONSENT_REQUIRED"

        ok = client.post(
            "/api/auth/register",
            json={
                "email": "privacy-consent@example.com",
                "password": "secret12",
                "verification_code": code,
                "opt_in_improvement": True,
            },
        )
        assert ok.status_code == 200
        assert ok.json()["user"]["improvement_consent"] is True
        assert ok.json()["user"]["improvement_consent_at"]


def test_feedback_is_mutually_exclusive_upsert():
    from sqlalchemy import func, select

    from wildidea.web.database import SessionLocal
    from wildidea.web.models import Candidate, Feedback, InteractionEvent, Run

    webapp.execute_run = lambda run_id: None

    with TestClient(webapp.app) as client:
        user_resp = register_user(client, "feedback@example.com")
        assert user_resp.status_code == 200
        headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

        run_resp = client.post(
            "/api/runs",
            headers=headers,
            json={"problem": "给相册 App 找非常规设计思路", "slot_count": 1},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run"]["id"]

        db = SessionLocal()
        try:
            candidate = Candidate(
                run_id=run_id,
                index=1,
                name="测试方案",
                slot="D1",
                source="测试来源",
                proto="通用机制",
                advantage="这种方案的优势在于，先解释为什么值得用",
                desc="具体方案",
                fail="失败条件",
                reroll_count=2,
            )
            silent_candidate = Candidate(
                run_id=run_id,
                index=2,
                name="未反馈方案",
                slot="D2",
                source="静默来源",
                proto="静默机制",
                advantage="这种方案的优势在于，沉默样本也可分析",
                desc="静默方案",
                fail="静默边界",
            )
            run_only = Run(
                user_id=user_resp.json()["user"]["id"],
                problem="只问问题无候选",
                status="failed",
                problem_type="product",
                error="模型失败",
                config_snapshot={"slot_count": 10, "credit_cost": 10},
            )
            db.add_all([candidate, silent_candidate, run_only])
            db.commit()
            candidate_id = candidate.id
        finally:
            db.close()

        first = client.post(
            f"/api/candidates/{candidate_id}/feedback",
            headers=headers,
            json={"label": "useful"},
        )
        assert first.status_code == 200
        assert first.json()["feedback"]["label"] == "useful"
        assert first.json()["feedback"]["adopted"] is False

        missing_other = client.post(
            f"/api/candidates/{candidate_id}/feedback",
            headers=headers,
            json={"label": "weak_other"},
        )
        assert missing_other.status_code == 422

        legacy_logic = client.post(
            f"/api/candidates/{candidate_id}/feedback",
            headers=headers,
            json={"label": "weak_logic"},
        )
        assert legacy_logic.status_code == 422

        for label in ["weak_obscure", "weak_off_topic", "weak_too_common", "weak_unusable"]:
            weak_resp = client.post(
                f"/api/candidates/{candidate_id}/feedback",
                headers=headers,
                json={"label": label},
            )
            assert weak_resp.status_code == 200
            assert weak_resp.json()["feedback_id"] == first.json()["feedback_id"]
            assert weak_resp.json()["feedback"]["label"] == label
            assert weak_resp.json()["feedback"]["rating"] == 2
            assert weak_resp.json()["feedback"]["adopted"] is False

        third = client.post(
            f"/api/candidates/{candidate_id}/feedback",
            headers=headers,
            json={"label": "weak_other", "comment": "不贴合真实相册场景"},
        )
        assert third.status_code == 200
        assert third.json()["feedback_id"] == first.json()["feedback_id"]
        assert third.json()["feedback"]["label"] == "weak_other"
        assert third.json()["feedback"]["rating"] == 2
        assert third.json()["feedback"]["adopted"] is False
        assert third.json()["feedback"]["comment"] == "不贴合真实相册场景"

        run_detail = client.get(f"/api/runs/{run_id}", headers=headers)
        assert run_detail.status_code == 200
        assert run_detail.json()["run"]["candidates"][0]["feedback"]["label"] == "weak_other"

        if user_resp.json()["user"]["role"] == "admin":
            admin_headers = headers
        else:
            admin_login = client.post(
                "/api/auth/login",
                json={"email": "admin@example.com", "password": "secret12"},
            )
            assert admin_login.status_code == 200
            admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        admin_feedback = client.get("/api/admin/feedback", headers=admin_headers)
        assert admin_feedback.status_code == 200
        latest = admin_feedback.json()["feedback"][0]
        assert latest["user_email"] == "feedback@example.com"
        assert latest["run_problem"] == "给相册 App 找非常规设计思路"
        assert latest["candidate_name"] == "测试方案"
        assert latest["candidate_slot"] == "D1"
        assert latest["candidate_domain"] == ""
        assert latest["candidate_reroll_count"] == 2
        assert latest["candidate_source_phenomenon"] == "测试来源"
        assert latest["candidate_source"] == "测试来源"
        assert latest["candidate_proto"] == "通用机制"
        assert latest["candidate_advantage"] == "这种方案的优势在于，先解释为什么值得用"
        assert latest["candidate_desc"] == "具体方案"
        assert latest["candidate_fail"] == "失败条件"
        assert latest["candidate_scores"] == {}
        assert latest["label"] == "weak_other"
        assert latest["comment"] == "不贴合真实相册场景"

        export_resp = client.get("/api/admin/feedback.xlsx", headers=admin_headers)
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert export_resp.content.startswith(b"PK")
        from io import BytesIO
        from zipfile import ZipFile

        with ZipFile(BytesIO(export_resp.content)) as archive:
            sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        assert "全量数据" in workbook_xml
        assert 'filename="wildidea-data.xlsx"' in export_resp.headers["content-disposition"]
        assert "数据类型" in sheet_xml
        assert "反馈类型" in sheet_xml
        assert "是否有反馈" in sheet_xml
        assert "重抽次数" in sheet_xml
        assert "不贴合真实相册场景" in sheet_xml
        assert "测试方案" in sheet_xml
        assert "未反馈方案" in sheet_xml
        assert "只问问题无候选" in sheet_xml
        assert "先解释为什么值得用" in sheet_xml
        assert "具体方案" in sheet_xml
        assert "静默方案" in sheet_xml

        db = SessionLocal()
        try:
            feedback_count = db.scalar(
                select(func.count()).select_from(Feedback).where(Feedback.candidate_id == candidate_id)
            )
            event_count = db.scalar(
                select(func.count()).select_from(InteractionEvent).where(
                    InteractionEvent.candidate_id == candidate_id,
                    InteractionEvent.event_type == "feedback",
                )
            )
            assert feedback_count == 1
            assert event_count == 6
        finally:
            db.close()


def test_create_run_defaults_to_ten_parallel_ten_cards():
    webapp.execute_run = lambda run_id: None

    with TestClient(webapp.app) as client:
        user_resp = register_user(client, "defaults@example.com")
        assert user_resp.status_code == 200
        headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

        run_resp = client.post(
            "/api/runs",
            headers=headers,
            json={"problem": "默认抽卡配置"},
        )

        assert run_resp.status_code == 200
        snapshot = run_resp.json()["run"]["config_snapshot"]
        assert run_resp.json()["run"]["created_at"].endswith("Z")
        assert snapshot["parallel"] == 10
        assert snapshot["slot_count"] == 10
        assert snapshot["credit_cost"] == 10
        assert "generation_mode" not in snapshot
        assert snapshot["max_retries"] == 3
        assert run_resp.json()["credit_balance"] == 20

        legacy_config_resp = client.post(
            "/api/runs",
            headers=headers,
            json={"problem": "旧前端配置不应改变策略", "slot_count": 1, "parallel": 1, "generation_mode": "speed"},
        )
        assert legacy_config_resp.status_code == 200
        legacy_snapshot = legacy_config_resp.json()["run"]["config_snapshot"]
        assert legacy_snapshot["parallel"] == 10
        assert "generation_mode" not in legacy_snapshot
        assert legacy_snapshot["max_retries"] == 3


def test_worker_executor_queues_without_background_execution():
    called: list[str] = []
    webapp.execute_run = lambda run_id: called.append(run_id)
    original_executor = webapp.settings.run_executor
    original_limit = webapp.settings.user_active_run_limit
    object.__setattr__(webapp.settings, "run_executor", "worker")
    object.__setattr__(webapp.settings, "user_active_run_limit", 1)
    try:
        with TestClient(webapp.app) as client:
            user_resp = register_user(client, "worker-queue@example.com")
            assert user_resp.status_code == 200
            headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

            run_resp = client.post(
                "/api/runs",
                headers=headers,
                json={"problem": "worker 模式入队", "slot_count": 1},
            )
            assert run_resp.status_code == 200
            assert run_resp.json()["run"]["status"] == "queued"
            assert run_resp.json()["credit_balance"] == 29
            assert called == []

            blocked_resp = client.post(
                "/api/runs",
                headers=headers,
                json={"problem": "第二个 worker 任务", "slot_count": 1},
            )
            assert blocked_resp.status_code == 429
            assert blocked_resp.json()["detail"]["error"] == "ACTIVE_RUN_LIMIT_REACHED"
    finally:
        object.__setattr__(webapp.settings, "run_executor", original_executor)
        object.__setattr__(webapp.settings, "user_active_run_limit", original_limit)


def test_queued_run_reports_position_and_wait_estimate():
    from wildidea.web.database import SessionLocal
    from wildidea.web.models import Run, WorkerHeartbeat

    webapp.execute_run = lambda run_id: None
    original_executor = webapp.settings.run_executor
    original_limit = webapp.settings.user_active_run_limit
    object.__setattr__(webapp.settings, "run_executor", "worker")
    object.__setattr__(webapp.settings, "user_active_run_limit", 1)
    try:
        db = SessionLocal()
        try:
            for run in db.query(Run).filter(Run.status.in_(["queued", "running"])).all():
                run.status = "succeeded"
            db.query(WorkerHeartbeat).delete()
            db.commit()
        finally:
            db.close()

        with TestClient(webapp.app) as client:
            first_user = register_user(client, "queue-first@example.com")
            second_user = register_user(client, "queue-second@example.com")
            first_headers = {"Authorization": f"Bearer {first_user.json()['access_token']}"}
            second_headers = {"Authorization": f"Bearer {second_user.json()['access_token']}"}

            first_run = client.post(
                "/api/runs",
                headers=first_headers,
                json={"problem": "前序任务", "slot_count": 2},
            )
            assert first_run.status_code == 200

            second_run = client.post(
                "/api/runs",
                headers=second_headers,
                json={"problem": "后续任务", "slot_count": 1},
            )
            assert second_run.status_code == 200
            run_id = second_run.json()["run"]["id"]

            detail = client.get(f"/api/runs/{run_id}", headers=second_headers)
            assert detail.status_code == 200
            queue = detail.json()["run"]["queue"]
            assert queue["status"] == "queued"
            assert queue["queue_position"] == 2
            assert queue["queued_ahead"] == 1
            assert queue["tasks_ahead"] == 1
            assert queue["users_ahead"] == 1
            assert queue["estimated_wait_seconds"] >= 180
            assert queue["worker_online"] is False
    finally:
        object.__setattr__(webapp.settings, "run_executor", original_executor)
        object.__setattr__(webapp.settings, "user_active_run_limit", original_limit)


def test_admin_queue_status_and_worker_once(monkeypatch):
    from datetime import datetime, timezone

    from wildidea.web import worker
    from wildidea.web.database import SessionLocal, init_db
    from wildidea.web.models import Run, RunEvent, RunLog, User, WorkerHeartbeat, utcnow

    init_db()
    db = SessionLocal()
    try:
        user = User(email="worker-once@example.com", password_hash="x", credit_balance=10)
        db.add(user)
        db.flush()
        run = Run(
            user_id=user.id,
            problem="worker 消费队列",
            status="queued",
            config_snapshot={"parallel": 1, "slot_count": 1, "credit_cost": 1},
            created_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        db.add(run)
        db.commit()
        run_id = run.id
    finally:
        db.close()

    consumed: list[str] = []

    def fake_execute_run(target_run_id: str) -> None:
        consumed.append(target_run_id)
        local_db = SessionLocal()
        try:
            target_run = local_db.get(Run, target_run_id)
            target_run.status = "succeeded"
            target_run.finished_at = utcnow()
            local_db.add(RunEvent(run_id=target_run_id, event_type="status", payload={"status": "succeeded"}))
            local_db.commit()
        finally:
            local_db.close()

    monkeypatch.setattr(worker, "execute_run", fake_execute_run)

    assert worker.run_worker_once("pytest-worker") is True
    assert consumed == [run_id]

    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        heartbeat = db.get(WorkerHeartbeat, "pytest-worker")
        logs = db.query(RunLog).filter_by(run_id=run_id).all()
        assert run.status == "succeeded"
        assert heartbeat.status == "idle"
        assert heartbeat.current_run_id is None
        assert {row.message for row in logs} >= {"worker claimed run", "worker released run"}
    finally:
        db.close()

    with TestClient(webapp.app) as client:
        admin_resp = register_user(client, "queue-admin@example.com")
        assert admin_resp.status_code == 200
        admin_headers = {"Authorization": f"Bearer {admin_resp.json()['access_token']}"}
        db = SessionLocal()
        try:
            admin = db.get(User, admin_resp.json()["user"]["id"])
            admin.role = "admin"
            db.commit()
        finally:
            db.close()

        queue_resp = client.get("/api/admin/queue", headers=admin_headers)
        assert queue_resp.status_code == 200
        payload = queue_resp.json()["queue"]
        assert "counts" in payload
        assert payload["workers"][0]["id"] == "pytest-worker"
        assert any(item["message"] == "worker released run" for item in payload["recent_logs"])


def test_run_event_stream_accepts_token_query():
    from wildidea.web.database import SessionLocal
    from wildidea.web.models import Run, RunEvent

    webapp.execute_run = lambda run_id: None

    with TestClient(webapp.app) as client:
        user_resp = register_user(client, "sse-token@example.com")
        assert user_resp.status_code == 200
        token = user_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        run_resp = client.post(
            "/api/runs",
            headers=headers,
            json={"problem": "事件流鉴权", "slot_count": 1},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run"]["id"]

        db = SessionLocal()
        try:
            run = db.get(Run, run_id)
            run.status = "succeeded"
            db.add(RunEvent(run_id=run_id, event_type="status", payload={"status": "succeeded"}))
            db.commit()
        finally:
            db.close()

        with client.stream("GET", f"/api/runs/{run_id}/events?token={token}") as response:
            assert response.status_code == 200
            text = next(response.iter_text())
        assert '"event_type": "status"' in text


def test_runner_build_pipeline_config_returns_config():
    import wildidea.web.runner as runner
    from wildidea.pipeline import Config

    config = runner._build_pipeline_config(
        {
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4-pro",
            "judge_model": "deepseek/deepseek-v4-pro",
        },
        output_dir=Path("/tmp/wildidea-test-output"),
    )

    assert isinstance(config, Config)
    assert config.provider == "openrouter"
    assert config.model == "deepseek/deepseek-v4-pro"
    assert config.judge_config.provider == "openrouter"
    assert config.parallel == 10
    assert config.target_count == 10
    assert config.max_retries == 3


def test_production_like_default_run_partial_refund_and_reroll_events(monkeypatch):
    import wildidea.web.runner as runner
    from wildidea.judge import JudgeScores
    from wildidea.pipeline import Result
    from wildidea.renderer import Candidate as RenderCandidate
    from wildidea.web.database import SessionLocal
    from wildidea.web.models import CreditTransaction, RunEvent

    webapp.execute_run = runner.execute_run

    def scores_payload(scores: JudgeScores) -> dict:
        return {
            "structural_depth": scores.structural_depth,
            "domain_distance": scores.domain_distance,
            "applicability": scores.applicability,
            "novelty": scores.novelty,
            "unexpectedness": scores.unexpectedness,
            "non_obviousness": scores.non_obviousness,
            "raw": scores.raw,
        }

    def fake_run_pipeline(problem, config, on_progress):
        assert config.parallel == 10
        assert config.target_count == 10
        slots = [
            {
                "slot_id": f"slot-{idx}",
                "slot": "D4",
                "domain": f"领域{idx}",
                "source": f"源现象{idx}",
                "source_phenomenon": f"源现象{idx}",
            }
            for idx in range(1, 11)
        ]
        on_progress("slots_done", {"count": 10, "target": 10, "slots": slots})
        candidates = []
        for idx in range(1, 9):
            slot_id = f"slot-{idx}"
            reroll_count = 0
            if idx == 2:
                reroll_count = 1
                on_progress("threshold_rejected", {
                    "slot_id": slot_id,
                    "slot": "D4",
                    "name": "低可用草稿",
                    "attempt": 1,
                    "sd": 8,
                    "nv": 8,
                    "ap": 8,
                    "sd_threshold": 8,
                    "novelty_threshold": 7,
                    "applicability_threshold": 9,
                })
            if idx == 5:
                reroll_count = 2
                for attempt in (1, 2):
                    on_progress("threshold_rejected", {
                        "slot_id": slot_id,
                        "slot": "D4",
                        "name": f"低分草稿{attempt}",
                        "attempt": attempt,
                        "sd": 7,
                        "nv": 8,
                        "ap": 9,
                        "sd_threshold": 8,
                        "novelty_threshold": 7,
                        "applicability_threshold": 9,
                    })
            scores = JudgeScores(
                structural_depth=8,
                domain_distance=9,
                applicability=9,
                novelty=8,
            )
            candidate = RenderCandidate(
                name=f"生产模拟方案{idx}",
                slot="D4",
                source=f"抽象方法{idx}",
                proto=f"抽象结构{idx}",
                desc=f"落地方案{idx}",
                fail=f"失败边界{idx}",
                scores=scores,
                reroll_count=reroll_count,
            )
            candidates.append(candidate)
            on_progress("candidate_ok", {
                "slot_id": slot_id,
                "index": len(candidates),
                "attempt": reroll_count + 1,
                "reroll_count": reroll_count,
                "name": candidate.name,
                "slot": candidate.slot,
                "source": candidate.source,
                "proto": candidate.proto,
                "desc": candidate.desc,
                "fail": candidate.fail,
                "scores": scores_payload(scores),
                "done": len(candidates),
                "total": 10,
            })
        return Result(
            candidates=candidates,
            errors=[],
            avg_scores={
                "structural_depth": 8,
                "domain_distance": 9,
                "novelty": 8,
                "applicability": 9,
            },
        )

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)

    with TestClient(webapp.app) as client:
        user_resp = register_user(client, "production-like@example.com")
        assert user_resp.status_code == 200
        headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

        run_resp = client.post(
            "/api/runs",
            headers=headers,
            json={"problem": "生产模拟默认 10 卡"},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run"]["id"]

        detail = client.get(f"/api/runs/{run_id}", headers=headers)
        assert detail.status_code == 200
        run = detail.json()["run"]
        assert run["status"] == "succeeded"
        assert len(run["candidates"]) == 8
        assert run["candidates"][0]["scores"]["applicability"] == 9
        assert run["candidates"][1]["reroll_count"] == 1
        assert run["candidates"][4]["reroll_count"] == 2

        ok_events = [event for event in run["events"] if event["event_type"] == "candidate_ok"]
        rejected_events = [event for event in run["events"] if event["event_type"] == "threshold_rejected"]
        assert len(ok_events) == 8
        assert len(rejected_events) == 3
        assert ok_events[1]["payload"]["reroll_count"] == 1
        assert ok_events[4]["payload"]["reroll_count"] == 2

        me_resp = client.get("/api/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["user"]["credit_balance"] == 22

        db = SessionLocal()
        try:
            partial_refund = db.query(CreditTransaction).filter_by(
                run_id=run_id,
                reason="run_partial_refund",
            ).one()
            refund_event = db.query(RunEvent).filter_by(
                run_id=run_id,
                event_type="refund",
            ).filter(RunEvent.payload["reason"].as_string() == "partial_card_refund").one()
            assert partial_refund.amount == 2
            assert partial_refund.meta["generated_candidates"] == 8
            assert partial_refund.meta["missing_cards"] == 2
            assert partial_refund.meta["reason"] == "reroll_limit_or_quality_gate"
            assert refund_event.payload["credits"] == 2
            assert refund_event.payload["missing_cards"] == 2
        finally:
            db.close()


def test_candidate_ok_persists_live_candidate_and_preserves_feedback(monkeypatch):
    import wildidea.web.runner as runner
    from wildidea.judge import JudgeScores
    from wildidea.pipeline import Result
    from wildidea.renderer import Candidate as RenderCandidate
    from wildidea.web.database import SessionLocal, init_db
    from wildidea.web.models import Candidate, Feedback, Run, User

    init_db()
    db = SessionLocal()
    try:
        user = User(email="live-feedback@example.com", password_hash="x", credit_balance=10)
        db.add(user)
        db.flush()
        run = Run(
            user_id=user.id,
            problem="生成中反馈",
            status="queued",
            config_snapshot={"parallel": 1, "slot_count": 1, "credit_cost": 1},
        )
        db.add(run)
        db.commit()
        run_id = run.id
        user_id = user.id
    finally:
        db.close()

    scores = JudgeScores(structural_depth=8, domain_distance=9, applicability=9, novelty=8)

    def fake_run_pipeline(problem, config, on_progress):
        on_progress("slots_done", {
            "count": 1,
            "target": 1,
            "slots": [{
                "slot_id": "live-slot",
                "slot": "D4",
                "domain": "产品",
                "source": "源现象",
                "source_phenomenon": "源现象",
            }],
        })
        candidate = RenderCandidate(
            name="实时方案",
            slot="D4",
            source="抽象方法",
            proto="抽象结构",
            desc="落地方案",
            fail="失败边界",
            scores=scores,
            reroll_count=1,
        )
        on_progress("candidate_ok", {
            "slot_id": "live-slot",
            "index": 1,
            "attempt": 2,
            "reroll_count": 1,
            "name": candidate.name,
            "slot": candidate.slot,
            "source": candidate.source,
            "proto": candidate.proto,
            "desc": candidate.desc,
            "fail": candidate.fail,
            "scores": {
                "structural_depth": 8,
                "domain_distance": 9,
                "applicability": 9,
                "novelty": 8,
            },
            "done": 1,
            "total": 1,
        })
        live_db = SessionLocal()
        try:
            live_candidate = live_db.query(Candidate).filter_by(run_id=run_id, index=1).one()
            live_db.add(Feedback(
                user_id=user_id,
                candidate_id=live_candidate.id,
                rating=5,
                label="useful",
            ))
            live_db.commit()
        finally:
            live_db.close()
        return Result(candidates=[candidate], errors=[], avg_scores={"applicability": 9})

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)

    runner.execute_run(run_id)

    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        candidate = db.query(Candidate).filter_by(run_id=run_id, index=1).one()
        feedback = db.query(Feedback).filter_by(candidate_id=candidate.id).one()
        assert run.status == "succeeded"
        assert candidate.name == "实时方案"
        assert candidate.reroll_count == 1
        assert feedback.label == "useful"
    finally:
        db.close()


def test_production_like_all_cards_fail_gets_full_refund(monkeypatch):
    import wildidea.web.runner as runner
    from wildidea.pipeline import Result
    from wildidea.web.database import SessionLocal
    from wildidea.web.models import CreditTransaction

    webapp.execute_run = runner.execute_run

    def fake_run_pipeline(problem, config, on_progress):
        assert config.target_count == 3
        on_progress("slots_done", {
            "count": 3,
            "target": 3,
            "slots": [
                {"slot_id": f"fail-slot-{idx}", "slot": "D4", "domain": "产品", "source": "源现象"}
                for idx in range(1, 4)
            ],
        })
        for idx in range(1, 4):
            on_progress("threshold_rejected", {
                "slot_id": f"fail-slot-{idx}",
                "slot": "D4",
                "name": f"失败草稿{idx}",
                "attempt": 1,
                "sd": 6,
                "nv": 6,
                "ap": 7,
                "sd_threshold": 8,
                "novelty_threshold": 7,
                "applicability_threshold": 9,
            })
            on_progress("gen_fail", {
                "slot_id": f"fail-slot-{idx}",
                "slot": "D4",
                "reason": "exhausted retries",
            })
        return Result(candidates=[], errors=[], avg_scores={})

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)

    with TestClient(webapp.app) as client:
        user_resp = register_user(client, "all-fail@example.com")
        assert user_resp.status_code == 200
        headers = {"Authorization": f"Bearer {user_resp.json()['access_token']}"}

        run_resp = client.post(
            "/api/runs",
            headers=headers,
            json={"problem": "生产模拟全部失败", "slot_count": 3, "parallel": 3},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["run"]["id"]

        detail = client.get(f"/api/runs/{run_id}", headers=headers)
        assert detail.status_code == 200
        run = detail.json()["run"]
        assert run["status"] == "failed"
        assert run["error"] == "No candidates were generated"
        assert len([event for event in run["events"] if event["event_type"] == "threshold_rejected"]) == 3

        me_resp = client.get("/api/me", headers=headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["user"]["credit_balance"] == 30

        db = SessionLocal()
        try:
            refund = db.query(CreditTransaction).filter_by(
                run_id=run_id,
                reason="run_refund",
            ).one()
            assert refund.amount == 3
        finally:
            db.close()


def test_parallel_progress_events_are_thread_safe(monkeypatch):
    from sqlalchemy import func, select

    import wildidea.web.runner as runner
    from wildidea.pipeline import Result
    from wildidea.renderer import Candidate
    from wildidea.web.database import SessionLocal, init_db
    from wildidea.web.models import Run, RunEvent, User

    init_db()
    db = SessionLocal()
    try:
        user = User(email="progress@example.com", password_hash="x", credit_balance=10)
        db.add(user)
        db.flush()
        run = Run(
            user_id=user.id,
            problem="给相册 App 找创新思路",
            status="queued",
            config_snapshot={"parallel": 8, "slot_count": 2, "credit_cost": 2},
        )
        db.add(run)
        db.commit()
        run_id = run.id
    finally:
        db.close()

    def fake_run_pipeline(problem, config, on_progress):
        def emit(index):
            on_progress("generating", {"slot_id": f"slot-{index}", "attempt": 1})

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(emit, range(20)))
        return Result(
            candidates=[
                Candidate(
                    name="测试方案",
                    slot="D1",
                    source="测试来源",
                    proto="通用机制",
                    desc="具体方案",
                    fail="失败条件",
                )
            ],
            errors=[],
            avg_scores={},
        )

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)

    runner.execute_run(run_id)

    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        generating_count = db.scalar(
            select(func.count()).select_from(RunEvent).where(
                RunEvent.run_id == run_id,
                RunEvent.event_type == "generating",
            )
        )
        assert run.status == "succeeded"
        assert generating_count == 20
    finally:
        db.close()


def test_execute_run_refunds_missing_cards(monkeypatch):
    import wildidea.web.runner as runner
    from wildidea.pipeline import Result
    from wildidea.renderer import Candidate
    from wildidea.web.database import SessionLocal, init_db
    from wildidea.web.models import CreditTransaction, Run, RunEvent, User
    from wildidea.web.services import charge_run_credit

    init_db()
    db = SessionLocal()
    try:
        user = User(email="partial-refund@example.com", password_hash="x", credit_balance=5)
        db.add(user)
        db.flush()
        run = Run(
            user_id=user.id,
            problem="给相册 App 找创新思路",
            status="queued",
            config_snapshot={"parallel": 1, "slot_count": 3, "credit_cost": 3},
        )
        db.add(run)
        db.flush()
        charge_run_credit(db, user, run.id, amount=3)
        db.commit()
        run_id = run.id
        user_id = user.id
    finally:
        db.close()

    def fake_run_pipeline(problem, config, on_progress):
        return Result(
            candidates=[
                Candidate(
                    name="通过阈值的方案",
                    slot="D1",
                    source="测试来源",
                    proto="通用机制",
                    desc="具体方案",
                    fail="失败条件",
                )
            ],
            errors=[],
            avg_scores={},
        )

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)

    runner.execute_run(run_id)

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        run = db.get(Run, run_id)
        partial_refund = db.query(CreditTransaction).filter_by(
            run_id=run_id,
            reason="run_partial_refund",
        ).one()
        refund_event = db.query(RunEvent).filter_by(
            run_id=run_id,
            event_type="refund",
        ).filter(RunEvent.payload["reason"].as_string() == "partial_card_refund").one()

        assert run.status == "succeeded"
        assert user.credit_balance == 4
        assert partial_refund.amount == 2
        assert partial_refund.meta["generated_candidates"] == 1
        assert partial_refund.meta["missing_cards"] == 2
        assert refund_event.payload["credits"] == 2
        assert refund_event.payload["missing_cards"] == 2
    finally:
        db.close()


def test_late_worker_does_not_overwrite_interrupted_run(monkeypatch):
    import wildidea.web.runner as runner
    from wildidea.pipeline import Result
    from wildidea.renderer import Candidate
    from wildidea.web.database import SessionLocal, init_db
    from wildidea.web.models import Run, User
    from wildidea.web.services import charge_run_credit, refund_run_credit

    init_db()
    db = SessionLocal()
    try:
        user = User(email="late-worker@example.com", password_hash="x", credit_balance=10)
        db.add(user)
        db.flush()
        run = Run(
            user_id=user.id,
            problem="模拟服务重启竞态",
            status="queued",
            config_snapshot={"parallel": 1, "slot_count": 1, "credit_cost": 1},
        )
        db.add(run)
        db.flush()
        charge_run_credit(db, user, run.id, amount=1)
        db.commit()
        run_id = run.id
        user_id = user.id
    finally:
        db.close()

    def fake_run_pipeline(problem, config, on_progress):
        race_db = SessionLocal()
        try:
            race_run = race_db.get(Run, run_id)
            race_user = race_db.get(User, user_id)
            race_run.status = "failed"
            race_run.error = "服务重启或任务中断，已自动退回积分"
            refund_run_credit(race_db, race_user, race_run, reason="run_interrupted_refund")
            race_db.commit()
        finally:
            race_db.close()
        return Result(
            candidates=[
                Candidate(
                    name="迟到的方案",
                    slot="D1",
                    source="测试来源",
                    proto="通用机制",
                    desc="具体方案",
                    fail="失败条件",
                )
            ],
            errors=[],
            avg_scores={},
        )

    monkeypatch.setattr(runner, "run_pipeline", fake_run_pipeline)

    runner.execute_run(run_id)

    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        user = db.get(User, user_id)
        assert run.status == "failed"
        assert run.error == "服务重启或任务中断，已自动退回积分"
        assert run.candidates == []
        assert user.credit_balance == 10
    finally:
        db.close()
