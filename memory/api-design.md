---
name: api-design
description: REST API 端点列表和请求/响应设计
metadata:
  type: project
---

# API 设计

## 端点列表

```
POST   /api/research/stream     # SSE 流式研究（核心端点）
POST   /api/research/sync       # 同步研究（无 SSE）
GET    /api/reports             # 历史报告列表
GET    /api/reports/{id}        # 单个报告详情
GET    /api/reports/{id}/export?format=md|pdf  # 导出
POST   /api/knowledge/upload    # 上传文档到知识库
POST   /api/knowledge/search    # 搜索知识库
DELETE /api/reports/{id}        # 删除报告
```

## 核心请求格式

```json
{
    "task": "分析2026年新能源汽车市场趋势",
    "options": {
        "depth": "deep",
        "sources": ["web", "knowledge_base"],
        "language": "zh-CN",
        "max_sections": 5
    }
}
```

**Why:** API 先于实现设计，确保前后端有清晰的契约。核心端点 `/research/stream` 是 SSE 流式，其他都是标准 REST。

**How to apply:** 实现 API 时严格按此端点列表。新增端点前先更新此文件。
