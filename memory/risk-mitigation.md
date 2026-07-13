---
name: risk-mitigation
description: 项目风险、概率和应对策略
metadata:
  type: project
---

# 风险与应对

| 风险 | 概率 | 应对 |
|------|------|------|
| DeepSeek API 不稳定 | 中 | 加 retry（exponential backoff，最多 3 次），备选：智谱 GLM API |
| Tavily 搜索质量差 | 中 | 备选 Bing Search API，或降低搜索依赖 |
| ChromaDB Windows 兼容 | 低 | 0.5+ 支持 Windows，备选 FAISS |
| Agent 循环死循环 | 中 | 最大迭代次数硬限制（20）+ 超时保护 + 日志 |
| 开发时间不够 | 中 | 砍 Phase 3（RAG/MCP）保 Phase 0-2 |

**Why:** 提前识别风险，遇到时不慌。每个风险有具体应对方案。

**How to apply:** 遇到对应问题时参考此表。如果出现新风险，加到这个文件中。
