---
name: tech-stack-decisions
description: 技术栈选择及每个选择的理由——为什么是这个而不是那个
metadata:
  type: project
---

# 技术栈决策

## 后端

| 选择 | 为什么 |
|------|--------|
| Python 3.12 + FastAPI 0.115+ | AI 生态标准，原生 async，SSE 支持好，自动文档 |
| DeepSeek API（非 GPT-4） | 中文能力强、价格 1/30、兼容 OpenAI SDK（base_url 切换即可换模型） |
| ChromaDB 0.5+（非 Pinecone/Weaviate） | 本地运行、零配置、Python 原生，适合 Demo 展示 |
| SQLite（非 PostgreSQL） | 零配置、单文件、足够单用户 Demo |
| LangGraph 0.2+ 辅助 | 复杂分支流程可视化和调试，但主循环自研 |
| httpx 0.28+ | 异步 HTTP，调用搜索 API 和 LLM API |
| Pydantic 2.x | FastAPI 深度集成，数据校验 |

## 前端

| 选择 | 为什么 |
|------|--------|
| React 18 + TypeScript | 生态最大，类型安全 |
| Vite | 快、配置少 |
| TailwindCSS | 快速开发 |
| Ant Design | 中文友好、表格/表单组件丰富 |
| EventSource API（非 WebSocket） | SSE 接收，浏览器原生支持，不需要额外库 |
| React-Markdown | 报告展示核心需求 |

## 外部 API

| API | 免费额度 |
|-----|---------|
| DeepSeek API | 注册送 500 万 token |
| Tavily Search API | 每月 1000 次免费 |
| Bing Search API（备选） | 每月 1000 次免费 |

## 关键架构决策

| 决策 | 选择 | 为什么 |
|------|------|--------|
| Agent 编排 | 自研 Unified Agent Loop + LangGraph 辅助 | 学习 FastGPT 生产实践，同时保留状态管理能力 |
| Agent 范式 | ReAct + Plan-and-Execute 混合 | 简单快速响应，复杂有规划执行 |
| 流式推送 | SSE（非 WebSocket） | 单向推送够用，浏览器原生支持，比 WebSocket 轻量 |
| 工具协议 | MCP 兼容 | 2026 年 Agent 生态标准 |

**Why:** 每个技术选择背后都有明确的权衡考量，不盲从流行方案，按实际场景做决策。

**How to apply:** 新引入依赖前，参照这个表的格式评估：它解决什么、替代方案是什么、为什么选它。
