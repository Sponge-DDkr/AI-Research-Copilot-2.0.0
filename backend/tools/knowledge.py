"""知识库工具 — search_knowledge_base，从用户上传的文档中检索信息

与记忆工具分离：
- memory tools → agent_memory collection（Agent 的研究经验/结论）
- knowledge tool → knowledge_base collection（用户上传的外部文档）

检索策略：三阶段（Dense + Sparse 混合 → RRF 融合 → Reranker 精排）
- 第一阶段（Dense 向量 + Sparse BM25）：各自召回 top-30，互补覆盖
  - Dense：BGE-large-zh 语义匹配，擅长同义词/概括性查询
  - Sparse：BM25 关键词匹配，擅长精确术语/版本号/API 名
- 第二阶段（RRF 融合）：Reciprocal Rank Fusion 合并双路排名
- 第三阶段（Reranker）：Cross-Encoder 精排 top-n
- 经多轮人工测试（精确检索、语义区分、否定逻辑等场景），三阶段检索质量相比纯向量有明显提升
"""

import uuid
from typing import Any

from tools.registry import registry
from vector import (
    get_knowledge_collection,
    RETRIEVAL_COARSE_N,
    RETRIEVAL_FINE_N,
    RRF_K,
    hybrid_retrieve,
    rerank,
    _invalidate_bm25_cache,
)

# 本模块使用的 collection 名
_COLLECTION = "knowledge_base"


@registry.register(
    name="search_knowledge_base",
    description=(
        "从用户上传的知识库文档中检索相关信息。"
        "适用于：查找用户上传的行业报告、论文、技术文档中的内容。"
        "如果用户明确提到'我的文档'、'上传的资料'、'知识库'等，优先使用此工具。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询，从知识库文档中查找相关内容。使用自然语言描述。",
            },
            "n_results": {
                "type": "integer",
                "description": "返回的结果条数，默认 3，最多 5",
                "default": 3,
            },
        },
        "required": ["query"],
    },
)
async def search_knowledge_base(
    state: Any,
    llm: Any,
    query: str = "",
    n_results: int = 3,
) -> str:
    """从知识库中检索相关文档片段（三阶段：Dense+Sparse → RRF → Reranker）"""
    if not query.strip():
        return "❌ 搜索查询不能为空"

    n_results = max(1, min(n_results, 5))

    try:
        collection = get_knowledge_collection()

        if collection.count() == 0:
            return (
                "📭 知识库为空，尚未上传任何文档。\n"
                "用户可以通过前端 KnowledgeUpload 组件上传 PDF/TXT/MD 文件。"
            )

        # ── 第一阶段：混合检索（Dense 向量 + Sparse BM25 → RRF 融合）──
        fused_ids, rrf_scores, id_to_data = hybrid_retrieve(
            collection=collection,
            collection_name=_COLLECTION,
            query=query.strip(),
            coarse_n=RETRIEVAL_COARSE_N,
            rrf_k=RRF_K,
            rrf_top_n=RETRIEVAL_COARSE_N,
        )

        if not fused_ids:
            return f"🔍 在知识库中未找到与「{query}」相关的内容。请尝试不同的搜索词。"

        # 构建粗排结果列表（按 RRF 融合后的顺序）
        coarse_items = []
        coarse_docs = []
        for doc_id in fused_ids:
            data = id_to_data.get(doc_id, {})
            doc = data.get("document", "")
            meta = data.get("metadata", {})
            coarse_items.append({"id": doc_id, "doc": doc, "meta": meta})
            coarse_docs.append(doc)

        # ── 第二阶段：精排（Cross-Encoder Reranker）──
        reranked = rerank(query.strip(), coarse_docs, top_n=n_results)

        if reranked:
            result_indices = [r[0] for r in reranked]
            result_scores = [r[1] for r in reranked]
            pipeline = "Dense+BM25→RRF→Reranker"
        else:
            # Fallback：按 RRF 分数
            result_indices = list(range(min(n_results, len(coarse_items))))
            result_scores = [rrf_scores[i] if i < len(rrf_scores) else 0.0 for i in result_indices]
            pipeline = "Dense+BM25→RRF（Reranker 未启用）"

        # ── 低相关度检测（多因子综合判断）──
        # CrossEncoder v5.x 分数已在 [0, 1]，无需额外归一化
        best_score = result_scores[0] if result_scores else 0.0
        median_score = sorted(result_scores)[len(result_scores) // 2] if result_scores else 0.0
        min_score = min(result_scores) if result_scores else 0.0
        score_spread = best_score - min_score

        # 三因子综合判断低相关度：
        #   因子1 — 绝对分数：最佳 < 0.3（模型明确判断不相关）
        #   因子2 — 分数坍塌：spread < 0.1（模型无法区分，所有文档差不多差）
        #   因子3 — 头尾比：best/median < 2.0（没有明显更优的文档）
        is_low_relevance = (
            best_score < 0.3
            or (score_spread < 0.1 and best_score < 0.5)
        )
        is_score_collapse = score_spread < 0.08

        warning_text = ""
        if is_low_relevance:
            reasons = []
            if best_score < 0.3:
                reasons.append(f"最佳匹配仅 {best_score:.0%}")
            if score_spread < 0.1 and best_score < 0.5:
                reasons.append(f"分数分布坍塌（spread={score_spread:.3f}），模型无法有效区分")
            reason_str = "；".join(reasons)
            warning_text = (
                f"⚠️ 低相关度：{reason_str}。"
                f"知识库中可能没有与「{query}」相关的内容，必须改用 web_search 工具！"
            )

        # ── 发射 RAG Trace 事件（结构化数据，供前端渲染检索质量卡片）──
        try:
            emitter = getattr(state, "emitter", None)
            if emitter:
                trace_chunks = []
                for rank, idx in enumerate(result_indices):
                    if idx >= len(coarse_items):
                        continue
                    item = coarse_items[idx]
                    trace_chunks.append({
                        "text": item["doc"][:200],
                        "source": item["meta"].get("source_file", "未知来源"),
                        "chunk_index": str(item["meta"].get("chunk_index", "?")),
                        "score": round(result_scores[rank], 4),
                        "rank": rank + 1,
                    })
                await emitter.rag_trace(
                    tool="search_knowledge_base",
                    query=query.strip(),
                    pipeline=pipeline,
                    chunks=trace_chunks,
                    warning=warning_text,
                    # 附加诊断信息供前端展示
                    score_quality=(
                        "poor" if is_score_collapse
                        else "borderline" if is_low_relevance
                        else "good"
                    ),
                )
        except Exception:
            pass  # rag_trace 失败不影响主流程

        # ── 格式化 Markdown 输出 ──
        lines = [f"## 📚 知识库检索结果：与「{query}」最相关的 {len(result_indices)} 条\n"]

        for rank, idx in enumerate(result_indices):
            if idx >= len(coarse_items):
                continue
            item = coarse_items[idx]
            doc = item["doc"]
            meta = item["meta"]
            score = result_scores[rank]

            source = meta.get("source_file", "未知来源")
            chunk_idx = meta.get("chunk_index", "?")

            lines.append(f"### {rank+1}. {source}（片段 {chunk_idx}，相关度: {score:.0%}）")
            lines.append(f"{doc[:800]}")
            lines.append("")

        # 低相关度强提示（让 Agent 必须切换 web_search）
        if is_low_relevance:
            lines.append("---")
            lines.append("## ⛔ 严重警告：知识库检索质量不足")
            lines.append("")
            if best_score < 0.3:
                lines.append(
                    f"- 最佳匹配相关度仅 **{best_score:.0%}**，"
                    f"说明知识库中没有与「{query}」真正相关的文档。"
                )
            if is_score_collapse:
                lines.append(
                    f"- 所有检索结果分数高度接近（spread={score_spread:.3f}），"
                    f"Reranker 无法有效区分，检索结果不可靠。"
                )
            lines.append("")
            lines.append(
                "**🚫 禁止根据以上不相关文档作答！** "
                "你必须立即调用 `web_search` 工具进行网络检索，"
                "并在回复中明确说明：「知识库未找到相关内容，以下信息来自网络搜索」。"
            )
            lines.append("")
            lines.append(
                "如果 web_search 也不可用，请如实告知用户"
                "「当前知识库和网络搜索均无法回答此问题」，不要编造内容。"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"❌ 知识库检索失败：{str(e)}"
