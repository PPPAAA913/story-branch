# 写作方法迭代与验证

整理日期：2026-11-13。实现版本：写作方法包 2026-11-13.1，平台 v0.7.0。

## 筛选结果

| 候选 | 本轮处理 | 原因 |
|---|---|---|
| [ur-grue/autopunk-media-skills](https://github.com/ur-grue/autopunk-media-skills) | 适配五项写作方法 | 人物、节拍、场景、对白与审阅分工清楚；MIT 许可证已核对 |
| [0xsline/short-drama](https://github.com/0xsline/short-drama) | 适配文化定位、立意、悬念、分场节奏和英文文化适配 | MIT 已核对；移除长季集数、固定秒数/字数、强制镜头和未经证实的爆款承诺 |
| [haowjy/creative-writing-skills](https://github.com/haowjy/creative-writing-skills) | 查阅 story-review，暂未集成 | 更侧重散文/小说编辑及配套资源；本轮优先完成剧本场景方法 |
| [jtydhr88/screenwriting-skills](https://github.com/jtydhr88/screenwriting-skills) | 查阅项目与 NOTICE，暂未集成 | 原创技能采用 MIT，但书籍和剧本引文不在许可范围；本轮没有引入这些参考文本 |

查阅原文、许可证和文件标识后，将适用的方法重新编排为中文短剧规则。没有安装第三方插件、运行第三方脚本或复制上游示例故事。这里的接入发生在 Story Branch 服务端，规则随 DeepSeek 请求生效；不依赖使用者安装 Codex skills。

## 已接入的方法

| 上游 skill | 应用阶段 | 本项目适配 |
|---|---|---|
| character-profile-writer | 人物与关系 | 目标、需要、压力选择、知情边界、口吻描述，不提前安排分集或写对白 |
| beat-sheet-builder | 前三集大纲 | 因果、代价与铺垫，不套长片十五节拍 |
| scene-writer / dialogue-polisher | 首集剧本 | 已确认分场的可拍动作、口吻与潜台词 |
| script-notes-writer | 任意阶段的只审阅模式 | 按当前阶段职责给出有证据的意见，不因为早期成果没有对白而扣分 |
| short-drama /overseas 与策划原则 | 定位、立意、剧本分别适配 | 具体地区文化背景、可理解的冲突、自然英文表达；三种角色分别加载，不混用全部职责 |
| short-drama hook-design | 前三集大纲 | 问题来自主线行动，下一集回应；反转需铺垫，不承诺商业效果 |
| short-drama rhythm-curve | 首集分场 | 场景推进与张弛、时长估计，不套固定场数或固定时长比例 |

阶段约定由 `studio/contracts.py` 统一定义：职责、输出段落、禁止越界的事项与检查标准。程序仅对必填段落、候选选择、场景编号/场景头和上游确认做确定性检查；人物动机、文化合理性和剧情逻辑仍需审阅与人工判断。

具体来源 URL 与 Git blob SHA 记录在 `third_party/autopunk-media-skills/sources.json` 与 `third_party/short-drama/sources.json`；各目录保留原许可证。适配规则位于 `studio/writing.py`，其注释保留原作者署名。Docker 打包包含许可文件。

## 平台行为

- 默认按阶段启用适用规则；仍允许小组修改本轮提示词及另存模板。
- 本轮任务可选“创作/修改”“只讨论”“只审阅”“英文对白润色”；润色限于首集剧本。
- 只讨论、只审阅由服务端强制保持原稿，即使模型返回了改写文本也不采纳；仅追加对话记录，不解除确认或待检查状态。
- 未完成上游时可讨论和审阅，未确认材料有单独标签；正式生成仍要求上游确认。
- 每次调用保存方法包版本、规则正文与 SHA-256、来源及上游版本引用。只增加当前调用的指导内容，不自动追加第二轮模型调用。
- 内置模板升级；小组自定义模板和历史版本中的旧提示词快照保留。

## 已验证与未验证

功能验证与当前测试数见 [DEVELOPMENT.md](DEVELOPMENT.md)。浏览器已验证新六阶段、人工选择、只读审阅、旧审阅保留、导出、分叉与桌面/窄屏；没有执行真实付费调用。

这些检查证明功能接入正确，不能证明生成质量已经提升。真实效果需通过下面的对照试写验证。

## 对照试写

从项目目录运行：

```sh
python -m studio.evaluate_writing
```

默认只准备三组对照任务，零 API 调用。分别检查人物口吻/潜台词、连续性/因果、制作限制/开场悬念。结果保存在忽略的 `data/writing-evaluation/` 下。

服务器环境已配置 DeepSeek 密钥后，由操作者明确运行：

```sh
python -m studio.evaluate_writing --live
```

每轮最多六次调用，无自动重试；基线与方法包条件使用相同模型、定位、选定立意、人物、大纲、首集分场、用户要求及阶段约定；仅开关可插拔 skills。脚本不训练模型。失败记录会保存，但不据此编造输出或评分。

王司恺负责检查测试简报、规则和期待行为；吕兴治组织至少两位组员对 `blind_samples.json` 按人物一致性、因果、口吻、制作约束、英语自然度、梗概忠实度各打 1–5 分，并引用具体片段。评分后再查看 `assignment.json` 对应关系。三组单次试写只作探索性比较，不能宣称统计显著提升。

运行时从服务器环境读取密钥，不将密钥写入结果。当前仍待真实 API、调用统计/限额与在线部署；GitHub 发布记录以仓库提交为准；上传源码不等于上线。
