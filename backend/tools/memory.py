"""记忆工具 — save_memory + recall_memory，注册到 Agent Loop

save_memory：深度研究 LLM 可在研究过程中主动调用，保存重要结论。
recall_memory：已从深度研究 System Prompt 移除（2026-07-18），
  深度研究的内容来源是知识库 + web_search，不依赖持久记忆。
  此工具保留供聊天模式使用。
"""

from typing import Any

from tools.registry import registry
from agent_engine.memory import (
    write_memory_file,
    index_memory_in_chroma,
    recall_memories,
    read_memory_index,
)


@registry.register(
    name="save_memory",
    description=(
        "将重要信息保存到持久记忆中，供后续研究和对话引用。"
        "适用于：保存研究结论、记录用户偏好、存储经验教训、标记重要发现。"
        "记忆会自动索引到向量库，支持语义检索。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "记忆的名称（简短的 kebab-case 标识，如 'user-prefers-bullet-points'）",
            },
            "description": {
                "type": "string",
                "description": "一行描述，用于语义检索匹配。例如：'用户喜欢用要点列表而非长段落'",
            },
            "content": {
                "type": "string",
                "description": "记忆的完整内容，推荐包含 **Why**（为什么）和 **How to apply**（如何应用）两部分",
            },
            "memory_type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "记忆类型：user=用户信息，feedback=用户反馈，project=项目结论，reference=外部参考",
                "default": "project",
            },
        },
        "required": ["name", "description", "content"],
    },
)
async def save_memory(
    state: Any,
    llm: Any,
    name: str = "",
    description: str = "",
    content: str = "",
    memory_type: str = "project",
) -> str:
    """Agent 手动保存记忆 — 双写（文件 + ChromaDB）"""
    if not name.strip():
        return "❌ 记忆名称不能为空"
    if not description.strip():
        return "❌ 记忆描述不能为空"
    if not content.strip():
        return "❌ 记忆内容不能为空"

    try:
        # 文件写入
        file_path = write_memory_file(
            name=name.strip(),
            description=description.strip(),
            content=content.strip(),
            memory_type=memory_type,
        )

        # ChromaDB 索引
        mem_id = index_memory_in_chroma(
            name=name.strip(),
            description=description.strip(),
            content=content.strip(),
        )

        return (
            f"✅ 记忆已保存\n"
            f"- 文件：{file_path}\n"
            f"- 向量ID：{mem_id}\n"
            f"- 类型：{memory_type}\n"
            f"- 描述：{description[:200]}"
        )
    except Exception as e:
        return f"❌ 保存记忆失败：{str(e)}"


@registry.register(
    name="recall_memory",
    description=(
        "从记忆库中检索相关的历史记忆和研究结论。"
        "适用于：查找之前的研究结果、回忆用户偏好、获取经验教训、检查是否研究过相似主题。"
        "返回最相关的记忆内容和相似度分数。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，描述你想查找的内容。尽量具体，如 '用户对报告格式的偏好' 或 '新能源汽车市场研究的结论'",
            },
            "n_results": {
                "type": "integer",
                "description": "返回的记忆条数，默认 3，最多 5",
                "default": 3,
            },
        },
        "required": ["query"],
    },
)
async def recall_memory(
    state: Any,
    llm: Any,
    query: str = "",
    n_results: int = 3,
) -> str:
    """Agent 语义召回记忆"""
    if not query.strip():
        return "❌ 搜索查询不能为空"

    n_results = max(1, min(n_results, 5))

    try:
        memories = recall_memories(query, n_results=n_results)

        # ── 低相关度检测 ──
        best_score = memories[0].get("score", 0) if memories else 0.0
        scores_list = [m.get("score", 0) for m in memories] if memories else []
        median_score = sorted(scores_list)[len(scores_list) // 2] if scores_list else 0.0
        min_score = min(scores_list) if scores_list else 0.0
        score_spread = best_score - min_score

        is_low_relevance = (
            best_score < 0.3
            or (score_spread < 0.1 and best_score < 0.5)
        )
        # 分数坍塌：仅在分数低且集中时触发。高分集中（如 0.85/0.83/0.80）说明多份记忆都相关
        is_score_collapse = score_spread < 0.08 and median_score < 0.5 and len(scores_list) > 1

        warning_text = ""
        if is_low_relevance:
            reasons = []
            if best_score < 0.3:
                reasons.append(f"最佳匹配仅 {best_score:.0%}")
            if is_score_collapse:
                reasons.append(f"分数分布坍塌（spread={score_spread:.3f}）")
            reason_str = "；".join(reasons)
            warning_text = (
                f"⚠️ 低相关度：{reason_str}。"
                f"记忆中可能没有与「{query}」相关的内容。"
            )

        # ── 发射 RAG Trace 事件 ──
        try:
            emitter = getattr(state, "emitter", None)
            if emitter and memories:
                trace_chunks = []
                for i, mem in enumerate(memories):
                    trace_chunks.append({
                        "text": mem.get("content", "")[:200],
                        "source": mem.get("name", "记忆"),
                        "chunk_index": mem.get("description", "")[:60],
                        "score": mem.get("score", 0),
                        "rank": i + 1,
                    })
                await emitter.rag_trace(
                    tool="recall_memory",
                    query=query.strip(),
                    pipeline="Dense+BM25→RRF→Reranker（agent_memory）",
                    chunks=trace_chunks,
                    warning=warning_text,
                    score_quality=(
                        "poor" if is_score_collapse
                        else "borderline" if is_low_relevance
                        else "good"
                    ),
                )
        except Exception:
            pass  # rag_trace 失败不影响主流程

        if not memories:
            # 也检查一下文件层有没有
            index = read_memory_index()
            if "暂无记忆" in index:
                return "📭 记忆库为空，还没有保存过任何记忆。你可以用 save_memory 工具保存第一条记忆。"

            return (
                f"🔍 未找到与「{query}」语义相关的记忆。\n\n"
                f"当前记忆索引中有以下条目（但语义不匹配）：\n\n{index}"
            )

        lines = [f"## 🧠 记忆召回结果：与「{query}」最相关的 {len(memories)} 条记忆\n"]
        for i, mem in enumerate(memories, 1):
            lines.append(f"### {i}. {mem['name']}（相关度: {mem['score']:.0%}）")
            lines.append(f"**描述**：{mem['description']}")
            lines.append(f"**内容**：{mem['content'][:500]}")
            lines.append("")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 记忆召回失败：{str(e)}"
