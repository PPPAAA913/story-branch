import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from studio.workspace import ModelGateway, WorkspaceStore, make_router


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkspaceStore(Path(self.temp.name) / "test.db")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            self.gateway = ModelGateway()
        self.p = self.store.create({"title": "Test story", "brief": "Two rivals. English script, Chinese discussion."})
        self.bid = self.p["branches"][0]["id"]
        self.root = self.p["branches"][0]["head"]

    def tearDown(self):
        self.temp.cleanup()

    def append(self, bid, head, doc, instruction="revise"):
        return self.store.append(self.p["id"], bid, head, instruction, "reply", doc, "demo", "sample", {"body": "guide v1"})

    def test_fork_isolates_future_context_and_survives_reload(self):
        main = self.append(self.bid, self.root, "Main future", "main-only instruction")
        main_head = main["branches"][0]["head"]
        fork = self.store.fork(self.p["id"], {"version_id": self.root, "name": "Alternative"})
        alternate = self.append(fork["branch_id"], self.root, "Alternate future")
        alt_head = next(b["head"] for b in alternate["branches"] if b["id"] == fork["branch_id"])
        later = WorkspaceStore(self.store.path)
        _, history = later.context(self.p["id"], fork["branch_id"], alt_head)
        self.assertEqual([self.root, alt_head], [v["id"] for v in history])
        self.assertNotIn("main-only instruction", str(history))
        self.assertEqual("Main future", later.context(self.p["id"], self.bid, main_head)[1][-1]["document"])
        self.assertEqual("", later.context(self.p["id"], self.bid, main_head)[1][0]["document"])

    def test_stale_append_does_not_add_or_overwrite_version(self):
        self.append(self.bid, self.root, "First winner")
        with self.assertRaises(HTTPException) as err:
            self.append(self.bid, self.root, "Stale loser")
        self.assertEqual(409, err.exception.status_code)
        p = self.store.project(self.p["id"])
        self.assertEqual(2, len(p["versions"]))
        self.assertEqual("First winner", p["versions"][-1]["document"])

    def test_cross_project_fork_rejected(self):
        other = self.store.create({"title": "Other", "brief": "Other brief"})
        with self.assertRaises(HTTPException) as err:
            self.store.fork(other["id"], {"version_id": self.root, "name": "Invalid"})
        self.assertEqual(404, err.exception.status_code)

    def test_prompt_library_and_snapshots_are_independent(self):
        prompts = self.store.prompts()
        self.assertEqual(8, len(prompts))
        custom = self.store.save_prompt({"title": "Custom", "category": "test", "body": "My original guide"})
        self.append(self.bid, self.root, "Document")
        self.store.save_prompt({"title": "Custom v2", "category": "test", "body": "Changed guide"})
        later = WorkspaceStore(self.store.path)
        self.assertEqual(10, len(later.prompts()))
        self.assertEqual("My original guide", next(p["body"] for p in later.prompts() if p["id"] == custom["id"]))
        self.assertEqual("guide v1", json.loads(later.project(self.p["id"])["versions"][-1]["prompt_json"])["body"])

    def test_key_never_returned_and_can_be_cleared(self):
        result = self.gateway.configure({"mode": "deepseek", "api_key": "private-test-key", "model": "test-model"})
        self.assertTrue(result["configured"])
        self.assertNotIn("private-test-key", json.dumps(result))
        self.gateway.configure({"mode": "demo", "clear_key": True, "model": "test-model"})
        self.assertFalse(self.gateway.status()["configured"])
        with self.assertRaises(HTTPException):
            self.gateway.configure({"mode": "deepseek"})

    def response(self, content, reason="stop"):
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": reason, "message": {"content": content}}]}).encode())

    def test_deepseek_request_uses_key_and_selected_context(self):
        self.gateway.configure({"mode": "deepseek", "api_key": "test-key", "model": "test-model"})
        _, history = self.store.context(self.p["id"], self.bid, self.root)
        with patch("studio.workspace.urlopen", return_value=self.response(json.dumps({"reply": "Done", "document": "Full draft"}))) as call:
            result = self.gateway.generate(self.p, history, "Write scene one", {"body": "Use two locations"})
        req = call.call_args.args[0]
        self.assertEqual("https://api.deepseek.com/chat/completions", req.full_url)
        self.assertEqual("Bearer test-key", req.get_header("Authorization"))
        payload = json.loads(req.data)
        self.assertEqual("test-model", payload["model"])
        self.assertIn("Use two locations", payload["messages"][0]["content"])
        self.assertEqual("Full draft", result[1])

    def test_failed_generation_does_not_commit(self):
        self.gateway.configure({"mode": "deepseek", "api_key": "test-key", "model": "test-model"})
        endpoint = next(r.endpoint for r in make_router(self.store, self.gateway).routes if r.path.endswith('/versions'))
        for content, reason in [("not json", "stop"), (json.dumps({"reply":"Done", "document":"Partial"}), "length")]:
            with self.subTest(reason=reason), patch("studio.workspace.urlopen", return_value=self.response(content, reason)):
                with self.assertRaises(HTTPException) as err:
                    endpoint(self.p["id"], {"action": "chat", "branch_id": self.bid, "parent_id": self.root, "instruction": "Write"})
                self.assertEqual(502, err.exception.status_code)
        self.assertEqual(1, len(self.store.project(self.p["id"])["versions"]))
        self.assertEqual(self.root, self.store.project(self.p["id"])["branches"][0]["head"])


if __name__ == "__main__":
    unittest.main()
