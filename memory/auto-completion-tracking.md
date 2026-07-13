---
name: auto-completion-tracking
description: 每完成一个开发步骤，自动追加总结到 Completion_Process.md 的对应章节
metadata:
  type: project
---

# 自动进度追踪规则

每完成一个开发 Phase/Day 后，必须自动执行以下操作：

1. **更新 `Completion_Process.md`**：在新章节下追加：
   - 实现了哪些文件
   - 关键代码片段（3-5 行核心逻辑）
   - 当前工具/能力列表
   - 2-4 个可直接运行的 curl 验收用例
2. **更新 `README.md` 开发状态**：将对应 Phase 的 `[ ]` 改为 `[x]`
3. **更新 `Completion_Process.md` 顶部日期**：`最后更新：YYYY-MM-DD`

不需要用户提醒，完成即记。

**Why:** 海绵酱要求每步自动总结，避免事后补文档遗漏细节。实时记录比回忆补写准确。

**How to apply:** 每个 Phase 实现的最后一步，更新此规则涉及的两个文件。[[project-identity]] [[dev-roadmap]]
