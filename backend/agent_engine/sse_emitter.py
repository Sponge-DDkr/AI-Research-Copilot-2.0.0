"""SSE 事件发射器 — Agent 执行过程的实时推送

当前 Phase 1 Day 2 使用同步模式（收集事件列表）。
Phase 2 Day 5 升级为真正的 SSE StreamingResponse。
"""

from typing import Any, Callable, Awaitable


class SseEmitter:
    """事件发射器

    两种模式：
    - sync（当前）：事件存入列表，run() 结束后一次性返回
    - stream（Phase 2）：通过 AsyncGenerator 实时推送
    """

    def __init__(self, mode: str = "sync"):
        self.mode = mode
        self.events: list[dict[str, Any]] = []
        self._stream_handler: Callable[[dict], Awaitable[None]] | None = None

    def set_handler(self, handler: Callable[[dict], Awaitable[None]]):
        """Phase 2：设置流式回调"""
        self._stream_handler = handler
        self.mode = "stream"

    async def emit(self, event_type: str, data: dict[str, Any] | None = None):
        """发射事件"""
        event = {"type": event_type, **(data or {})}
        self.events.append(event)

        if self._stream_handler:
            await self._stream_handler(event)

    # ── 便捷方法 ──

    async def task_started(self, task: str):
        await self.emit("task_started", {"task": task})

    async def plan_created(self, steps: list[dict]):
        await self.emit("plan_created", {"steps": steps})

    async def step_started(self, step_id: str, description: str):
        await self.emit("step_started", {"step_id": step_id, "description": description})

    async def tool_executed(self, tool: str, result_preview: str):
        await self.emit(
            "tool_executed",
            {"tool": tool, "result_preview": result_preview[:300]},
        )

    async def step_completed(self, step_id: str, detail: str = ""):
        await self.emit("step_completed", {"step_id": step_id, "detail": detail})

    async def revision_requested(self, feedback: str):
        await self.emit("revision_requested", {"feedback": feedback})

    async def tool_retry(self, tool: str, attempt: int, reason: str = ""):
        await self.emit("tool_retry", {"tool": tool, "attempt": attempt, "reason": reason})

    async def error(self, message: str):
        await self.emit("error", {"message": message})

    async def complete(self, report: str):
        await self.emit("complete", {"report": report})

    async def rag_trace(
        self,
        tool: str,
        query: str,
        pipeline: str,
        chunks: list[dict],
        warning: str = "",
        score_quality: str = "good",
    ):
        """发射 RAG 检索 Trace 事件（含结构化片段数据，供前端渲染检索卡片）

        Args:
            tool: 工具名（search_knowledge_base / recall_memory）
            query: 检索查询文本
            pipeline: 检索管线描述（"Dense+BM25→RRF→Reranker" / "RRF-Fallback"）
            chunks: 检索片段列表 [{"text", "source", "score", "rank"}, ...]
            warning: 低相关度警告文案（有值时前端红色高亮）
            score_quality: 分数质量标签 — "good" | "borderline" | "poor"
        """
        await self.emit("rag_trace", {
            "tool": tool,
            "query": query,
            "pipeline": pipeline,
            "chunks": chunks,
            "warning": warning,
            "score_quality": score_quality,
        })
