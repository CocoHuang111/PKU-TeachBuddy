"""多用户认证、隔离、管理员和 mock SSO 测试。需要可用的 PostgreSQL。"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("AUTH_MODE", "local")
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("LOCAL_REGISTRATION_ENABLED", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pku2:pku2@127.0.0.1:5432/pku2",
)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, select, text  # noqa: E402

from backend.app.core.app_settings import get_app_settings, reset_app_settings  # noqa: E402
from backend.app.core.database import reset_engines  # noqa: E402
from backend.app.core.storage import random_filename  # noqa: E402
from backend.app.models import AuditLog, AuthIdentity, Base  # noqa: E402


def _postgres_ready() -> bool:
    try:
        engine = create_engine(get_app_settings().database_url_sync)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@unittest.skipUnless(_postgres_ready(), "PostgreSQL 未启动，跳过认证测试")
class AuthSystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_app_settings()
        reset_engines()
        engine = create_engine(get_app_settings().database_url_sync)
        Base.metadata.create_all(engine)
        engine.dispose()
        from backend.app.main import app

        cls.app = app
        cls._cm = TestClient(app)
        cls.client = cls._cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cm.__exit__(None, None, None)

    def setUp(self) -> None:
        os.environ["AUTH_MODE"] = "local"
        os.environ["LOCAL_REGISTRATION_ENABLED"] = "true"
        os.environ["LOCAL_REGISTRATION_INVITE_CODE"] = ""
        os.environ["LOCAL_REGISTRATION_MAX_USES"] = "0"
        reset_app_settings()
        self.suffix = uuid.uuid4().hex[:10]

    def register(self, username=None, password="password12", display_name="教师", school=None):
        username = username or f"u{self.suffix}"
        resp = self.client.post(
            "/api/auth/register",
            json={
                "school": "测试学校" if school is None else school,
                "username": username,
                "password": password,
                "confirm_password": password,
                "display_name": display_name,
                "role": "admin",
            },
        )
        return resp, username

    def login(self, username, password="password12", school=None):
        return self.client.post(
            "/api/auth/login",
            json={
                "school": "测试学校" if school is None else school,
                "username": username,
                "password": password,
            },
        )

    def test_register_login_logout_and_me(self):
        resp, username = self.register()
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertNotIn("token", resp.json())
        self.assertEqual(resp.json()["user"]["role"], "user")
        self.assertEqual(resp.json()["user"]["school"], "测试学校")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        login = self.login(username)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_login_distinguishes_unknown_username_and_wrong_password(self):
        unknown = self.login(f"missing{self.suffix}")
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.json()["detail"], "学校和工号不匹配")

        registered, username = self.register()
        self.assertEqual(registered.status_code, 200, registered.text)
        self.client.post("/api/auth/logout")
        wrong_password = self.login(username, password="incorrect-password")
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(wrong_password.json()["detail"], "密码错误")

    def test_password_not_plaintext(self):
        resp, username = self.register()
        self.assertEqual(resp.status_code, 200, resp.text)
        engine = create_engine(get_app_settings().database_url_sync)
        with engine.connect() as conn:
            row = conn.execute(
                select(AuthIdentity.password_hash).where(
                    AuthIdentity.provider == "local",
                    AuthIdentity.subject == username,
                )
            ).fetchone()
        engine.dispose()
        self.assertTrue(row and row[0].startswith("$argon2"))
        self.assertNotIn("password12", row[0])

    def test_duplicate_username(self):
        resp, username = self.register()
        self.assertEqual(resp.status_code, 200, resp.text)
        again, _ = self.register(username=username)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"], "该学校的工号已被使用")

    def test_same_staff_id_can_register_at_another_school(self):
        resp, username = self.register(school="学校甲")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.client.post("/api/auth/logout")
        other, _ = self.register(username=username, school="学校乙")
        self.assertEqual(other.status_code, 200, other.text)
        conflict = self.client.patch("/api/auth/me", json={"school": "学校甲"})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        moved = self.client.patch("/api/auth/me", json={"school": "学校丙"})
        self.assertEqual(moved.status_code, 200, moved.text)
        self.assertEqual(moved.json()["school"], "学校丙")
        self.client.post("/api/auth/logout")
        self.assertEqual(self.login(username, school="学校乙").status_code, 401)
        ok = self.login(username, school="学校丙")
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(self.login(username, school="学校甲").status_code, 200)

    def test_invite_quota_counts_successful_registrations_under_concurrency(self):
        engine = create_engine(get_app_settings().database_url_sync)
        with engine.connect() as conn:
            used_before = conn.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "register",
                    AuditLog.details["provider"].astext == "local",
                )
            )
        engine.dispose()

        os.environ["LOCAL_REGISTRATION_INVITE_CODE"] = "beta-test-code"
        os.environ["LOCAL_REGISTRATION_MAX_USES"] = str(used_before + 1)
        reset_app_settings()

        def register_one(index):
            client = TestClient(self.app)
            try:
                return client.post(
                    "/api/auth/register",
                    json={
                        "school": "测试学校",
                        "username": f"beta{index}{self.suffix}",
                        "password": "password12",
                        "confirm_password": "password12",
                        "display_name": "内测用户",
                        "invite_code": "beta-test-code",
                    },
                )
            finally:
                client.close()

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(register_one, (1, 2)))
            self.assertEqual(sorted(response.status_code for response in responses), [200, 403])
            self.assertEqual(
                next(response.json()["detail"] for response in responses if response.status_code == 403),
                "内测名额已满，暂不接受新用户注册",
            )
            engine = create_engine(get_app_settings().database_url_sync)
            with engine.connect() as conn:
                used_after = conn.scalar(
                    select(func.count())
                    .select_from(AuditLog)
                    .where(
                        AuditLog.action == "register",
                        AuditLog.details["provider"].astext == "local",
                    )
                )
            engine.dispose()
            self.assertEqual(used_after, used_before + 1)
        finally:
            os.environ["LOCAL_REGISTRATION_INVITE_CODE"] = ""
            os.environ["LOCAL_REGISTRATION_MAX_USES"] = "0"
            reset_app_settings()

    def test_cannot_register_as_admin(self):
        resp, _ = self.register()
        self.assertEqual(resp.json()["user"]["role"], "user")

    def test_disabled_session_invalid(self):
        from sqlalchemy.orm import Session

        from backend.app.models import User

        resp, _ = self.register()
        user_id = resp.json()["user"]["id"]
        engine = create_engine(get_app_settings().database_url_sync)
        with Session(engine) as session:
            user = session.get(User, __import__("uuid").UUID(user_id))
            user.status = "disabled"
            session.commit()
        engine.dispose()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_local_mode_allows_login(self):
        self.assertEqual(self.client.get("/api/auth/config").json()["auth_mode"], "local")
        resp, _ = self.register()
        self.assertEqual(resp.status_code, 200)

    def test_pku_mode_blocks_local_login(self):
        os.environ["AUTH_MODE"] = "pku_sso"
        reset_app_settings()
        try:
            cfg = self.client.get("/api/auth/config").json()
            self.assertEqual(cfg["auth_mode"], "pku_sso")
            self.assertFalse(cfg["registration_enabled"])
            self.assertEqual(
                self.client.post(
                    "/api/auth/register",
                    json={
                        "school": "测试学校",
                        "username": f"x{self.suffix}",
                        "password": "password12",
                        "confirm_password": "password12",
                        "display_name": "X",
                    },
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    "/api/auth/login",
                    json={"username": "nope", "password": "password12"},
                ).status_code,
                403,
            )
        finally:
            os.environ["AUTH_MODE"] = "local"
            reset_app_settings()

    def test_mock_sso_creates_and_reuses_user(self):
        os.environ["AUTH_MODE"] = "pku_sso"
        reset_app_settings()
        subject = f"pku-{self.suffix}"
        try:
            first = self.client.get(
                "/api/auth/pku/callback",
                params={"mock": "1", "subject": subject},
            )
            self.assertEqual(first.status_code, 200, first.text)
            user_id = first.json()["user"]["id"]
            self.client.post("/api/auth/logout")
            second = self.client.get(
                "/api/auth/pku/callback",
                params={"mock": "1", "subject": subject},
            )
            self.assertEqual(second.status_code, 200)
            self.assertEqual(second.json()["user"]["id"], user_id)
        finally:
            os.environ["AUTH_MODE"] = "local"
            reset_app_settings()

    def test_providers_do_not_merge(self):
        subject = f"same{self.suffix}"
        resp, _ = self.register(username=subject)
        local_id = resp.json()["user"]["id"]
        os.environ["AUTH_MODE"] = "pku_sso"
        reset_app_settings()
        try:
            sso = self.client.get(
                "/api/auth/pku/callback",
                params={"mock": "1", "subject": subject},
            )
            self.assertEqual(sso.status_code, 200, sso.text)
            self.assertNotEqual(sso.json()["user"]["id"], local_id)
        finally:
            os.environ["AUTH_MODE"] = "local"
            reset_app_settings()

    def test_user_isolation(self):
        user_a = f"a{self.suffix}"
        user_b = f"b{self.suffix}"
        self.client.post(
            "/api/auth/register",
            json={
                "school": "测试学校",
                "username": user_a,
                "password": "password12",
                "confirm_password": "password12",
                "display_name": "A",
            },
        )
        cookies_a = dict(self.client.cookies)
        self.client.cookies.clear()
        self.client.post(
            "/api/auth/register",
            json={
                "school": "测试学校",
                "username": user_b,
                "password": "password12",
                "confirm_password": "password12",
                "display_name": "B",
            },
        )
        cookies_b = dict(self.client.cookies)
        me_a = self.client.get("/api/auth/me", cookies=cookies_a)
        self.assertEqual(me_a.status_code, 200, me_a.text)
        import asyncio

        from backend.app.core import db as core_db

        task_id = asyncio.run(
            core_db.create_syllabus_task(
                filename="隔离测试",
                prompt_mode=None,
                source_text="这是一份足够长的测试大纲内容，用于隔离。",
                user_id=me_a.json()["id"],
            )
        )
        self.assertEqual(
            self.client.get(f"/api/syllabus/task/{task_id}", cookies=cookies_a).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(f"/api/syllabus/task/{task_id}", cookies=cookies_b).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f"/api/syllabus/task/{task_id}/cancel", cookies=cookies_b).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"/api/syllabus/task/{task_id}", cookies=cookies_b).status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/admin/overview", cookies=cookies_b).status_code,
            403,
        )

    def test_admin_access_and_audit(self):
        from sqlalchemy.orm import Session

        from backend.app.models import User

        resp, username = self.register(username=f"adm{self.suffix}")
        user_id = resp.json()["user"]["id"]
        engine = create_engine(get_app_settings().database_url_sync)
        with Session(engine) as session:
            user = session.get(User, __import__("uuid").UUID(user_id))
            user.role = "admin"
            session.commit()
        engine.dispose()
        self.client.post("/api/auth/logout")
        self.login(username)
        overview = self.client.get("/api/admin/overview")
        self.assertEqual(overview.status_code, 200, overview.text)
        audit = self.client.get("/api/admin/audit")
        self.assertEqual(audit.status_code, 200)
        self.assertGreaterEqual(audit.json()["total"], 1)

        with Session(create_engine(get_app_settings().database_url_sync)) as session:
            user = session.get(User, __import__("uuid").UUID(user_id))
            user.status = "disabled"
            session.commit()
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 401)

    def test_path_traversal_filename(self):
        name = random_filename("png")
        self.assertNotIn("..", name)
        self.assertFalse(name.startswith("/"))
        with self.assertRaises(ValueError):
            from backend.app.core.storage import LocalStorageBackend

            LocalStorageBackend(Path(tempfile.mkdtemp())).path_for("../etc/passwd")

    def test_chroma_user_filter(self):
        from ai_engine.rag.retriever import search

        embedder = type("E", (), {"embed": staticmethod(lambda queries: [[0.1, 0.2]])})()
        with patch("ai_engine.rag.retriever.get_embedder", return_value=embedder):
            with patch("ai_engine.rag.store.query", return_value=[]) as mocked:
                search(["课堂提问"], ["eval_reports"], user_id="bbb")
                mocked.assert_called()
                self.assertEqual(mocked.call_args.kwargs.get("where"), {"user_id": "bbb"})
            with patch("ai_engine.rag.store.query") as mocked:
                search(["课堂提问"], ["eval_reports"], user_id=None)
                mocked.assert_not_called()
            with patch("ai_engine.rag.store.query", return_value=[]) as mocked:
                search(
                    ["课堂提问"],
                    ["eval_reports"],
                    user_id="bbb",
                    eval_task_ids=["task-1", "task-2"],
                )
                self.assertEqual(
                    mocked.call_args.kwargs.get("where"),
                    {
                        "$and": [
                            {"user_id": "bbb"},
                            {"task_id": {"$in": ["task-1", "task-2"]}},
                        ]
                    },
                )
            with patch("ai_engine.rag.store.query") as mocked:
                search(
                    ["课堂提问"],
                    ["eval_reports"],
                    user_id="bbb",
                    eval_task_ids=[],
                )
                mocked.assert_not_called()


class AlembicTest(unittest.TestCase):
    @unittest.skipUnless(_postgres_ready(), "PostgreSQL 未启动，跳过 Alembic 测试")
    def test_upgrade_and_downgrade(self):
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")


if __name__ == "__main__":
    unittest.main()
