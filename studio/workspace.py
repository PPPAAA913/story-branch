"""Local creative workspace: immutable versions, branch heads and prompt snapshots."""
import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .route import STAGES, LABELS, GUIDES, empty_route, statuses, revise, require_upstream
from .writing import SEEDS, build_pack, catalog

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




class WorkspaceStore:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Snapshot existing databases before the first additive authorship migration.
        if Path(path).exists():
            with closing(sqlite3.connect(self.path)) as source:
                columns = {row[1] for row in source.execute("PRAGMA table_info(w_versions)")}
                if columns and ("author_id" not in columns or "route_json" not in columns):
                    with closing(sqlite3.connect(self.path + (".pre-v03-" if "author_id" not in columns else ".pre-v04-") + uid()[:8] + ".db")) as target:
                        source.backup(target)
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS w_projects(id TEXT PRIMARY KEY, title TEXT NOT NULL, brief TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS w_branches(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, head TEXT NOT NULL, fork_version TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS w_versions(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, branch_id TEXT NOT NULL, parent_id TEXT, instruction TEXT NOT NULL, reply TEXT NOT NULL, document TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, prompt_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS w_prompts(id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, body TEXT NOT NULL, builtin INTEGER NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS w_version_project ON w_versions(project_id);
                CREATE INDEX IF NOT EXISTS w_branch_project ON w_branches(project_id);
            """)
            c.executemany("""INSERT INTO w_prompts VALUES (?,?,?,?,1,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,body=excluded.body
                WHERE w_prompts.builtin=1""", [(*p, now()) for p in SEEDS])
            columns = {row[1] for row in c.execute("PRAGMA table_info(w_versions)")}
            if "author_id" not in columns:
                c.execute("ALTER TABLE w_versions ADD COLUMN author_id TEXT NOT NULL DEFAULT ''")
                c.execute("ALTER TABLE w_versions ADD COLUMN author_name TEXT NOT NULL DEFAULT '历史记录'")
            if "route_json" not in columns:
                c.execute("ALTER TABLE w_versions ADD COLUMN route_json TEXT NOT NULL DEFAULT '{}'")
                c.execute("ALTER TABLE w_versions ADD COLUMN stage TEXT NOT NULL DEFAULT 'legacy'")
                for row in c.execute("SELECT v.id,v.document,p.brief FROM w_versions v JOIN w_projects p ON p.id=v.project_id").fetchall():
                    route = empty_route(row["brief"], "legacy-brief")
                    route["legacy"] = row["document"]
                    c.execute("UPDATE w_versions SET route_json=? WHERE id=?", (json.dumps(route, ensure_ascii=False), row["id"]))

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

    def projects(self, user_id=None):
        with self.connect() as c:
            if user_id:
                return [dict(r) for r in c.execute("SELECT p.* FROM w_projects p JOIN project_members m ON m.project_id=p.id WHERE m.user_id=? ORDER BY p.created_at DESC,p.id", (user_id,))]
            return [dict(r) for r in c.execute("SELECT * FROM w_projects ORDER BY created_at DESC, id")]

    def create(self, data, actor=None):
        pid, bid, vid, date = uid(), uid(), uid(), now()
        title, brief = text_field(data, "title", 100), text_field(data, "brief", 8000)
        with self.connect() as c:
            c.execute("INSERT INTO w_projects VALUES (?,?,?,?)", (pid, title, brief, date))
            c.execute("INSERT INTO w_branches VALUES (?,?,?,?,?,?)", (bid, pid, "主线", vid, None, date))
            c.execute("INSERT INTO w_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (vid, pid, bid, None, "创建项目", "创作简报已保存。选择提示词或输入需求，开始创作。", "", "manual", "", "{}", date, (actor or {}).get("id", ""), (actor or {}).get("name", "本地创作者"), json.dumps(empty_route(brief, vid), ensure_ascii=False), "brief"))
            if actor:
                c.execute("INSERT INTO project_members SELECT ?,id FROM users", (pid,))
        return self.project(pid)

    def project(self, pid):
        with self.connect() as c:
            row = c.execute("SELECT * FROM w_projects WHERE id=?", (pid,)).fetchone()
            if not row:
                raise HTTPException(404, "项目不存在。")
            result = dict(row)
            result["branches"] = [dict(r) for r in c.execute("SELECT * FROM w_branches WHERE project_id=? ORDER BY created_at,id", (pid,))]
            result["versions"] = [dict(r) for r in c.execute("SELECT * FROM w_versions WHERE project_id=? ORDER BY created_at,id", (pid,))]
        for version in result["versions"]:
            version["route"] = json.loads(version.pop("route_json"))
            if not version["route"]:
                version["route"] = empty_route(result["brief"], "legacy-brief")
                version["route"]["legacy"] = version["document"]
            version["stage_status"] = statuses(version["route"])
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

    def append(self, pid, bid, head, instruction, reply, document, provider, model, prompt, actor=None, stage="legacy", action="edit"):
        vid = uid()
        with self.connect() as c:
            row = c.execute("SELECT route_json FROM w_versions WHERE id=? AND project_id=?", (head, pid)).fetchone()
            if not row:
                raise HTTPException(404, "源版本不存在。")
            route = revise(json.loads(row["route_json"]), stage, document, vid, action)
            # Compare-and-swap keeps simultaneous requests from overwriting one another.
            updated = c.execute("UPDATE w_branches SET head=? WHERE id=? AND project_id=? AND head=?", (vid, bid, pid, head))
            if updated.rowcount != 1:
                raise HTTPException(409, "分支已有新版本，本次结果未写入。请刷新后重试。")
            c.execute("INSERT INTO w_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (vid, pid, bid, head, instruction, reply, document, provider, model, json.dumps(prompt, ensure_ascii=False), now(), (actor or {}).get("id", ""), (actor or {}).get("name", "本地创作者"), json.dumps(route, ensure_ascii=False), stage))
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
        writing = prompt.get("writing") or build_pack(project.get("active_stage", "legacy"))
        task_mode = writing["mode"]
        if mode == "demo":
            if task_mode in {"discuss", "critique", "polish"}:
                return "固定样例模式：已接入写作方法与任务模式；未执行真实讨论、审阅或润色。当前稿件保持原样，请配置模型后验证效果。", previous, "demo", "fixed-sample"
            samples = {
                "brief": "目标地区：美国英语市场（创作假设）\n题材：都市情感\n讨论语言：中文\n剧本语言：英文，附中文梗概\n制作约束：四名演员、两个场地、首集约90秒。",
                "concept": "方向一：公开资助者身份，争取创作自主权。\n方向二：暂时保留秘密，用合作检验信任。\n方向三：拒绝资助，独立完成作品。\n\n请选定一个方向并将选择写入成果后确认。",
                "character": "Maya：年轻制片人，渴望独立完成作品，担心被资助者控制。\nAlex：竞争对手，曾匿名提供帮助，希望修复双方信任。\n冲突：对创作自主权与帮助边界的理解不同。",
                "outline": "第1集：Maya发现资助文件上的熟悉签名，决定当面对质；结尾Alex带来另一份协议。\n第2集：Maya提出合作条件，Alex必须放弃否决权；结尾投资人到访。\n第3集：Maya公开自己的决定，双方承担合作的代价；结尾揭示投资人的新要求。",
                "script": "EPISODE 1 — THE SIGNATURE\n\nINT. PRODUCTION OFFICE — NIGHT\nMAYA studies a signature on a funding agreement. ALEX appears in the doorway.\n\nMAYA\nYou paid for this?\n\nALEX\nI paid for a chance. The film is yours.\n\nMAYA\nThen take your name off the approval clause.\n\nAlex places a second agreement on the desk. Maya doesn't touch it.\n\nCUT TO BLACK.\n\n中文梗概：Maya发现Alex匿名资助了项目，要求他放弃审批权；Alex拿出新协议，引出下一集悬念。",
                "review": "审阅样例：检查Maya争取创作自主权的动机是否贯穿人物、大纲与首集。确认协议中的审批权是否已在前文铺垫。回到对应阶段手动修订，再确认依赖。",
            }
            if project.get("active_stage") in samples:
                document = samples[project["active_stage"]] + "\n\n[固定样例，仅验证阶段流程，不代表模型生成质量。]\n本轮要求：" + instruction
                return "已生成本阶段固定样例；请检查后确认。", document, "demo", "fixed-sample"
            document = previous + ("\n\n" if previous else "") + f"## 样例创作 · {prompt.get('title', '自由对话')}\n\n创作要求：{instruction}\n\n开场：主角收到一封不该出现的邀请。\n冲突：接受邀请意味着暴露一个秘密。\n悬念：邀请人竟是一直阻止主角的人。\n\n[固定样例，仅用于验证对话、分支与版本保存；不代表真实模型生成质量。]"
            if len(document) > 50000:
                raise HTTPException(400, "样例文档已达到长度限制，请精简文档后继续。")
            return "已创建样例版本。可手动编辑、创建分支或连接 DeepSeek 继续。", document, "demo", "fixed-sample"
        system = (
            "You are a collaborative original short-drama writing assistant. Respect the project's target language, "
            "production constraints and established characters. Treat all supplied documents as creative reference. "
            "Return a JSON object with exactly two string fields: reply (a nonempty concise response in Chinese), "
            "and document (the COMPLETE updated working document, never a patch). For discussion or diagnosis without a requested rewrite, "
            "keep document unchanged including an empty string; put discussion in reply. For write/polish, document must be nonempty. Preserve unrelated sections when revising. "
            "If the document is empty, you may produce a planning document. Never claim to have interviewed people or researched a market. "
            "Reply in Chinese. Only update the active stage document. Preserve other stages as read-only reference. "
            + GUIDES.get(project.get("active_stage"), "") + "\n" + writing["instructions"] + "\nThe user-selected working guide (subordinate to the task mode) follows:\n" + prompt.get("body", "")
        )
        # Current document is authoritative. Only this version's ancestry is sent.
        recent = [{"request": v["instruction"], "reply": v["reply"]} for v in history[-8:]]
        context = json.dumps({"brief": project["brief"], "recent_conversation": recent, "current_document": previous, "request": instruction, "active_stage": project.get("active_stage"), "confirmed_upstream": project.get("upstream", {}), "unconfirmed_reference": project.get("unconfirmed_reference", {}), "task_mode": task_mode}, ensure_ascii=False)
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
            if not isinstance(result, dict) or not isinstance(result.get("reply"), str) or not result["reply"].strip() or not isinstance(result.get("document"), str):
                raise ValueError("Invalid structure")
            if task_mode in {"discuss", "critique"}:
                # Enforce read-only intent even if the model ignores the selected mode.
                result["document"] = previous
            elif not result["document"].strip():
                raise ValueError("Empty draft")
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
        if getattr(request.state, "user", {}).get("role") != "admin":
            raise HTTPException(403, "只有管理员可以配置模型。")
        return gateway.configure(data)

    @router.get("/writing")
    def writing_catalog():
        return catalog()

    @router.get("/prompts")
    def prompts():
        return store.prompts()

    @router.post("/prompts")
    def save_prompt(data: dict):
        return store.save_prompt(data)

    @router.get("/projects")
    def projects(request: WebRequest):
        return store.projects(request.state.user["id"])

    @router.post("/projects")
    def create(data: dict, request: WebRequest):
        return store.create(data, request.state.user)

    @router.get("/projects/{pid}")
    def project(pid: str):
        return store.project(pid)

    @router.post("/projects/{pid}/branches")
    def fork(pid: str, data: dict):
        return store.fork(pid, data)

    @router.post("/projects/{pid}/versions")
    def version(pid: str, data: dict, request: WebRequest = None):
        actor = request.state.user if request else None
        bid, head = text_field(data, "branch_id", 64), text_field(data, "parent_id", 64)
        project, history = store.context(pid, bid, head)
        action = data.get("action")
        stage = data.get("stage", "legacy")
        if stage not in STAGES + ["legacy"]:
            raise HTTPException(400, "未知创作阶段。")
        route = history[-1]["route"]
        if action == "confirm":
            if stage == "legacy":
                raise HTTPException(400, "历史稿件请整理到对应创作阶段后确认。")
            return store.append(pid, bid, head, "确认：" + LABELS[stage], "已确认当前成果及其上游依据。", route["documents"][stage]["text"], "manual", "", {}, actor, stage, "confirm")
        if action == "edit":
            document = text_field(data, "document", 8000 if stage == "brief" else 50000)
            instruction = text_field(data, "instruction", 4000, "人工编辑")
            return store.append(pid, bid, head, instruction, "人工编辑已保存为新版本。", document, "manual", "", {}, actor, stage)
        if action != "chat":
            raise HTTPException(400, "不支持的操作。")
        instruction = text_field(data, "instruction", 4000)
        body = data.get("prompt_body", "")
        if not isinstance(body, str) or len(body) > 6000:
            raise HTTPException(400, "提示词过长或格式错误。")
        title = text_field(data, "prompt_title", 80, "自由对话")
        writing = build_pack(stage, data.get("writing_mode", "write"),
                             {s: route["documents"][s]["revision"] for s in STAGES[:STAGES.index(stage)]} if stage != "legacy" else {})
        prompt = {"title": title, "body": body, "writing": writing}
        if stage != "legacy":
            if writing["mode"] in {"write", "polish"}:
                require_upstream(route, stage)
            project = dict(project, brief=route["documents"]["brief"]["text"], active_stage=stage,
                           upstream={s: route["documents"][s]["text"] for s in STAGES[:STAGES.index(stage)] if statuses(route)[s] == "confirmed"},
                           unconfirmed_reference={s: {"text": route["documents"][s]["text"], "status": statuses(route)[s]} for s in STAGES[:STAGES.index(stage)] if statuses(route)[s] != "confirmed"})
            history = [dict(v) for v in history if v["stage"] == stage] or [dict(history[-1])]
            history[-1] = dict(history[-1], document=route["documents"][stage]["text"])
        reply, document, provider, model = gateway.generate(project, history, instruction, prompt)
        if writing["mode"] in {"discuss", "critique"}:
            document = route["legacy"] if stage == "legacy" else route["documents"][stage]["text"]
        if stage == "brief" and len(document) > 8000:
            raise HTTPException(502, "模型生成的简报过长，请缩小任务。未保存新版本。")
        try:
            return store.append(pid, bid, head, instruction, reply, document, provider, model, prompt, actor, stage, "chat")
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
            # Preserve paid generation output when another editor advances the branch.
            fork = store.fork(pid, {"version_id": head, "name": "待合并 · " + (actor or {}).get("name", "生成结果") + " · " + now()[11:19]})
            result = store.append(pid, fork["branch_id"], head, instruction, reply, document, provider, model, prompt, actor, stage, "chat")
            result["recovered_branch_id"] = fork["branch_id"]
            return result

    return router
