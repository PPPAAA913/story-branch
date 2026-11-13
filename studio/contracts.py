"""Stage contracts shared by prompts, confirmation gates and the UI.

Structural checks are deliberately separate from subjective AI writing reviews.
Drafts remain saveable even when incomplete.
"""
import re

STAGES = ["brief", "concept", "character", "outline", "scenes", "script"]
LABELS = dict(zip(STAGES, ["创作定位", "故事立意", "人物与关系", "前三集大纲", "首集分场", "首集剧本"]))
CONTRACTS = {
    "brief": {
        "role": "创作策划：确定目标与约束，不创作具体故事。",
        "sections": ["目标地区与语言", "受众与题材", "时长与制作约束", "内容边界与待确认事项"],
        "output": "明确具体英语地区与文化背景；将受众判断标为假设；说明题材、语气、单集时长、演员/场地/道具上限及内容边界。未知信息明确标注。",
        "boundary": "不写故事事件、人物传记、分集大纲或对白；不虚构市场调查。",
        "check": "地区是否具体，语言与文化背景是否分开说明，制作限制是否明确，假设是否标明。",
    },
    "concept": {
        "role": "故事策划：探索核心冲突与叙事承诺，供人选择。",
        "sections": ["方向一", "方向二", "方向三"],
        "output": "三个方向分别包含一句话故事、主角主动目标、对抗力量、选择代价、核心吸引力与制作风险。三个方向应有实质区别。人选定后，后续仅使用人工保存的选定立意。",
        "boundary": "只定义人物的必要身份和冲突，不写详细人物卡、逐集事件、场景执行或对白；不得替用户选定方向。",
        "check": "三个方向是否不同，冲突是否能够展开，是否符合定位；不能把候选当作已确认事实。",
    },
    "character": {
        "role": "人物设计：为选定立意建立能驱动行动的人物与关系。",
        "sections": ["人物卡", "关系与知情边界", "口吻特征"],
        "output": "人物卡逐人说明姓名、身份、外部目标、内在需要、动机、弱点与压力下的选择；关系表说明利益冲突、秘密及谁知道什么；口吻用词汇、句长和回避方式描述。",
        "boundary": "允许细化立意未规定的经历；不得改变选定立意的核心身份和冲突。不指定第几集发生何事，不写场景或成段对白。",
        "check": "动机能否解释行动，各人知情范围是否自洽，关系是否符合选定立意，是否超出角色数量限制。",
    },
    "outline": {
        "role": "分集编剧：把人物选择组织成前三集的因果链。",
        "sections": ["第1集", "第2集", "第3集"],
        "output": "严格三集；每集写开场承接、目标、行动与阻力、主动选择与代价、结果/转折、结尾悬念。说明下一集如何回应上一集及所需角色/地点。",
        "boundary": "可以安排事件，不得改变人物身份、动机与初始知情；信息变化必须由事件解释。不写完整对白或逐场执行，不扩写第四集。",
        "check": "事件是否因果相接，每集是否有进展，悬念是否承接，反转是否铺垫，人物知道信息的时间是否合理。",
    },
    "scenes": {
        "role": "场景设计：只将第一集大纲拆成可执行的场景。",
        "sections": ["场景列表", "时长与制作核对"],
        "output": "场景列表逐场用 ### 场景1 等编号，列地点/内外/日夜、出场人物、目标、阻力、行动、进入与退出局面的变化、对大纲事件的对应、预计时长。核对演员/场地/道具与首集悬念。时长只是估计。",
        "boundary": "可补必要衔接，不改变第一集事件结果或结尾，不编第二集，不写完整对白，不编详细摄影分镜。",
        "check": "每场是否有变化，是否覆盖第一集关键事件，末场是否保留既定悬念，场景时长和制作需求是否可行。",
    },
    "script": {
        "role": "剧本编剧：按已确认首集分场完成英文场景、动作和对白。",
        "sections": ["英文剧本", "中文梗概"],
        "output": "只写首集。英文剧本采用 INT./EXT. 场景头、现在时可见动作、人物名与对白；中文梗概忠于正文。延续人物口吻与目标地区表达。",
        "boundary": "可丰富动作和对白，不改变已确认场景结果、人物知情、关系、时间线与结尾；不额外写第二集；不把导演镜头清单当文学剧本。",
        "check": "逐场是否符合分场，对白是否自然且可区分人物，动作是否可拍，中文梗概是否与英文正文一致。",
    },
}


def template(stage):
    return "\n\n".join("## " + title + "\n[待填写]" for title in CONTRACTS[stage]["sections"])


def sections(text):
    """Parse exact level-two headings; preserve lower-level scene/person headings."""
    matches = list(re.finditer(r"^##[ \t]+([^\n]+?)\s*$", text, re.M))
    return [(m.group(1).strip(), text[m.end():matches[i+1].start() if i+1 < len(matches) else len(text)].strip()) for i, m in enumerate(matches)]


def issues(stage, text, selection=""):
    if stage not in CONTRACTS:
        return []
    parts = sections(text)
    errors = []
    for title in CONTRACTS[stage]["sections"]:
        found = [body for heading, body in parts if heading == title]
        if not found:
            errors.append("缺少段落：## " + title)
        elif len(found) != 1:
            errors.append("段落重复：" + title)
        elif not found[0] or "[待填写]" in found[0]:
            errors.append("请填写：" + title)
    if stage == "concept" and not selection.strip():
        errors.append("请在选定立意中保存一个方向的完整核心设定，不能只填写编号。")
    if stage == "outline" and any(re.fullmatch(r"第[一二三四五六七八九十百\d]+集.*", title) and title not in CONTRACTS[stage]["sections"] for title, _ in parts):
        errors.append("本阶段只交付前三集，请移除额外集数。")
    if stage == "scenes" and not re.search(r"^###[ \t]+场景[ \t]*[1１一]", text, re.M):
        errors.append("请在场景列表中用 ### 场景1 等三级标题逐场编号。")
    if stage == "script" and not re.search(r"\b(?:INT|EXT)\.", dict(parts).get("英文剧本", "")):
        errors.append("英文剧本需包含 INT. 或 EXT. 场景头。")
    return errors


def public_contracts():
    return {s: dict(c, label=LABELS[s], template=template(s), upstream=STAGES[:STAGES.index(s)]) for s, c in CONTRACTS.items()}
