---
name: database-schema
description: SQLite 表结构 + ChromaDB Collection 设计
metadata:
  type: project
---

# 数据库设计

## SQLite 表结构

### reports 表
- `id` TEXT PK (UUID)
- `task` TEXT — 用户原始任务描述
- `report_md` TEXT — Markdown 格式报告
- `plan_json` TEXT — JSON 格式执行计划
- `status` TEXT — pending | running | done | failed
- `created_at`, `updated_at`

### tool_logs 表（调试+复盘用）
- `id` INTEGER PK AUTOINCREMENT
- `report_id` TEXT FK → reports.id
- `tool_name` TEXT
- `arguments` TEXT (JSON)
- `result` TEXT — 截断到前 1000 字
- `duration_ms` INTEGER
- `error` TEXT
- `created_at`

### documents 表（知识库）
- `id` TEXT PK
- `filename` TEXT
- `content` TEXT
- `chunk_count` INTEGER
- `created_at`

## ChromaDB Collection

```
Collection: "research_docs"
  - documents: 文档片段（chunk）
  - metadatas: {source, chunk_index, title}
  - embeddings: BAAI/bge-small-zh-v1.5 (512维)
```

**Why:** SQLite 单文件零配置适合 Demo，但表结构设计要展示工程思维——有日志表说明考虑了可观测性，有状态字段说明考虑了生命周期管理。

**How to apply:** Phase 0-2 只需实现 reports 表。tool_logs 在 Day 8 加。documents 表 + ChromaDB 在 Phase 3（Day 7）。所有 DB 操作封装在 `backend/database/sqlite.py`。
