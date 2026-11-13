"""Prepare paired writing trials; --live explicitly enables at most six API calls.

Run from repository root: python -m studio.evaluate_writing
No API calls are made without --live. Human scoring is intentionally separate.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random

from .workspace import ModelGateway
from .writing import build_pack

CASES = [
    {
        "id": "voice-and-subtext",
        "brief": "美国英语都市情感短剧，首集约90秒，2位演员，1个办公室。英文剧本，附中文梗概。",
        "concept": "年轻制片人发现竞争对手匿名资助她的作品，必须争取独立决定权。",
        "character": "MAYA：问短而具体的问题，受压时更克制；知道资金来源但不知道审批条款。ALEX：用商业术语回避情感，害怕被拒绝；知道条款。他们都不会直接告白。",
        "outline": "第1集：Maya带着付款凭证质问Alex；Alex承认资助，却要求她签字。Maya主动翻到审批条款，坚持划掉否决权。最后Alex表示该条款来自另一个出资者。第2集追查出资者，第3集作出合作选择。",
        "scenes": "场景1：办公室内，Maya出示付款凭证，Alex承认资助；Maya从询问转为要求说明条件，约30秒。场景2：同一办公室，Alex递出待签协议，Maya翻到审批条款并要求取消否决权；Alex透露另一个出资者，约60秒。仅两人、付款凭证和协议。",
        "checks": ["两人的口吻可区分", "动作和对白承担潜台词", "Maya通过看文件才知道条款", "只使用两名演员和一个场景"],
    },
    {
        "id": "continuity-and-causality",
        "brief": "英国英语悬疑短剧，首集约90秒，2位演员、仅公寓内景，不出现武器或警方。英文剧本，附中文梗概。",
        "concept": "租客通过一张旧收据发现室友隐瞒了前任租客的离开时间。",
        "character": "NORA：租客，今天首次看到收据，尚不知道前任租客姓名。ELI：室友，知道姓名但不愿说；只能确认对方搬走，不能确认其死亡。",
        "outline": "第1集：Nora发现昨晚日期的收据，与Eli声称前任早已搬走矛盾；她主动核对日期并追问。Eli最终承认昨晚见过对方。结尾门外敲门但不展示第三人。第2集解释来访，第3集揭示隐瞒原因。",
        "scenes": "场景1：公寓内，Nora发现收据，核对昨晚日期，形成时间矛盾，约30秒。场景2：公寓内，Nora以日期追问Eli，他承认昨晚见过前任租客但不说姓名；结尾门外响起敲门声，不展示第三人，约60秒。",
        "checks": ["Nora没有凭空知道姓名", "没有将搬走升级为死亡事实", "揭示源于核对和追问", "没有新增第三名出镜角色"],
    },
    {
        "id": "production-and-hook",
        "brief": "美国英语轻喜剧短剧，首集约60秒，2位演员、1个咖啡店内景、道具仅纸杯和笔。英文剧本，附中文梗概。",
        "concept": "两位求职者错拿了写有面试暗号的纸杯，为了获取线索进行交易。",
        "character": "JUNE：急于证明能力，语速快但不用长篇说明；SAM：谨慎，常用反问。两人互不认识，只有各自纸杯上的半句暗号。",
        "outline": "第1集：June看到Sam杯上的暗号，先试探后提出交换；Sam要求她先透露半句。两人拼出暗号后发现它要求他们互相面试。结尾两人同时问第一个问题。不新增面试官或其他场景。",
        "scenes": "场景1：咖啡店内，June注意Sam纸杯的暗号并试探，约15秒。场景2：同一地点，Sam要求交换，双方用纸杯和笔拼出暗号，发现要互相面试；结尾同时发问，约45秒。只有June和Sam。",
        "checks": ["开场以可见事件引出问题", "没有手机、额外人物或外景", "交易推动反转而非旁白解释", "中文梗概没有补写英文稿中不存在的情节"],
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Enable up to 6 paid calls using DEEPSEEK_API_KEY.")
    parser.add_argument("--output", default="data/writing-evaluation")
    args = parser.parse_args()
    directory = Path(args.output) / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True, exist_ok=False)
    plan = {"status": "prepared_only", "api_calls": 0, "cases": CASES,
            "rubric": ["人物一致性", "行动与因果", "口吻与潜台词", "制作约束", "英文自然度", "梗概忠实度"],
            "scoring": "每项1–5分，并引用输出片段说明；先盲评再查看assignment.json。不把一次试写当成统计结论。",
            "baseline": "相同模型、简报、选定立意、人物、大纲、分场、阶段约定与输出协议；仅省略可插拔skills规则。",
            "limitations": "尚未执行真实试写；没有质量提升结论。真实调用每轮最多6次，不自动重试。"}
    def save(name, value):
        (directory/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    save("plan.json", plan)
    if not args.live:
        print(f"Prepared 3 paired trials; 0 API calls. Files: {directory}")
        return
    gateway = ModelGateway()
    if gateway.status()["mode"] != "deepseek":
        raise SystemExit("Set DEEPSEEK_API_KEY in the server environment before --live. No calls made.")
    samples, assignment, errors = [], [], []
    rng = random.Random(20261111)
    for case in CASES:
        conditions = ["baseline", "skills"]
        rng.shuffle(conditions)
        for label, condition in zip(["A", "B"], conditions):
            pack = build_pack("script", include_skills=condition == "skills")
            project = {"brief":case["brief"], "active_stage":"script", "upstream":{key:case[key] for key in ("brief","concept","character","outline","scenes")}}
            prompt = {"title":"首集试写", "body":"根据已确认设定写第一集英文剧本，附中文梗概。", "writing":pack}
            assignment.append({"case":case["id"], "label":label, "condition":condition, "prompt":prompt})
            try:
                plan["api_calls"] += 1
                reply, document, _, model = gateway.generate(project,[{"document":"","instruction":"","reply":""}],"完成第一集，不增加后续集正文。",prompt)
                samples.append({"case":case["id"],"label":label,"reply":reply,"document":document,"model":model})
            except Exception as exc:
                errors.append({"case":case["id"],"label":label,"error":getattr(exc,"detail","Trial failed")})
            save("blind_samples.json", samples)
            save("assignment.json", assignment)
            save("errors.json", errors)
            plan["status"] = "completed" if len(samples) == 6 else "partial"
            plan["limitations"] = "未自动评分；等待人工盲评。单次生成具有随机性，不构成统计质量结论。"
            save("plan.json", plan)
    print(f"Trials complete: {len(samples)} outputs, {len(errors)} errors. Files: {directory}")


if __name__ == "__main__":
    main()
