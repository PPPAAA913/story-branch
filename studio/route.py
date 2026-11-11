"""Immutable story-route snapshots and explicit upstream review dependencies."""
from copy import deepcopy
from fastapi import HTTPException

STAGES = ["brief", "concept", "character", "outline", "script", "review"]
LABELS = dict(zip(STAGES, ["创作简报", "故事方向", "人物设定", "前三集大纲", "首集剧本", "修改与对比"]))
GUIDES = {
    "brief": "整理中文创作简报，明确具体英语目标地区、题材、受众、时长、角色和场景限制。未知信息标记待确认。",
    "concept": "用中文提出故事方向。供人选择；只有用户选定并确认后才用于人物开发。",
    "character": "根据已确认方向，用中文建立人物动机、关系、秘密与成长变化。",
    "outline": "用中文编写前三集大纲，每集包含行动、冲突升级与结尾悬念。",
    "script": "输出第一集完整英文剧本，包含场景、动作和英文对白；文末另附中文梗概。",
    "review": "用中文审阅本路线的剧本并提出具体修改建议。只更新审阅记录，不改写其他阶段。用户需回到相应阶段修改。",
}


def empty_route(brief, revision):
    docs = {s: {"text": "", "revision": None, "confirmed": False, "dependencies": {}} for s in STAGES}
    docs["brief"].update(text=brief, revision=revision)
    return {"documents": docs, "legacy": ""}


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
        doc["dependencies"] = dependencies(route, stage)
        doc["confirmed"] = True
        # Confirmation doesn't change the content revision or invalidate descendants.
    elif text != doc["text"]:
        first = not doc["text"]
        doc.update(text=text, revision=revision, confirmed=False)
        # Manual edits to an existing stale draft require explicit review confirmation.
        if first or action == "chat":
            doc["dependencies"] = dependencies(route, stage)
    return result
