import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from studio.auth import AuthStore
from studio.workspace import WorkspaceStore, ModelGateway, make_router


class TeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "test.db"
        self.store = WorkspaceStore(self.path)
        self.auth = AuthStore(self.path)
        self.uid = self.auth.add_user("one", "One", "test-password-one", "admin")
        self.other = self.auth.add_user("two", "Two", "test-password-two")
        self.actor = {"id": self.uid, "name": "One", "role": "admin"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_session_password_storage_expiry_and_logout(self):
        token, error = self.auth.login("one", "test-password-one", "local")
        self.assertIsNone(error)
        self.assertEqual("One", self.auth.user(token)["name"])
        with self.auth.connect() as c:
            self.assertNotIn("test-password-one", str([tuple(r) for r in c.execute("SELECT * FROM users")]))
            self.assertNotIn(token, str([tuple(r) for r in c.execute("SELECT * FROM sessions")]))
            c.execute("UPDATE sessions SET expires=0")
        self.assertIsNone(self.auth.user(token))
        token, _ = self.auth.login("one", "test-password-one", "local")
        self.auth.logout(token)
        self.assertIsNone(self.auth.user(token))

    def test_failed_logins_are_limited(self):
        for _ in range(20):
            self.assertEqual("invalid", self.auth.login("missing", "wrong", "local")[1])
        self.assertEqual("limited", self.auth.login("one", "test-password-one", "local")[1])

    def test_membership_filter_and_author(self):
        project = self.store.create({"title": "Shared", "brief": "English drama"}, self.actor)
        self.assertTrue(self.auth.member(project["id"], self.other))
        self.assertEqual("One", project["versions"][0]["author_name"])
        with self.auth.connect() as c:
            c.execute("DELETE FROM project_members WHERE user_id=?", (self.other,))
        self.assertFalse(self.auth.member(project["id"], self.other))
        self.assertEqual([], self.store.projects(self.other))
        self.assertEqual(1, len(self.store.projects(self.uid)))

    def test_ai_result_survives_concurrent_save(self):
        project = self.store.create({"title": "Shared", "brief": "English drama"}, self.actor)
        branch = project["branches"][0]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            gateway = ModelGateway()
        def concurrent(*args):
            self.store.append(project["id"], branch["id"], branch["head"], "Other edit", "Saved", "Other member draft", "manual", "", {}, {"id":self.other,"name":"Two"})
            return "Generated", "Paid generation preserved", "deepseek", "test-model"
        endpoint = next(r.endpoint for r in make_router(self.store, gateway).routes if r.path.endswith("/versions"))
        with patch.object(gateway, "generate", side_effect=concurrent):
            result = endpoint(project["id"], {"action":"chat","branch_id":branch["id"],"parent_id":branch["head"],"instruction":"Write"})
        self.assertIn("recovered_branch_id", result)
        self.assertEqual(2, len(result["branches"]))
        main = next(b for b in result["branches"] if b["id"] == branch["id"])
        alternate = next(b for b in result["branches"] if b["id"] == result["recovered_branch_id"])
        by_id = {v["id"]:v for v in result["versions"]}
        self.assertEqual("Other member draft", by_id[main["head"]]["document"])
        self.assertEqual("Paid generation preserved", by_id[alternate["head"]]["document"])
        self.assertEqual("deepseek", by_id[alternate["head"]]["provider"])

    def test_old_database_migrates_with_backup(self):
        old = Path(self.tmp.name) / "old.db"
        c = sqlite3.connect(old)
        c.execute("CREATE TABLE w_versions(id TEXT PRIMARY KEY, project_id TEXT, branch_id TEXT, parent_id TEXT, instruction TEXT, reply TEXT, document TEXT, provider TEXT, model TEXT, prompt_json TEXT, created_at TEXT)")
        c.execute("INSERT INTO w_versions VALUES('v','p','b',NULL,'i','r','Original draft','manual','','{}','date')")
        c.commit(); c.close()
        migrated = WorkspaceStore(old)
        with migrated.connect() as c:
            row = c.execute("SELECT * FROM w_versions").fetchone()
            self.assertEqual("Original draft", row["document"])
            self.assertEqual("历史记录", row["author_name"])
        self.assertEqual(1, len(list(Path(self.tmp.name).glob("old.db.pre-v03-*.db"))))
        WorkspaceStore(old)
        self.assertEqual(1, len(list(Path(self.tmp.name).glob("old.db.pre-v03-*.db"))))
