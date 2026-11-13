"""Immutable story-route snapshots and explicit upstream review dependencies."""
from copy import deepcopy
from fastapi import HTTPException
from .contracts import STAGES, LABELS, CONTRACTS, issues

GUIDES = {s: c["role"] for s, c in CONTRACTS.items()}


def blank_document():
    return {"text": "", "revision": None, "confirmed": False, "dependencies": {}}


def normalize(route):
    """Read projection only: never rewrite immutable historical database rows."""
    result = deepcopy(route)
    docs = result.setdefault("documents", {})
    old = result.get("schema_version") != 2
    if "review" in docs:
        result["archived_review"] = docs.pop("review")
    for s in STAGES:
        docs.setdefault(s, blank_document())
        if old:
            docs[s]["confirmed"] = False
    result.setdefault("legacy", "")
    result.setdefault("selected_concept", "")
    if old:
        result["migration_notice"] = "旧路线内容已保留；请按新阶段要求整理并重新确认。旧审阅报告在历史审阅中，首集分场需补充。"
    result["schema_version"] = 2
    return result


def stage_issues(route, stage):
    return issues(stage, route["documents"][stage]["text"], route.get("selected_concept", ""))


def upstream_text(route, stage):
    # Candidate directions never become downstream facts.
    return route.get("selected_concept", "") if stage == "concept" else route["documents"][stage]["text"]


def empty_route(brief, revision):
    docs = {s: blank_document() for s in STAGES}
    docs["brief"].update(text=brief, revision=revision)
    return {"schema_version": 2, "documents": docs, "legacy": "", "selected_concept": ""}


def dependencies(route, stage):
    return {s: route["documents"][s]["revision"] for s in STAGES[:STAGES.index(stage)]}


def statuses(route):
    result = {}
    for stage in STAGES:
        doc = route["documents"][stage]
        expected = dependencies(route, stage)
        stale = bool(doc["text"]) and (doc["dependencies"] != expected or any(result[s] == "stale" for s in expected))
        result[stage] = "empty" if not doc["text"] else "stale" if stale else "confirmed" if doc["confirmed"] else "draft"
    return result


def require_upstream(route, stage):
    state = statuses(route)
    missing = [LABELS[s] for s in STAGES[:STAGES.index(stage)] if state[s] != "confirmed"]
    if missing:
        raise HTTPException(400, "请先检查并确认上游成果：" + "、".join(missing))


def revise(route, stage, text, revision, action):
    route = normalize(route)
    result = deepcopy(route)
    if stage == "legacy":
        result["legacy"] = text
        return result
    if stage not in STAGES:
        raise HTTPException(400, "未知创作阶段。")
    doc = result["documents"][stage]
    if action == "confirm":
        if not doc["text"].strip():
            raise HTTPException(400, "请先填写本阶段成果。")
        require_upstream(route, stage)
        errors = stage_issues(result, stage)
        if errors:
            raise HTTPException(400, "本阶段尚不能确认：" + "；".join(errors))
        doc["dependencies"] = dependencies(route, stage)
        doc["confirmed"] = True
        if all(d["confirmed"] for d in result["documents"].values()):
            result.pop("migration_notice", None)
        # Confirmation doesn't change the content revision or invalidate descendants.
    elif action == "select_concept":
        if stage != "concept":
            raise HTTPException(400, "只能在故事立意阶段选定方向。")
        if text != result.get("selected_concept", ""):
            result["selected_concept"] = text
            doc.update(revision=revision, confirmed=False)
    elif text != doc["text"]:
        first = not doc["text"]
        doc.update(text=text, revision=revision, confirmed=False)
        if stage == "concept":
            result["selected_concept"] = ""
        # Manual edits to an existing stale draft require explicit review confirmation.
        if first or action == "chat":
            doc["dependencies"] = dependencies(route, stage)
    return result
