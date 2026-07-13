---
name: mcp-integration
description: 双向 MCP 集成计划——Server 端暴露能力 + Client 端消费外部工具
metadata:
  type: project
---

# MCP 集成（Phase 2 加分项）

## 双向 MCP 架构

### Server 端：暴露 Research Copilot 能力
外部 AI（Claude Desktop / Cursor IDE）通过 MCP 协议调用：
- `deep_research` — 深度研究某个主题
- `quick_search` — 快速搜索并总结
- `generate_report` — 生成结构化报告

技术：`mcp` Python SDK 或 `fastmcp`，SSE transport（复用 FastAPI server）

### Client 端：消费外部 MCP 工具
Agent Loop 可以连接外部 MCP Server（如浏览器自动化 Server），获取需要 JS 渲染的动态网页内容——传统 HTTP 爬取拿不到。

协议层：JSON-RPC 2.0 + SSE transport

## 面试价值

> "我实现了双向 MCP——既能作为 Server 被外部 AI 调用，也能作为 Client 消费外部 MCP 工具。协议层使用 JSON-RPC + SSE transport，工具 Schema 遵循 JSON Schema 规范。"

这句话展示：你不只是调 API，你理解协议层设计。

**Why:** MCP 是 2026 年 Agent 生态的标准协议，面试高频考点。双向实现比单向更有深度。

**How to apply:** Phase 2（Day 7-8 之后）再启动。实现时参考 FastGPT 的 `projects/mcp_server/` 结构。[[tech-stack-decisions]]
