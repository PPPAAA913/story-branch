# 给彭奥：真实 API 联调前的三个已知坑

2026-11-12 · 王司恺

11 月 7 日我用 `deepseek-flash` 跑过 37 次真实调用（当时是旧版单文档结构），踩到三个会直接导致失败的问题。现在 `studio/workspace.py` 已经改版，下面只作为联调检查清单，**请先核对当前代码再决定是否修改**。不涉及密钥，也不要把 Key 写进任何记录。

## 1. 思考模式默认开启，和正文共用 `max_tokens`

- 现象：`finish_reason=length`，`completion_tokens=8192`，其中 `reasoning_tokens=8192`，`content` 为空或只有半截。
- 证据：首轮六步里 4 次失败，其中一次正文 0 字。
- 当前代码：`studio/workspace.py` 的请求里固定 `"max_tokens": 8192`，未传 `thinking`，服务端默认开启思考。
- 建议：
  - 请求加 `"thinking": {"type": "disabled"}`（或 `"reasoning_effort": "none"`）；
  - 把 `max_tokens` 提到 32768–65536。六阶段每次都要回传完整阶段稿件，8192 在剧本/审阅阶段不够。
- 代价对比：关闭思考单条约 19 秒；开启思考约 43 秒，且更容易截断。

## 2. JSON 模式偶尔在合法 JSON 后追加杂质

- 现象：`json.loads` 报 `Extra data: line 1 column ...`，实际内容末尾多出 `</parameter>` 之类的文本。
- 建议：先 `json.loads`，失败再用 `JSONDecoder().raw_decode(content.strip())` 取第一个完整对象；仍失败才按格式错误处理。这样不会把一次可用的付费结果丢掉。

## 3. 截断与格式错误混在一起

- 当前 `finish_reason != "stop"` 统一报 `Incomplete output`，排查时分不清是截断、过滤还是模型结构问题。
- 建议：`finish_reason == "length"` 单独提示“输出被截断”，并把 `usage.completion_tokens_details.reasoning_tokens` 记进日志（不记正文）。

## 验证顺序建议

1. `GET /models` 确认 Key 有效、模型名可用（不花生成 token）。
2. 一次最小 JSON 调用，确认结构。
3. 连发 3 次，观察限流与耗时波动。
4. 再用一份短简报跑完整六阶段；每步确认 `document` 非空、`stage_status` 正确。
5. 失败时保留原始返回（截断/空白/杂质），不要重试掩盖。

修好后的参考结果：同一份简报六步 6/6 成功，最终阶段文档约 1.2 万字符，单步 18–37 秒。
