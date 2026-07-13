"""Research API — Agent Loop 的执行端点"""

import asyncio
import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_engine.loop import UnifiedAgentLoop, MaxIterationsError
from agent_engine.sse_emitter import SseEmitter
from llm_client import create_llm_client

router = APIRouter(tags=["research"])


class ResearchRequest(BaseModel):
    task: str = Field(
        ...,
        description="研究任务描述",
        min_length=1,
        max_length=5000,
        examples=["写一篇关于人工智能的短文"],
    )
    max_iterations: int = Field(
        default=15,
        ge=1,
        le=30,
        description="最大迭代次数",
    )
    depth: Literal["auto", "quick", "deep"] = Field(
        default="auto",
        description=(
            "执行深度："
            "auto=自动判断（默认），"
            "quick=轻量模式（只允许搜索+直接回答，最多3轮），"
            "deep=深度模式（全部工具可用）"
        ),
    )


class ResearchResponse(BaseModel):
    report: str = Field(..., description="最终生成的报告")
    iterations: int = Field(..., description="实际迭代次数")
    plan_steps: int = Field(..., description="计划步骤总数")
    events: list[dict] = Field(default_factory=list, description="执行过程事件")


@router.post("/research/sync", response_model=ResearchResponse)
async def research_sync(request: ResearchRequest) -> ResearchResponse:
    """
    同步研究端点。

    提交一个任务，Agent Loop 自动规划并执行，返回完整报告。

    depth 模式：
    - auto：零 token 预检 + LLM 自主判断复杂度（默认推荐）
    - quick：轻量，只搜索+直接回答，最多 3 轮（适合简单问题）
    - deep：全工具链，最多 20 轮（适合深度研究）
    """
    try:
        llm = create_llm_client()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    loop = UnifiedAgentLoop(
        llm=llm,
        max_iterations=request.max_iterations,
    )

    try:
        result = await loop.run(task=request.task, depth=request.depth)
    except MaxIterationsError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent 执行失败: {str(e)}")

    return ResearchResponse(
        report=result["report"],
        iterations=result["iterations"],
        plan_steps=result["plan_steps"],
        events=result["events"],
    )


# ═══════════════════════════════════════════════════
# SSE 流式端点 — Phase 2 Day 5
# ═══════════════════════════════════════════════════


async def _sse_event_generator(queue: asyncio.Queue, loop: UnifiedAgentLoop, task: str, depth: str):
    """SSE 事件生成器 — 从 asyncio.Queue 读取事件并格式化为 SSE。

    在后台运行 Agent Loop，同时不断从队列中取出事件 yield 给客户端。
    研究完成后自动保存报告到数据库。
    """
    # 启动 Agent Loop 作为后台任务
    loop_task = asyncio.ensure_future(loop.run(task=task, depth=depth))

    # 收集 all events 用于数据库存储
    all_events: list[dict] = []

    # 持续从队列读取事件，直到收到 "done" 信号
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            if loop_task.done():
                break
            continue

        if event is None:
            break

        all_events.append(event)
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    # 确保 loop_task 完成并获取结果
    loop_result = None
    if not loop_task.done():
        loop_task.cancel()
        try:
            loop_result = await loop_task
        except asyncio.CancelledError:
            pass
    else:
        try:
            loop_result = loop_task.result()
        except Exception:
            pass

    # ── 自动保存报告到数据库 ──
    if loop_result and loop_result.get("report"):
        import json as _json
        from database import save_report
        save_report(
            task=task,
            report=loop_result["report"],
            depth=depth,
            iterations=loop_result.get("iterations", 0),
            plan_steps=loop_result.get("plan_steps", 0),
            events_json=_json.dumps(all_events, ensure_ascii=False),
        )

        # ── 自动保存研究结论到记忆（代码级自动路径）──
        try:
            from agent_engine.memory import auto_save_research
            await auto_save_research(
                task=task,
                report=loop_result["report"],
                iterations=loop_result.get("iterations", 0),
            )
        except Exception:
            pass  # 记忆保存失败不阻塞主流程

    yield "data: [DONE]\n\n"


@router.post("/research/stream")
async def research_stream(request: ResearchRequest):
    """
    SSE 流式研究端点。

    提交任务后，通过 Server-Sent Events 实时推送 Agent 执行过程：
    - task_started: 任务开始
    - plan_created: Agent 创建了执行计划
    - tool_executed: 工具执行完成
    - step_completed: 步骤完成
    - revision_requested: Stop Gate 要求修正
    - tool_retry: 工具重试
    - error: 错误信息
    - complete: 最终报告完成

    前端可通过 EventSource 或 fetch + ReadableStream 消费。
    """
    try:
        llm = create_llm_client()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    loop = UnifiedAgentLoop(
        llm=llm,
        max_iterations=request.max_iterations,
    )

    # 创建异步队列作为事件通道
    queue: asyncio.Queue = asyncio.Queue()

    # 创建流式 emitter 并绑定到 loop
    emitter = SseEmitter()

    async def stream_handler(event: dict):
        """SSE 事件回调：将事件放入队列"""
        await queue.put(event)

    emitter.set_handler(stream_handler)
    loop._set_emitter(emitter)

    return StreamingResponse(
        _sse_event_generator(queue, loop, request.task, request.depth),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
