"""Unified Agent Loop — LLM 驱动的自适应 Agent 循环

借鉴 FastGPT v4.15 的 baseLoop 设计：
    while 任务未完成:
        1. LLM 分析当前状态 → 输出思考 + tool_call
        2. 执行 tool_call（带超时保护 + 自动重试）
        3. 把工具结果追加到上下文
        4. Stop Gate 检查是否应该结束（5 项校验）
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Literal

from agent_engine.state import AgentState
from agent_engine.prompt import RESEARCH_AGENT_PROMPT
from agent_engine.router import quick_classify
from agent_engine.sse_emitter import SseEmitter
from tools.registry import registry

# 北京时间
CST = timezone(timedelta(hours=8))

# 导入工具模块以触发 @registry.register() 装饰器

# 导入工具模块以触发 @registry.register() 装饰器
import tools.plan  # noqa: F401
import tools.write  # noqa: F401
import tools.search  # noqa: F401
import tools.memory  # noqa: F401 — save_memory + recall_memory
import tools.knowledge  # noqa: F401 — search_knowledge_base
import tools.review  # noqa: F401 — review_section + fact_check

# ── 常量 ──

TOOL_MAX_RETRIES = 3
MAX_REVISION_ROUNDS = 3

# depth 模式 → 工具白名单（None = 全部工具）
_DEPTH_TOOLS: dict[str, set[str] | None] = {
    "quick": {"web_search"},           # 只允许搜索 + 直接回答
    "auto": None,                       # 全部工具，LLM 自主判断
    "deep": None,                       # 全部工具
}

# depth 模式 → 最大迭代次数上限
_DEPTH_MAX_ITERATIONS: dict[str, int] = {
    "quick": 3,
    "auto": 20,
    "deep": 25,
}


# ═══════════════════════════════════════════════════
# Stop Gate
# ═══════════════════════════════════════════════════


class StopGateResult:
    """Stop Gate 校验结果"""

    def __init__(self, passed: bool, feedback: str = ""):
        self.passed = passed
        self.feedback = feedback


class StopGate:
    """本地同步校验 — Day 4 增强版

    5 项检查：
    1. 内容长度（简单≥20字符 / 复杂≥300字符）
    2. Plan 完成度（≤1 pending）
    3. Markdown 标题结构
    4. 来源引用（用了搜索则必须标注来源）
    5. 章节完整性（复杂任务≥2个二级标题）
    """

    MIN_CHARS_SIMPLE = 20
    MIN_CHARS_COMPLEX = 300
    MIN_HEADINGS_COMPLEX = 2  # 复杂报告至少 2 个 ## 二级标题

    def __init__(self):
        self.revision_count = 0

    def reset(self):
        self.revision_count = 0

    def check(self, state: AgentState, content: str) -> StopGateResult:
        is_simple = len(state.plan) == 0
        content_len = len(content.strip())
        min_chars = self.MIN_CHARS_SIMPLE if is_simple else self.MIN_CHARS_COMPLEX

        # ── 1. 内容长度 ──
        if not content or content_len < self.MIN_CHARS_SIMPLE:
            return StopGateResult(
                passed=False,
                feedback=f"输出内容过短（仅 {content_len} 字符），请生成完整的报告。",
            )

        if not is_simple and content_len < self.MIN_CHARS_COMPLEX:
            return StopGateResult(
                passed=False,
                feedback=(
                    f"报告字数不足（当前 {content_len} 字符，需 ≥ {self.MIN_CHARS_COMPLEX} 字符）。"
                    f"请补充各章节的详细内容。"
                ),
            )

        # ── 2. Plan 完成度 ──
        incomplete = [s for s in state.plan if s.status == "pending"]
        done_count = sum(1 for s in state.plan if s.status == "done")

        if len(incomplete) > 1:
            pending_descs = [s.description for s in incomplete]
            return StopGateResult(
                passed=False,
                feedback=(
                    f"还有 {len(incomplete)} 个步骤未完成：{pending_descs}。"
                    f"当前已完成 {done_count}/{len(state.plan)} 步。请继续执行未完成的步骤。"
                ),
            )

        # 如果有 plan 但所有步骤都还是 pending/未开始，不允许直接输出
        if len(state.plan) > 0 and done_count == 0:
            return StopGateResult(
                passed=False,
                feedback=(
                    f"计划已创建（{len(state.plan)} 个步骤）但尚未开始执行。"
                    f"请使用 write_section 逐步完成每个步骤后再输出最终报告。"
                ),
            )

        # ── 3. Markdown 标题结构 ──
        if state.plan and "##" not in content and "#" not in content:
            return StopGateResult(
                passed=False,
                feedback="报告缺少章节标题（使用 Markdown ## 或 # 格式），请为每个章节添加标题。",
            )

        # ── 4. 来源引用（必须包含可点击的 URL） ──
        if "web_search" in state.tool_results:
            has_url = "http://" in content or "https://" in content
            if not has_url:
                return StopGateResult(
                    passed=False,
                    feedback=(
                        "报告使用了网络搜索结果但参考资料中没有可点击的 URL 链接。"
                        "请在文末添加「## 参考资料」章节，每条使用 Markdown 链接格式："
                        "`1. [文章标题](https://完整URL)`。搜索工具返回的结果中已包含 URL。"
                    ),
                )

        # ── 5. 章节完整性（复杂任务 ≥ 2 个二级标题） ──
        if len(state.plan) >= 3:
            heading_count = content.count("\n## ") + (1 if content.startswith("## ") else 0)
            if heading_count < self.MIN_HEADINGS_COMPLEX:
                return StopGateResult(
                    passed=False,
                    feedback=(
                        f"报告章节不足（当前 {heading_count} 个二级标题，需 ≥ {self.MIN_HEADINGS_COMPLEX} 个）。"
                        f"计划有 {len(state.plan)} 个步骤，每个步骤应对应一个章节。请补充完整。"
                    ),
                )

        # ── 全部通过 ──
        self.revision_count = 0
        return StopGateResult(passed=True)


# ═══════════════════════════════════════════════════
# Error
# ═══════════════════════════════════════════════════


class MaxIterationsError(Exception):
    """Agent 超过最大迭代次数（含兜底失败）"""

    pass


# ═══════════════════════════════════════════════════
# Agent Loop
# ═══════════════════════════════════════════════════


class UnifiedAgentLoop:
    """核心 Agent 循环引擎 — Day 4 增强版

    新增：
    - StopGate 5 项校验（字数、plan、标题、引用、章节）
    - 工具执行自动重试（最多 3 次）
    - 最大迭代前预警 + 兜底输出
    - 修正轮次上限防止死循环
    """

    def __init__(
        self,
        llm: Any,
        max_iterations: int = 15,
    ):
        self.llm = llm
        self.max_iterations = max_iterations
        self.stop_gate = StopGate()
        self.emitter = SseEmitter()

    def _set_emitter(self, emitter: SseEmitter):
        """注入自定义 emitter（Phase 2 SSE 流式用）"""
        self.emitter = emitter

    # ── 公共入口 ──

    async def run(
        self,
        task: str,
        depth: Literal["auto", "quick", "deep"] = "auto",
    ) -> dict[str, Any]:
        """执行 Agent Loop

        Args:
            task: 用户任务
            depth: 执行深度
                - "quick": 轻量模式，只允许搜索 + 直接回答，最多 3 轮
                - "auto": 自动判断（默认），零 token 预检引导 + LLM 自主决策
                - "deep": 深度模式，全部工具可用，最多 20 轮

        Returns:
            {"report": str, "events": list, "iterations": int, "plan_steps": int}
        """
        # ── 第三层：复杂度预检（0 token） ──
        complexity_hint = quick_classify(task)

        # depth 模式覆盖
        depth_max_iterations = min(
            self.max_iterations,
            _DEPTH_MAX_ITERATIONS.get(depth, self.max_iterations),
        )
        self._depth = depth  # 保存供 _call_llm 使用

        state = AgentState(task=task)
        state.emitter = self.emitter  # 注入 emitter 供工具发射 rag_trace
        self.stop_gate.reset()

        await self.emitter.task_started(task)
        await self.emitter.emit("complexity_hint", {
            "bias": complexity_hint["bias"],
            "reason": complexity_hint["reason"],
            "depth": depth,
        })

        for i in range(depth_max_iterations):
            remaining = self.max_iterations - i - 1

            # ── 接近上限预警 ──
            if remaining == 2:
                state.messages.append({
                    "role": "user",
                    "content": (
                        "⚠️ 剩余迭代次数不多（还剩 2 轮）。请整合已有内容，"
                        "尽快完成剩余步骤并输出最终报告。不要再创建新的搜索或分析任务。"
                    ),
                })

            # 1. 调用 LLM
            response = await self._call_llm(state, complexity_hint)

            # 2. 写入 assistant 消息
            assistant_msg = response.choices[0].message
            state.messages.append({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": (
                    [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_msg.tool_calls
                    ]
                    if assistant_msg.tool_calls
                    else None
                ),
            })

            # 3. 有 tool_call → 执行工具
            if assistant_msg.tool_calls:
                for tc in assistant_msg.tool_calls:
                    await self._execute_and_record_tool(tc, state)
            else:
                # 4. 无 tool_call → Stop Gate 校验
                content = assistant_msg.content or ""
                check = self.stop_gate.check(state, content)

                if check.passed:
                    state.final_report = content
                    await self.emitter.emit("stopgate_passed", {
                        "checks": 5,
                        "content_length": len(content.strip()),
                        "plan_done": sum(1 for s in state.plan if s.status == "done"),
                        "plan_total": len(state.plan),
                        "has_url": "http" in content,
                    })
                    await self.emitter.complete(content)
                    return {
                        "report": content,
                        "events": self.emitter.events,
                        "iterations": i + 1,
                        "plan_steps": len(state.plan),
                    }

                # 不通过 → 修正循环
                self.stop_gate.revision_count += 1

                if self.stop_gate.revision_count > MAX_REVISION_ROUNDS:
                    # 修正次数过多，放宽标准通过
                    await self.emitter.error(
                        f"修正 {MAX_REVISION_ROUNDS} 次仍未通过 Stop Gate，放宽标准接受当前输出。"
                        f"最后反馈：{check.feedback}"
                    )
                    state.final_report = content
                    await self.emitter.complete(content)
                    return {
                        "report": content,
                        "events": self.emitter.events,
                        "iterations": i + 1,
                        "plan_steps": len(state.plan),
                    }

                await self.emitter.revision_requested(check.feedback)
                state.messages.append({
                    "role": "user",
                    "content": (
                        f"⚠️ 请修正以下问题：{check.feedback}\n\n"
                        f"请继续完善你的报告，确认所有内容完成后直接输出最终版本。"
                    ),
                })

        # ── 达到最大迭代：兜底尝试 ──
        try:
            state.messages.append({
                "role": "user",
                "content": (
                    "已达到最大迭代次数限制。请基于你已完成的所有步骤和收集到的信息，"
                    "直接输出当前最佳版本的完整报告。不需要再调用任何工具。"
                ),
            })
            response = await self._call_llm(state, complexity_hint)
            content = response.choices[0].message.content or ""

            if content and len(content.strip()) >= 50:
                state.final_report = content
                await self.emitter.complete(content)
                return {
                    "report": content,
                    "events": self.emitter.events,
                    "iterations": self.max_iterations,
                    "plan_steps": len(state.plan),
                }
        except Exception:
            pass

        raise MaxIterationsError(
            f"Agent 超过最大迭代次数 {self.max_iterations} 且兜底输出失败。"
            f"当前 plan: {state.get_plan_summary()}"
        )

    # ── 内部方法 ──

    async def _call_llm(self, state: AgentState, complexity_hint: dict | None = None):
        """调用 LLM，返回完整的 chat completion response"""
        messages = self._build_messages(state, complexity_hint)

        # depth 模式工具过滤
        depth = getattr(self, "_depth", "auto")
        allowed = _DEPTH_TOOLS.get(depth)
        if allowed is not None:
            tools = [
                s for s in registry.get_all_schemas()
                if s["function"]["name"] in allowed
            ]
        else:
            tools = registry.get_all_schemas()

        return await self.llm.chat.completions.create(
            model=self.llm.model,
            messages=messages,
            tools=tools,
            temperature=0.7,
            max_tokens=4000,
        )

    async def _execute_and_record_tool(self, tool_call, state: AgentState):
        """执行工具 + 自动重试 + SSE 推送 + 追加结果到消息历史"""
        from config import get_config

        config = get_config()
        tool_name = tool_call.function.name

        # 解析参数
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            arguments = {}

        # ── SSE: 工具开始执行 ──
        tool_desc = {
            "web_search": f"🔍 搜索: {arguments.get('query', '')[:100]}",
            "create_plan": f"📋 制定执行计划",
            "update_plan": f"📌 更新步骤状态",
            "write_section": f"✍️ 撰写: {arguments.get('title', '')[:100]}",
        }.get(tool_name, f"🔧 执行: {tool_name}")
        await self.emitter.emit("step_started", {
            "step_id": tool_call.id,
            "tool": tool_name,
            "description": tool_desc,
            "arguments": arguments,
        })

        # ── 带重试的执行 ──
        result = None
        last_error = ""
        import time
        t_start = time.time()

        for attempt in range(TOOL_MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    registry.execute(
                        tool_name=tool_name,
                        state=state,
                        llm=self.llm,
                        **arguments,
                    ),
                    timeout=config.tool_timeout_seconds,
                )
                break  # 成功，跳出重试循环
            except asyncio.TimeoutError:
                last_error = (
                    f"[Timeout] 工具 {tool_name} 执行超过 {config.tool_timeout_seconds} 秒"
                )
                if attempt < TOOL_MAX_RETRIES:
                    await self.emitter.tool_retry(
                        tool_name, attempt + 1, reason="timeout"
                    )
            except Exception as e:
                last_error = f"[Error] 工具 {tool_name} 执行异常: {str(e)}"
                if attempt < TOOL_MAX_RETRIES:
                    await self.emitter.tool_retry(
                        tool_name, attempt + 1, reason=str(e)[:100]
                    )

        duration_ms = int((time.time() - t_start) * 1000)

        if result is None:
            # 所有重试耗尽
            result = (
                f"{last_error}（已重试 {TOOL_MAX_RETRIES} 次，放弃）\n"
                f"请尝试其他方案：换关键词重新搜索，或基于已有信息继续。"
            )

        # ── 工具执行日志（调试 + 复盘）──
        log_status = "error" if result is None or last_error else "success"
        if "Timeout" in str(last_error):
            log_status = "timeout"
        try:
            from database import save_tool_log
            save_tool_log(
                task=state.task,
                tool_name=tool_name,
                arguments_json=json.dumps(arguments, ensure_ascii=False),
                result_preview=str(result)[:500] if result else last_error[:500],
                status=log_status,
                duration_ms=duration_ms,
            )
        except Exception:
            pass  # 日志写入失败不中断主流程

        # 追加工具结果到消息历史
        state.messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(result),
        })

        # ── SSE: 工具执行完成 ──
        await self.emitter.tool_executed(tool_name, result)

        # ── SSE: plan_created 特殊事件 ──
        if tool_name == "create_plan":
            plan_steps = [
                {"id": s.id, "description": s.description, "status": s.status}
                for s in state.plan
            ]
            await self.emitter.plan_created(plan_steps)

        # ── SSE: step_completed ──
        if tool_name == "update_plan":
            step_id = arguments.get("step_id", "")
            step = state.get_step_by_id(step_id)
            await self.emitter.step_completed(
                step_id, detail=step.description if step else ""
            )

    def _build_messages(
        self, state: AgentState, complexity_hint: dict | None = None
    ) -> list[dict]:
        """构建发给 LLM 的完整消息列表"""
        plan_summary = state.get_plan_summary()

        # ── 复杂度预检 hint（第三层防御） ──
        precheck_hint = ""
        if complexity_hint:
            bias = complexity_hint["bias"]
            reason = complexity_hint["reason"]
            if bias == "simple":
                precheck_hint = (
                    f"\n\n[系统预检] 该任务初步判定为**简单问题**（{reason}）。"
                    "请直接回答，不要使用任何工具。用 200 字以内完成回答。"
                )
            elif bias == "medium":
                precheck_hint = (
                    f"\n\n[系统预检] 该任务需要实时信息（{reason}）。"
                    "可使用 web_search 搜索，但不需要创建复杂的写作计划。搜索后直接总结即可。"
                )
            elif bias == "complex":
                precheck_hint = (
                    f"\n\n[系统预检] 该任务初步判定为**复杂任务**（{reason}）。"
                    "请使用工具链：搜索→分析→计划→撰写→输出报告。"
                )
            # "auto" 不注入 hint，让 LLM 完全自主判断

        # 如果有搜索结果，在 system 中提示
        search_hint = ""
        if "web_search" in state.tool_results:
            search_hint = (
                "\n\n⚠️ 重要提醒：你已使用过 web_search 工具获取网络信息。"
                "最终报告必须在文末包含「## 参考资料」章节，列出引用来源。"
            )

        today = datetime.now(CST).strftime("%Y年%m月%d日")
        system_content = (
            RESEARCH_AGENT_PROMPT
            + f"\n\n## 系统信息\n\n当前日期：{today}（北京时间）。涉及日期、时间的问题以这个日期为准。"
            + precheck_hint
            + f"\n\n## 当前计划状态\n\n{plan_summary}"
            + search_hint
        )

        # 注：深度研究不自动注入持久记忆。
        # 设计决策（2026-07-18）：深度研究的唯一内容来源是知识库切片 + 网络搜索结果。
        # 持久记忆（agent_memory）是聊天模式的上下文工具，不应干扰研究聚焦。
        # 研究结论仍通过 auto_save_research() 自动归档到 agent_memory，供聊天模式检索。

        messages: list[dict] = [{"role": "system", "content": system_content}]

        for msg in state.messages:
            messages.append(msg)

        if not state.messages:
            messages.append({
                "role": "user",
                "content": f"请完成以下任务：\n\n{state.task}",
            })

        return messages
