---
name: dev-roadmap
description: 10 天开发路线图——4 个 Phase 的里程碑和验收标准
metadata:
  type: project
---

# 开发路线图（10 天，4 个 Phase）

## Phase 0：项目骨架（Day 1）
**目标**：项目能跑起来
- Git init + FastAPI + React 项目初始化
- DeepSeek API 调通
- 前端↔后端连通

**验收**：网页输入"你好"，DeepSeek 回复。

## Phase 1：Agent Engine（Day 2-4）
**Day 2**：核心循环 — AgentState、UnifiedAgentLoop.run()、ToolRegistry、System Prompt、2 个工具（create_plan + write_section）
**Day 3**：搜索+分析 — web_search（Tavily）、analyze_data、上下文管理、迭代限制
**Day 4**：Stop Gate + 错误处理 — 章节/字数/引用校验、修正循环、工具失败重试（最多 3 次）

**验收**：Agent 自主完成「研究→搜索→分析→撰写→审核→修正→完成」全流程。

## Phase 2：前后端打通（Day 5-6）
**Day 5**：SSE 流式 + 前端时间线
**Day 6**：报告渲染 + 导出 MD/PDF + SQLite 历史记录

**验收**：完整闭环——输入任务→看 Agent 干活→查看报告→下载文件→历史可查。

## Phase 3：进阶功能（Day 7-8）
**Day 7**：RAG 知识库（ChromaDB + Embedding + upload + search_knowledge_base）
**Day 8**：质量工具（review_section + fact_check）+ 执行日志 + UI 打磨

## Phase 4：收尾+部署（Day 9-10）
**Day 9**：测试 + 文档
**Day 10**：Docker Compose + 部署 + Demo 录制 + GitHub 公开

## 降级策略
如果时间不够：砍 Phase 3（RAG/MCP）保 Phase 0-2，确保最小可用版本。

**Why:** 10 天是硬约束。Phase 0-2 是 MVP 必须的，Phase 3 是加分项，Phase 4 是面试准备。每阶段有明确验收标准，不做完不进入下一阶段。

**How to apply:** 每天开始前确认当天目标，完成后对照验收标准自测。遇到阻塞优先降级而非死磕。
