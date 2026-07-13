---
name: tool-layer
description: 工具注册中心模式 + 核心工具列表（Agent 的能力边界）
metadata:
  type: project
---

# 工具层设计

## 设计原则

每个 Agent 角色被抽象为一个或一组**工具（Tool）**，而不是独立服务。借鉴 FastGPT runtime tool 设计——所有能力暴露为 tool，LLM 自主调度。

## ToolRegistry 单例模式

- `register(name, description, parameters)` 装饰器注册工具
- `get_all_schemas()` 返回 OpenAI 兼容的 tool schemas 列表
- `execute(name, **kwargs)` 执行指定工具

## 核心工具列表（按优先级）

| 工具名 | 功能 | 优先级 |
|--------|------|--------|
| `create_plan` | 拆解复杂任务为子步骤 | P0 |
| `update_plan` | 执行中动态调整计划 | P1 |
| `web_search` | 调用搜索 API，返回网页摘要 | P0 |
| `fetch_page` | 抓取单个网页全文 | P1 |
| `search_knowledge_base` | 查询本地向量知识库（RAG） | P1 |
| `analyze_data` | 对收集的数据做结构化分析 | P0 |
| `compare_perspectives` | 对比不同来源的观点 | P2 |
| `write_section` | 撰写报告的某个章节 | P0 |
| `format_markdown` | 格式化 Markdown 结构 | P1 |
| `review_section` | 检查一个章节的质量 | P1 |
| `fact_check` | 尝试验证关键事实 | P2 |
| `export_file` | 导出 Markdown/PDF 文件 | P0 |

**Why:** 工具是 Agent 的"手脚"——工具列表定义了 Agent 的能力边界。P0 工具是 MVP 必须的，P1/P2 可以后续迭代。工具注册中心模式让新增能力不需要改循环代码。

**How to apply:** 新增 Agent 能力时，不要新建 Agent 类，而是注册新工具。实现新工具放在 `backend/tools/` 目录下，用 `@ToolRegistry.register()` 装饰器。[[agent-engine-design]]
