---
name: project-identity
description: AI Research Copilot 项目的核心定位、一句话描述和价值主张
metadata:
  type: project
---

# AI Research Copilot — 项目身份

**一句话**：用户输入复杂研究主题 → 单 Agent 自主调用搜索/分析/写作等 9 个工具（拆解任务 → 搜索资料 → 分析数据 → 生成报告 → 质量审核 → 导出文件），全程 SSE 实时推送进度。

**核心价值**：将传统 4-8 小时的研究报告工作压缩到 2-5 分钟，且每一步思考过程实时可见。

**与普通 ChatGPT 套壳的区别**：
- 单 Agent 多工具自主研究（非一问一答）
- SSE 实时展示工作状态（非黑盒 loading）
- review_section + fact_check 工具 + Stop Gate 质量校验（非"输出靠运气"）
- RAG 检索 + 来源引用（可追溯）
- 报告可导出 Markdown/PDF，知识存入向量库（可复用）

**Why:** 这是项目的"北极星"——所有架构决策都应服务于这一定位。不是做聊天机器人，是做自主研究助手。

**How to apply:** 每次做架构决策时回看这个文件，确认新设计不偏离核心价值主张。
