---
name: test-strategy
description: 测试分层策略和关键测试用例
metadata:
  type: project
---

# 测试策略

## 测试分层

```
E2E（可选）           — 完整研究任务端到端
API 集成测试（pytest） — FastAPI TestClient，测端点→Agent→DB 链路
单元测试（pytest）     — Agent Loop 循环逻辑、Stop Gate 校验、每个 Tool、ToolRegistry
```

## 关键测试用例（agent_engine）

- `test_simple_task_direct_answer` — 简单问题不创建 Plan，直接回答
- `test_complex_task_creates_plan` — 复杂问题先创建计划再逐步执行
- `test_stop_gate_rejects_incomplete` — Stop Gate 拒绝不完整报告→触发修正循环
- `test_tool_error_retry` — 工具失败→自动重试→最多 3 次
- `test_max_iterations_protection` — 超最大迭代次数抛出异常

## 测试策略

LLM 返回用 Mock：`AsyncMock` 模拟 `llm.chat()` 的不同返回（有 tool_call / 无 tool_call / 异常）。

**Why:** 测试策略和 Mock 设计体现工程的严谨性——写的是工程代码，不是 demo。

**How to apply:** Phase 4（Day 9）集中写测试。但 Day 2-4 写 Agent Engine 时就要考虑可测试性——LLM 调用必须通过依赖注入（`__init__` 传入 llm 参数），不能硬编码。
