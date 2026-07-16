---
name: mcp-integration
description: MCP 集成计划——独立 mcp-knowledge-agent 项目
metadata:
  type: project
---

# MCP 集成

## 实际实现

AI Research Copilot 本身未内置 MCP 协议层。MCP 能力拆分到了独立的 **mcp-knowledge-agent** 项目：

- **MCP Server 端**（已实现）：将知识库 RAG 检索管线封装为 8 个 MCP 工具（`search_knowledge`、`answer_with_citation`、`search_similar` 等），通过 stdio transport 供 Claude Desktop / Claude Code / Cursor / DataAgent 调用
- **MCP Client 端**（未实现）：Agent Loop 消费外部 MCP 工具的功能目前不在开发范围内

## 原始计划（设计阶段）

> 计划实现双向 MCP——Server 端暴露 Research Copilot 能力，Client 端消费外部 MCP 工具（如浏览器自动化）。协议层使用 JSON-RPC + SSE transport。

实际执行时，考虑到独立的 MCP Server 复用性更好（一套代码四个下游消费者），选择了将 MCP 层拆分为独立项目。

**Why:** MCP 是 2026 年 Agent 生态的标准协议。独立 Server 项目比内嵌在 FastAPI 中更干净、更容易复用。

**How to apply:** MCP Server 项目位于 `../mcp-knowledge-agent/`，使用 `python -m mcp_knowledge_agent` 启动。[[tech-stack-decisions]]
