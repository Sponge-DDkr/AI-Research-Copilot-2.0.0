---
name: agent-engine-design
description: Unified Agent Loop 核心架构设计——为什么不走固定管线，以及循环机制
metadata:
  type: project
---

# Agent Engine 设计（核心创新点）

## 为什么不走固定管线

原方案是固定的 5-Agent 管线（Planner → Research → Analyst → Writer → Reviewer），问题：
- 简单问题不需要完整流程，浪费时间
- 复杂问题可能需要交替执行（Research + Analyst 多次往返），固定管线做不到
- 新增 Agent 角色要改管线代码，扩展性差

## Unified Agent Loop（借鉴 FastGPT v4.15）

核心思路：**LLM 自己决定下一步做什么**，不是预设的管线。

```
while 任务未完成:
    1. LLM 分析当前状态 → 输出思考 + tool_call
    2. 执行 tool_call（可能是 research / analyze / write / review）
    3. 把工具结果追加到上下文
    4. Stop Gate 检查是否应该结束
return 最终结果
```

## 不同复杂度处理

- 简单问题 → 直接回答（0 次 tool_call）
- 中等复杂 → search → analyze → write（3-5 次 tool_call）
- 高度复杂 → plan → search×3 → analyze×2 → write → review（10+ 次，可回退）

同一个引擎处理所有复杂度等级。

**Why:** 这是整个项目最核心的技术决策。固定管线是"为最复杂情况设计，简单情况也走全程"；Unified Loop 是"LLM 自适应复杂度"。

**How to apply:** 实现时 Agent Engine 的 `run()` 方法是唯一入口，不设任何 hard-coded 的步骤顺序。所有能力都暴露为 Tool，由 LLM 自主调度。[[tool-layer]] [[stop-gate-design]]
