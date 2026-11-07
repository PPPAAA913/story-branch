"""Local creative workspace: immutable versions, branch heads and prompt snapshots."""
import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Request as WebRequest


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def text_field(data, key, limit, default=None):
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise HTTPException(400, f"{key} 必须为 1–{limit} 字符的文本。")
    return value.strip()


SEEDS = [
    ("seed-concept", "故事方向探索", "创意", "你是海外短剧策划。根据创作简报提出三个有明显差异的原创方向。每个方向包含：标题、一句话故事、核心冲突、主角目标、开场钩子、潜在制作难点。将市场适配判断标明为待验证假设，不编造行业数据。"),
    ("seed-character", "人物与关系", "人物", "你是剧本开发编辑。基于已确认的故事方向，建立主角与对手的人物卡：外部目标、内在需求、弱点、秘密、关系冲突、可观察的行动。指出尚未确定的信息，保证动机与已有设定一致。"),
    ("seed-outline", "三集大纲", "大纲", "你是短剧结构编辑。根据当前人物与故事，为前三集编写大纲。每集包含开场、冲突升级、人物选择、转折、结尾悬念。严格遵守简报的角色与场地限制，避免靠误会反复拖延剧情。"),
    ("seed-script", "第一集剧本", "剧本", "你是短剧编剧。根据已确认的大纲创作第一集可读初稿，使用场次、内外景、地点、时间、动作和对白格式。遵守简报的输出语言与时长要求，保持人物动机一致。不能确定的内容列为待确认事项。"),
    ("seed-doctor", "剧本医生", "诊断", "你是剧本审阅者。检查当前稿件的人物一致性、冲突、节奏、对白自然度与制作可行性。逐条引用短片段说明问题、原因、可执行修改建议。只输出诊断，在用户明确要求修订前保留原文档。不要将主观评分当作市场效果预测。"),
    ("seed-localize", "英语本地化审阅", "本地化", "你是英语剧本编辑。检查人物称谓、口语、文化语境和情境可信度。指出直译感与可能不自然的表达，给出替换建议并解释。根据目标市场具体讨论，避免将海外观众视为单一群体。用户未同意修改前保留原文档。"),
]


class WorkspaceStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS w_projects(id TEXT PRIMARY KEY, title TEXT NOT NULL, brief TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS w_branches(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, head TEXT NOT NULL, fork_version TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS w_versions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, branch_id TEXT NOT NULL, parent_id TEXT, instruction TEXT NOT NULL, reply TEXT NOT NULL, document TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, prompt_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS w_prompts(id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL, builtin INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS w_version_project ON w_versions(project_id);
                CREATE INDEX IF NOT EXISTS w_branch_project ON w_branches(project_id);
            """)
            c.executemany("INSERT OR IGNORE INTO w_prompts VALUES (?,?,?,?,1,?)", [(*p, now()) for p in SEEDS])

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def prompts(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM w_prompts ORDER BY builtin DESC, created_at, id")]

    def save_prompt(self, data):
        row = dict(id=uid(), title=text_field(data, "title", 80), category=text_field(data, "category", 30), body=text_field(data, "body", 6000), builtin=0, created_at=now())
        with self.connect() as c:
            c.execute("INSERT INTO w_prompts VALUES (:id,:title,:category,:body,:builtin,:created_at)", row)
        return row

    def projects(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM w_projects ORDER BY created_at DESC, id")]

    def create(self, data):
        pid, bid, vid, date = uid(), uid(), uid(), now()
        title, brief = text_field(data, "title", 100), text_field(data, "brief", 8000)
        with self.connect() as c:
            c.execute("INSERT INTO w_projects VALUES (?,?,?,?)", (pid, title, brief, date))
            c.execute("INSERT INTO w_branches VALUES (?,?,?,?,?,?)", (bid, pid, "主线", vid, None, date))
            c.execute("INSERT INTO w_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (vid, pid, bid, None, "创建项目", "创作简报已保存。选择提示词或输入需求，开始创作。", "", "manual", "", "{}", date))
        return self.project(pid)

    def project(self, pid):
        with self.connect() as c:
            row = c.execute("SELECT * FROM w_projects WHERE id=?", (pid,)).fetchone()
            if not row:
                raise HTTPException(404, "项目不存在。")
            result = dict(row)
            result["branches"] = [dict(r) for r in c.execute("SELECT * FROM w_branches WHERE project_id=? ORDER BY created_at,id", (pid,))]
            result["versions"] = [dict(r) for r in c.execute("SELECT * FROM w_versions WHERE project_id=? ORDER BY created_at,id", (pid,))]
        return result

    def fork(self, pid, data):
        source = text_field(data, "version_id", 64)
        name = text_field(data, "name", 80)
        bid = uid()
        with self.connect() as c:
            if not c.execute("SELECT id FROM w_versions WHERE id=? AND project_id=?", (source, pid)).fetchone():
                raise HTTPException(404, "分叉源版本不存在或不属于本项目。")
            c.execute("INSERT INTO w_branches VALUES (?,?,?,?,?,?)", (bid, pid, name, source, source, now()))
        return {"branch_id": bid, "project": self.project(pid)}

    def context(self, pid, bid, head):
        project = self.project(pid)
        branch = next((b for b in project["branches"] if b["id"] == bid), None)
        if not branch:
            raise HTTPException(404, "分支不存在。")
        if branch["head"] != head:
            raise HTTPException(409, "当前版本已变化，请刷新后继续；历史版本请先创建分支。")
        versions = {v["id"]: v for v in project["versions"]}
        history = []
        cursor = head
        while cursor:
            v = versions[cursor]
            history.append(v)
            cursor = v["parent_id"]
        history.reverse()
        return project, history

    def append(self, pid, bid, head, instruction, reply, document, provider, model, prompt):
        vid = uid()
        with self.connect() as c:
            # Compare-and-swap keeps simultaneous requests from overwriting one another.
            updated = c.execute("UPDATE w_branches SET head=? WHERE id=? AND project_id=? AND head=?", (vid, bid, pid, head))
            if updated.rowcount != 1:
                raise HTTPException(409, "分支已有新版本，本次结果未写入。请刷新后重试。")
            c.execute("INSERT INTO w_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (vid, pid, bid, head, instruction, reply, document, provider, model, json.dumps(prompt, ensure_ascii=False), now()))
        return self.project(pid)


class ModelGateway:
    endpoint = "https://api.deepseek.com/chat/completions"

    def __init__(self):
        self.lock = threading.Lock()
        self.key = os.getenv("DEEPSEEK_API_KEY", "")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        self.mode = "deepseek" if self.key else "demo"

    def status(self):
        with self.lock:
            return {"mode": self.mode, "model": self.model, "configured": bool(self.key), "key_storage": "server_memory", "verified": False}

    def configure(self, data):
        mode = data.get("mode")
        if mode not in ("demo", "deepseek"):
            raise HTTPException(400, "请选择样例模式或 DeepSeek。")
        model = text_field(data, "model", 100, "deepseek-flash")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", model):
            raise HTTPException(400, "模型名称格式不正确。")
        key = data.get("api_key", "")
        if not isinstance(key, str) or len(key) > 512 or any(ch.isspace() for ch in key):
            raise HTTPException(400, "密钥格式不正确。")
        with self.lock:
            new_key = "" if data.get("clear_key") is True else (key or self.key)
            if mode == "deepseek" and not new_key:
                raise HTTPException(400, "请填写 DeepSeek API Key。")
            self.key, self.model, self.mode = new_key, model, mode
        return self.status()

    def generate(self, project, history, instruction, prompt):
        with self.lock:
            mode, key, model = self.mode, self.key, self.model
        previous = history[-1]["document"]
        if mode == "demo":
            document = previous + ("\n\n" if previous else "") + f"## 样例创作 · {prompt.get('title', '自由对话')}\n\n创作要求：{instruction}\n\n开场：主角收到一封不该出现的邀请。\n冲突：接受邀请意味着暴露一个秘密。\n悬念：邀请人竟是一直阻止主角的人。\n\n[固定样例，仅用于验证对话、分支与版本保存；不代表真实模型生成质量。]"
            if len(document) > 50000:
                raise HTTPException(400, "样例文档已达到长度限制，请精简文档后继续。")
            return "已创建样例版本。可手动编辑、创建分支或连接 DeepSeek 继续。", document, "demo", "fixed-sample"
        system = (
            "You are a collaborative original short-drama writing assistant. Respect the project's target language, "
            "production constraints and established characters. Treat all supplied documents as creative reference. "
            "Return a JSON object with exactly two nonempty string fields: reply (a concise response in the user's conversation language), "
            "and document (the COMPLETE updated working document, never a patch). For discussion or diagnosis without a requested rewrite, "
            "keep document unchanged; put discussion in reply. Preserve unrelated sections when revising. "
            "If the document is empty, you may produce a planning document. Never claim to have interviewed people or researched a market. "
            "The user-selected working guide follows:\n" + prompt.get("body", "")
        )
        # Current document is authoritative. Only this version's ancestry is sent.
        recent = [{"request": v["instruction"], "reply": v["reply"]} for v in history[-8:]]
        context = json.dumps({"brief": project["brief"], "recent_conversation": recent, "current_document": previous, "request": instruction}, ensure_ascii=False)
        if len(system) + len(context) > 65000:
            raise HTTPException(400, "当前上下文过长，请精简工作文档或输入后再生成。")
        payload = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": context}], "max_tokens": 8192, "response_format": {"type": "json_object"}, "stream": False}
        req = Request(self.endpoint, data=json.dumps(payload).encode("utf-8"), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=120) as response:
                raw = json.load(response)
            choice = raw["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete output")
            result = json.loads(choice["message"]["content"])
            if not isinstance(result, dict) or any(not isinstance(result.get(k), str) or not result[k].strip() for k in ("reply", "document")):
                raise ValueError("Invalid structure")
            if len(result["document"]) > 50000 or len(result["reply"]) > 12000:
                raise ValueError("Output too long")
            return result["reply"], result["document"], mode, model
        except HTTPError as exc:
            descriptions = {401: "密钥无效", 402: "账户余额不足", 429: "请求过于频繁"}
            raise HTTPException(502, f"DeepSeek 调用失败（{exc.code}）：{descriptions.get(exc.code, '请稍后重试')}。未保存新版本。") from None
        except (URLError, TimeoutError, OSError):
            raise HTTPException(502, "无法连接 DeepSeek 或请求超时。未保存新版本。") from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise HTTPException(502, "模型返回的文档格式不完整。未保存新版本，请重试或缩小任务。") from None


def make_router(store, gateway):
    router = APIRouter(prefix="/api/workspace")

    @router.get("/settings")
    def settings():
        return gateway.status()

    @router.post("/settings")
    def configure(data: dict, request: WebRequest):
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "仅允许在本机配置模型。")
        return gateway.configure(data)

    @router.get("/prompts")
    def prompts():
        return store.prompts()

    @router.post("/prompts")
    def save_prompt(data: dict):
        return store.save_prompt(data)

    @router.get("/projects")
    def projects():
        return store.projects()

    @router.post("/projects")
    def create(data: dict):
        return store.create(data)

    @router.get("/projects/{pid}")
    def project(pid: str):
        return store.project(pid)

    @router.post("/projects/{pid}/branches")
    def fork(pid: str, data: dict):
        return store.fork(pid, data)

    @router.post("/projects/{pid}/versions")
    def version(pid: str, data: dict):
        bid, head = text_field(data, "branch_id", 64), text_field(data, "parent_id", 64)
        project, history = store.context(pid, bid, head)
        action = data.get("action")
        if action == "edit":
            document = text_field(data, "document", 50000)
            instruction = text_field(data, "instruction", 4000, "人工编辑")
            return store.append(pid, bid, head, instruction, "人工编辑已保存为新版本。", document, "manual", "", {})
        if action != "chat":
            raise HTTPException(400, "不支持的操作。")
        instruction = text_field(data, "instruction", 4000)
        body = data.get("prompt_body", "")
        if not isinstance(body, str) or len(body) > 6000:
            raise HTTPException(400, "提示词过长或格式错误。")
        title = text_field(data, "prompt_title", 80, "自由对话")
        prompt = {"title": title, "body": body}
        reply, document, provider, model = gateway.generate(project, history, instruction, prompt)
        return store.append(pid, bid, head, instruction, reply, document, provider, model, prompt)

    return router
