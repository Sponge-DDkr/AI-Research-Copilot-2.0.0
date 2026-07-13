---
name: directory-structure
description: 项目目录结构约定——什么放哪、怎么命名
metadata:
  type: project
---

# 项目目录结构

```
ai-research-copilot/
├── backend/
│   ├── main.py                    # FastAPI 入口 + 生命周期
│   ├── config.py                  # 配置管理（环境变量 + .env）
│   ├── api/                       # API 路由层
│   │   ├── research.py            # /api/research/* 端点
│   │   ├── reports.py             # /api/reports/* 端点
│   │   └── knowledge.py           # /api/knowledge/* 端点
│   ├── agent_engine/              # 🎯 Agent 核心
│   │   ├── loop.py                # UnifiedAgentLoop 主循环
│   │   ├── state.py               # AgentState + PlanStep 数据结构
│   │   ├── stop_gate.py           # Stop Gate 校验
│   │   ├── prompt.py              # System Prompt 模板管理
│   │   └── sse_emitter.py         # SSE 事件发射器
│   ├── tools/                     # 🎯 工具层
│   │   ├── registry.py            # ToolRegistry 注册中心
│   │   ├── search.py              # web_search + search_knowledge_base
│   │   ├── fetch.py               # fetch_page
│   │   ├── analyze.py             # analyze_data + compare_perspectives
│   │   ├── write.py               # write_section + format_markdown
│   │   ├── review.py              # review_section + fact_check
│   │   └── export.py              # export_file (MD/PDF)
│   ├── database/
│   │   ├── sqlite.py              # SQLite 连接 + CRUD
│   │   └── models.py              # Pydantic 数据模型
│   ├── vector/
│   │   ├── chroma.py              # ChromaDB 客户端封装
│   │   └── embedder.py            # Embedding 模型调用
│   └── tests/
│       ├── test_agent_loop.py
│       ├── test_tools.py
│       ├── test_stop_gate.py
│       └── test_api.py
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── HomePage.tsx       # 首页：任务输入 + 历史列表
│       │   └── ReportPage.tsx     # 报告页：查看 + 导出
│       ├── components/
│       │   ├── TaskInput.tsx
│       │   ├── AgentTimeline.tsx  # 🎯 Agent 执行时间线
│       │   ├── StepCard.tsx       # 单步骤状态卡片
│       │   ├── ReportViewer.tsx   # Markdown 报告渲染
│       │   ├── KnowledgeUpload.tsx
│       │   └── ExportButton.tsx
│       ├── hooks/
│       │   ├── useResearchStream.ts  # SSE 流式接收
│       │   └── useReports.ts
│       ├── api/client.ts          # Axios 封装
│       └── types/index.ts         # TypeScript 类型
├── .env.example
├── .gitignore
├── README.md
└── docker-compose.yml             # Phase 2+
```

**Why:** 严格的目录结构约定让 AI 编码时知道什么文件放哪里。遵循这个结构就不需要每次编码前重新讨论"放哪"。

**How to apply:** 新建文件严格按此结构放置。`agent_engine/` 和 `tools/` 是核心模块，修改频率最高。文件名用 snake_case（Python）或 PascalCase（React 组件）。
