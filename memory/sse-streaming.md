---
name: sse-streaming
description: SSE 实时流式推送的事件类型设计和前后端实现模式
metadata:
  type: project
---

# SSE 实时流式推送

## 为什么用 SSE 而非 WebSocket

- 单向推送 Agent 进度就够用（不需要双向）
- 浏览器原生 EventSource API 支持
- 比 WebSocket 轻量，实现更简单
- 面试亮点：不是"做了个 loading"，而是"实时展示 Agent 协作过程"

## SSE 事件类型

| 事件类型 | 触发时机 | 前端展示 |
|---------|---------|---------|
| `task_started` | 用户提交任务 | 显示"开始处理..." |
| `plan_created` | 创建研究计划 | 展示计划步骤列表 |
| `step_started` | 开始执行某步骤 | 该步骤高亮 + spinner |
| `tool_executed` | 工具执行完毕 | 展示工具名 + 结果摘要 |
| `step_completed` | 某步骤完成 | 打勾 ✅ |
| `section_written` | 写完某章节 | 流式展示章节内容 |
| `revision_requested` | Stop Gate 不通过 | 显示"正在修正..." |
| `error` | 工具执行出错 | 显示错误信息 + 自动重试 |
| `complete` | 报告生成完毕 | 展示完整报告 + 下载按钮 |

## 关键实现细节

- 后端：FastAPI `StreamingResponse` + `text/event-stream` media type
- 前端：`reader.read()` 手动解析 SSE（非 EventSource，因为需要 POST）
- 需禁用 Nginx 缓冲：`X-Accel-Buffering: no`
- 消息边界：`\n\n` 分隔，格式 `data: {json}\n\n`

**Why:** 这是项目的"面试大杀器"——面试官问"怎么展示 Agent 工作过程"，回答 SSE 实时推送比"loading 动画"强一个量级。

**How to apply:** 新增 Agent 事件时，先在 `sse_emitter.py` 定义事件类型，再在 loop 中正确时机调用 `emit()`。前端在 `useResearchStream` 中处理新事件类型。
