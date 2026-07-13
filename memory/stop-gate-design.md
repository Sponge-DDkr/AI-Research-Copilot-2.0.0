---
name: stop-gate-design
description: Stop Gate 本地同步校验机制——不额外调 LLM 的质量门禁
metadata:
  type: project
---

# Stop Gate 设计

## 核心思路

**本地同步校验，不额外调 LLM**——节省一次 API 调用。

Stop Gate 不是让 LLM 判断"报告好不好"，而是用规则检查结构化指标。

## 校验维度

1. **Plan 完成度**：所有 plan steps 都标记为 done（非 pending）
2. **章节完整性**：正则匹配 Markdown 标题，检查必需章节（概述、现状分析、趋势判断、建议/结论）
3. **长度检查**：最小 500 字阈值
4. **来源引用**：内容包含 URL 或"来源"标记

## 不通过处理

不通过 → 追加反馈到消息历史 → LLM 收到修正指令 → 继续循环 → 再次校验

## 代码位置

`backend/agent_engine/stop_gate.py` — StopGate 类，`check(state, content) → StopGateResult`

**Why:** 这是区分"调用 API 的 demo"和"工程化产品"的关键设计。每次 LLM 调用都有成本和延迟，Stop Gate 把这些检查本地化，既快又省钱。

**How to apply:** 新增质量检查规则时，加到 `StopGate.check()` 方法中，保持纯规则判断（不调 LLM）。[[agent-engine-design]]
