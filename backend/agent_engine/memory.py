"""Agent Memory — 四层记忆模型中的 Episodic + Semantic 记忆层

架构：
- 文件层：每份记忆一个 .md 文件，含 YAML frontmatter（仿 Claude Code）
- 向量层：ChromaDB semantic recall，对 description 字段做 embedding
- 索引层：MEMORY.md 索引文件，列出所有记忆的条目

双写路径：
1. Agent 手动 — save_memory 工具 → write_memory_file() + ChromaDB upsert
2. 代码级自动 — auto_save_research() 在研究完成时自动保存结论

记忆使用策略（2026-07-18 更新）：
- 聊天模式：_fetch_relevant_context() 自动检索对话历史（chat_history）+ 持久记忆（agent_memory）
- 深度研究：不自动注入记忆，LLM 仅通过知识库 + web_search 获取内容。
  研究结论仍通过 auto_save_research() 归档到 agent_memory，供聊天模式检索。
  深度研究 Agent 不再主动调用 recall_memory（已从 System Prompt 移除）。
"""

import json
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

CST = timezone(timedelta(hours=8))

# ── 路径 ──
MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
MEMORY_INDEX_PATH = MEMORY_DIR / "MEMORY.md"

# 确保目录存在
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════
# 文件级操作
# ═══════════════════════════════════════════════════

def _slugify(name: str) -> str:
    """将名称转为 kebab-case slug"""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w一-鿿-]", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")[:80] or "memory"


def _format_frontmatter(name: str, description: str, metadata: dict) -> str:
    """生成 YAML frontmatter"""
    meta_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    return (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"metadata:\n"
        + "\n".join(f"  {line}" for line in meta_json.split("\n")[1:-1])
        + "\n---\n\n"
    )


def write_memory_file(
    name: str,
    description: str,
    content: str,
    memory_type: str = "project",
    metadata: Optional[dict] = None,
) -> str:
    """写入一份记忆文件，返回文件路径

    Args:
        name: 记忆短名（kebab-case slug）
        description: 一行描述（用于语义召回）
        content: 记忆正文
        memory_type: user | feedback | project | reference
        metadata: 额外元数据
    """
    slug = _slugify(name)
    file_path = MEMORY_DIR / f"{slug}.md"
    meta = {"type": memory_type, **(metadata or {})}
    frontmatter = _format_frontmatter(slug, description, meta)
    full_content = frontmatter + content

    file_path.write_text(full_content, encoding="utf-8")

    # 更新索引
    _update_index(slug, file_path.name, description)

    return str(file_path)


def _update_index(slug: str, filename: str, description: str):
    """在 MEMORY.md 中添加/更新一条索引"""
    entry = f"- [{slug}]({filename}) — {description}\n"

    if MEMORY_INDEX_PATH.exists():
        lines = MEMORY_INDEX_PATH.read_text(encoding="utf-8").split("\n")
    else:
        lines = ["# MEMORY.md — Agent 记忆索引\n", "\n"]

    # 检查是否已有同名条目
    for i, line in enumerate(lines):
        if f"[{slug}]" in line and line.strip().startswith("-"):
            lines[i] = entry
            MEMORY_INDEX_PATH.write_text("\n".join(lines), encoding="utf-8")
            return

    # 追加新条目
    lines.append(entry)
    MEMORY_INDEX_PATH.write_text("\n".join(lines), encoding="utf-8")


def read_memory_index() -> str:
    """读取 MEMORY.md 索引（Agent Loop 注入用）"""
    if MEMORY_INDEX_PATH.exists():
        return MEMORY_INDEX_PATH.read_text(encoding="utf-8")
    return "（暂无记忆索引）"


def read_all_memory_files() -> list[dict]:
    """读取所有记忆文件，返回列表"""
    memories = []
    if not MEMORY_DIR.exists():
        return memories

    for f in sorted(MEMORY_DIR.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        text = f.read_text(encoding="utf-8")
        # 解析 frontmatter
        name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        desc_match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        # 正文：第一个 --- 和第二个 --- 之间的内容之后
        parts = text.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else text

        memories.append({
            "name": name_match.group(1).strip() if name_match else f.stem,
            "description": desc_match.group(1).strip() if desc_match else "",
            "content": body,
            "file": f.name,
        })

    return memories


# ═══════════════════════════════════════════════════
# ChromaDB 语义层
# ═══════════════════════════════════════════════════


def _get_memory_collection():
    """延迟导入避免循环依赖"""
    from vector import get_memory_collection
    return get_memory_collection()


def index_memory_in_chroma(name: str, description: str, content: str, metadata: Optional[dict] = None):
    """将记忆索引到 ChromaDB（对 description 做 embedding）

    语义召回时用 description 匹配，返回对应的 content。
    """
    collection = _get_memory_collection()
    mem_id = str(uuid.uuid4())

    collection.upsert(
        ids=[mem_id],
        documents=[description],  # embedding 对象
        metadatas=[{
            "name": name,
            "content": content[:2000],  # 截断，完整内容在文件里
            **(metadata or {}),
        }],
    )

    # 使 BM25 缓存失效（文档已变更）
    from vector import _invalidate_bm25_cache
    _invalidate_bm25_cache("agent_memory")

    return mem_id


def recall_memories(query: str, n_results: int = 5) -> list[dict]:
    """语义召回：三阶段检索（Dense+Sparse 混合 → RRF 融合 → Reranker 精排）

    1. Dense 向量检索 + Sparse BM25 各自召回 top-30
    2. RRF 融合双路排名
    3. Cross-Encoder 精排取 top-n

    Reranker 不可用时降级为 RRF 分数排序。

    Args:
        query: 查询文本（与记忆的 description 做语义匹配）
        n_results: 精排后保留的条数

    Returns:
        [{"name": ..., "description": ..., "content": ..., "score": ...}, ...]
        score 为 Reranker 归一化分数（0-1），或降级时为 RRF 分数
    """
    from vector import RETRIEVAL_COARSE_N, RRF_K, hybrid_retrieve, rerank

    collection = _get_memory_collection()

    if collection.count() == 0:
        return []

    # 第一阶段：混合检索（Dense + Sparse → RRF）
    fused_ids, rrf_scores, id_to_data = hybrid_retrieve(
        collection=collection,
        collection_name="agent_memory",
        query=query,
        coarse_n=RETRIEVAL_COARSE_N,
        rrf_k=RRF_K,
        rrf_top_n=RETRIEVAL_COARSE_N,
    )

    memories = []
    if not fused_ids:
        return memories

    # 构建粗排结果列表（按 RRF 融合顺序）
    coarse_items = []
    for i, doc_id in enumerate(fused_ids):
        data = id_to_data.get(doc_id, {})
        meta = data.get("metadata", {})
        description = data.get("document", "")
        content = meta.get("content", "")
        cosine = data.get("cosine_score", 0.0)

        coarse_items.append({
            "id": doc_id,
            "name": meta.get("name", ""),
            "description": description,
            "content": content,
            "cosine_score": cosine,
            "rrf_score": rrf_scores[i] if i < len(rrf_scores) else 0.0,
        })

    # 第二阶段：精排（Cross-Encoder Reranker）
    # 用 description + content 作为 reranker 的文档文本，比只用 description 更准确
    rerank_texts = [
        (item["description"] + " " + item["content"])[:1500]
        for item in coarse_items
    ]
    reranked = rerank(query, rerank_texts, top_n=n_results)

    if reranked:
        for idx, rerank_score in reranked:
            item = coarse_items[idx]
            memories.append({
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "content": item["content"],
                "score": round(rerank_score, 4),
            })
    else:
        # Fallback：按 RRF 分数排序
        coarse_items.sort(key=lambda x: x["rrf_score"], reverse=True)
        for item in coarse_items[:n_results]:
            memories.append({
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "content": item["content"],
                "score": round(item["rrf_score"], 4),
            })

    return memories


# ═══════════════════════════════════════════════════
# 代码级自动保存
# ═══════════════════════════════════════════════════


async def auto_save_research(task: str, report: str, iterations: int):
    """研究完成后自动保存结论到记忆（代码级自动路径）

    从报告中抽取摘要作为记忆内容，存入文件 + ChromaDB。
    """
    # 生成记忆名
    timestamp = datetime.now(CST).strftime("%Y%m%d-%H%M")
    slug = f"research-{_slugify(task)[:40]}-{timestamp}"

    # 从报告前 500 字作为摘要
    summary = report[:500].replace("\n", " ").strip()
    if len(report) > 500:
        summary += "…"

    description = f"研究任务：{task[:100]}"
    content = (
        f"**任务**：{task}\n\n"
        f"**迭代次数**：{iterations}\n\n"
        f"**摘要**：{summary}\n\n"
        f"**Why**: 该研究由 Agent 自动执行，结论可供后续类似任务参考。\n\n"
        f"**How to apply**: 当用户询问相关主题时，recall_memory 可召回此结论作为上下文。"
    )

    # 写入文件
    write_memory_file(
        name=slug,
        description=description,
        content=content,
        memory_type="project",
        metadata={"source": "auto_save_research", "timestamp": timestamp},
    )

    # 写入 ChromaDB
    index_memory_in_chroma(
        name=slug,
        description=description,
        content=content,
        metadata={"source": "auto_save_research"},
    )

    return slug


# ═══════════════════════════════════════════════════
# 对话历史自动存档
# ═══════════════════════════════════════════════════


def _get_chat_history_collection():
    """延迟导入"""
    from vector import get_chat_history_collection
    return get_chat_history_collection()


def save_chat_turn(user_message: str, assistant_reply: str) -> str:
    """存档一轮对话到 ChromaDB chat_history collection

    自动调用，不需 LLM 主动 save_memory。
    用户消息作为 embedding 文本，助手回复存储在 metadata。

    数量上限策略：chat_history 仅负责短期上下文缓存（≤500 条），
    超过上限时自动淘汰最旧的记录。长期记忆由 agent_memory 承担。

    Args:
        user_message: 用户消息（用于语义匹配）
        assistant_reply: 助手回复

    Returns:
        ChromaDB document ID
    """
    import uuid
    from datetime import datetime, timezone, timedelta

    CST = timezone(timedelta(hours=8))
    mem_id = str(uuid.uuid4())
    timestamp = datetime.now(CST).strftime("%Y-%m-%d %H:%M")

    # 截断，ChromaDB metadata 有大小限制
    user_preview = user_message[:300]
    reply_preview = assistant_reply[:500]

    try:
        collection = _get_chat_history_collection()

        # 数量上限控制：超过阈值自动淘汰最旧记录
        MAX_CHAT_HISTORY = 500
        EVICT_COUNT = 100
        current_count = collection.count()
        if current_count >= MAX_CHAT_HISTORY:
            # ChromaDB 按插入顺序存储，get(limit=EVICT_COUNT) 取最旧的
            old = collection.get(limit=EVICT_COUNT, include=[])
            if old and old.get("ids"):
                collection.delete(ids=old["ids"])
                from vector import _invalidate_bm25_cache
                _invalidate_bm25_cache("chat_history")

        collection.upsert(
            ids=[mem_id],
            documents=[user_preview],  # 对用户消息做 embedding
            metadatas=[{
                "user_message": user_preview,
                "assistant_reply": reply_preview,
                "timestamp": timestamp,
            }],
        )

        # 使 BM25 缓存失效（文档已变更）
        from vector import _invalidate_bm25_cache
        _invalidate_bm25_cache("chat_history")

        return mem_id
    except Exception:
        return ""


def get_recent_chat_turns(n: int = 10) -> list[dict]:
    """按时间戳取最近 N 轮对话（不经过语义检索）

    用于处理时间限定查询（"刚刚问了什么""今天聊了什么"）——
    这类查询的意图是时间指向，不是语义匹配，语义检索反而会命中旧对话。

    Args:
        n: 返回条数

    Returns:
        按时间戳降序排列的最近对话列表
    """
    try:
        collection = _get_chat_history_collection()
    except Exception:
        return []

    total = collection.count()
    if total == 0:
        return []

    # ChromaDB 按插入顺序存储，需取全量后按时间戳排序
    # chat_history 上限 500 条，全量取性能可接受
    result = collection.get(limit=min(total, 500), include=["metadatas"])
    if not result or not result.get("ids"):
        return []

    turns = []
    for i, doc_id in enumerate(result["ids"]):
        meta = result["metadatas"][i] if result.get("metadatas") else {}
        turns.append({
            "id": doc_id,
            "user_message": meta.get("user_message", ""),
            "assistant_reply": meta.get("assistant_reply", ""),
            "timestamp": meta.get("timestamp", ""),
        })

    # 按时间戳降序排列（最新的在前）
    turns.sort(key=lambda t: t.get("timestamp", ""), reverse=True)

    return turns[:n]


def recall_chat_history(query: str, n_results: int = 3) -> list[dict]:
    """从对话历史中召回相关轮次（三阶段：Dense+Sparse → RRF → Reranker）

    1. Dense 向量检索 + Sparse BM25 各自召回 top-30
    2. RRF 融合双路排名
    3. Cross-Encoder 精排取 top-n

    Reranker 不可用时降级为 RRF 分数排序。

    Args:
        query: 查询文本
        n_results: 精排后保留的条数

    Returns:
        [{"id": ..., "user_message": ..., "assistant_reply": ..., "score": ..., "timestamp": ...}, ...]
        score 为 Reranker 归一化分数（0-1），或降级时为 RRF 分数
    """
    from vector import RETRIEVAL_COARSE_N, RRF_K, hybrid_retrieve, rerank

    try:
        collection = _get_chat_history_collection()
    except Exception:
        return []

    if collection.count() == 0:
        return []

    # 第一阶段：混合检索（Dense + Sparse → RRF）
    try:
        fused_ids, rrf_scores, id_to_data = hybrid_retrieve(
            collection=collection,
            collection_name="chat_history",
            query=query,
            coarse_n=RETRIEVAL_COARSE_N,
            rrf_k=RRF_K,
            rrf_top_n=RETRIEVAL_COARSE_N,
        )
    except Exception:
        return []

    if not fused_ids:
        return []

    # 构建粗排结果列表（按 RRF 融合顺序）
    coarse_items = []
    for i, doc_id in enumerate(fused_ids):
        data = id_to_data.get(doc_id, {})
        meta = data.get("metadata", {})

        coarse_items.append({
            "id": doc_id,
            "user_message": meta.get("user_message", ""),
            "assistant_reply": meta.get("assistant_reply", ""),
            "timestamp": meta.get("timestamp", ""),
            "cosine_score": data.get("cosine_score", 0.0),
            "rrf_score": rrf_scores[i] if i < len(rrf_scores) else 0.0,
        })

    # 第二阶段：精排（Cross-Encoder Reranker）
    # 用 user_message + assistant_reply 拼接作为 reranker 的文档文本
    rerank_texts = [
        (item["user_message"] + " " + item["assistant_reply"])[:1500]
        for item in coarse_items
    ]
    reranked = rerank(query, rerank_texts, top_n=n_results)

    turns = []
    if reranked:
        for idx, rerank_score in reranked:
            item = coarse_items[idx]
            turns.append({
                "id": item["id"],
                "user_message": item["user_message"],
                "assistant_reply": item["assistant_reply"],
                "timestamp": item["timestamp"],
                "score": round(rerank_score, 4),
            })
    else:
        # Fallback：按 RRF 分数排序
        coarse_items.sort(key=lambda x: x["rrf_score"], reverse=True)
        for item in coarse_items[:n_results]:
            turns.append({
                "id": item["id"],
                "user_message": item["user_message"],
                "assistant_reply": item["assistant_reply"],
                "timestamp": item["timestamp"],
                "score": round(item["rrf_score"], 4),
            })

    # 时间衰减：语义分 × 时间因子，近期对话优先
    turns = _apply_time_decay(turns, query)
    return turns


def _apply_time_decay(
    turns: list[dict],
    query: str = "",
    max_age_hours: int = 72,
) -> list[dict]:
    """对聊天历史召回结果应用时间衰减

    纯语义检索无法区分"今天下午问了什么"和"两周前问了什么"——
    两者语义相似度可能相同。时间衰减让近期对话在同等语义匹配下优先。

    衰减策略（指数衰减，半衰期 24h）：
    - 1 小时内：权重 ≈ 1.0（几乎不衰减）
    - 24 小时：权重 = 0.5
    - 3 天：权重 = 0.125
    - 7 天：权重 ≈ 0.008

    同时检测查询中是否含时间限定词（刚/刚才/今天/最近/上一次），
    含时限词时大幅惩罚超过 24 小时的旧记录（额外 ×0.3）。

    Args:
        turns: recall_chat_history 的结果列表
        query: 用户查询（用于检测时间限定词）
        max_age_hours: 超过此时长的记录直接过滤（0 表示不过滤）

    Returns:
        按衰减后分数降序排列的结果列表，过滤掉分数过低的条目
    """
    from datetime import datetime, timezone, timedelta
    from math import exp

    if not turns:
        return turns

    CST = timezone(timedelta(hours=8))
    now = datetime.now(CST)

    # 检测用户是否用了时间限定词
    time_bound_keywords = [
        "刚才", "刚刚", "刚问", "刚才问", "上一次", "上次",
        "今天", "今天问", "最近", "最新的", "当前",
        "刚刚说", "刚才说", "之前问",
    ]
    has_time_binding = any(kw in query for kw in time_bound_keywords)

    HALF_LIFE_HOURS = 24.0
    decayed = []
    for turn in turns:
        ts_str = turn.get("timestamp", "")
        if not ts_str:
            decayed.append(turn)
            continue

        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M").replace(tzinfo=CST)
        except ValueError:
            decayed.append(turn)
            continue

        age_hours = (now - ts).total_seconds() / 3600

        # 超过最大时限的直接过滤
        if max_age_hours > 0 and age_hours > max_age_hours:
            continue

        # 指数衰减：weight = 2^(-age / half_life)
        time_weight = 2 ** (-age_hours / HALF_LIFE_HOURS)

        # 时间限定词惩罚：用户说"刚才"但记录已超过 24h → 大幅降权
        if has_time_binding and age_hours > 24:
            time_weight *= 0.3

        turn["score"] = round(turn["score"] * time_weight, 4)
        # 保留原始分数用于调试对比
        turn["age_hours"] = round(age_hours, 1)
        decayed.append(turn)

    # 按衰减后分数降序排列
    decayed.sort(key=lambda x: x["score"], reverse=True)

    # 过滤：衰减后分数太低的结果不再返回
    SCORE_FLOOR = 0.05
    decayed = [t for t in decayed if t["score"] >= SCORE_FLOOR]

    return decayed


# ═══════════════════════════════════════════════════
# 记忆上下文构建（聊天模式 System Prompt 用）
# ═══════════════════════════════════════════════════
#
# 注意（2026-07-18）：深度研究不再调用此函数。
# 深度研究的内容来源是知识库切片 + 网络搜索结果，不需要持久记忆注入。
# 此函数仅供聊天模式的 _build_chat_system_prompt 使用（如果将来需要）。


def build_memory_context(task: str) -> str:
    """构建要注入 System Prompt 的记忆上下文（当前仅供聊天模式使用）

    含两部分：
    1. MEMORY.md 索引（文件层概览）
    2. ChromaDB 语义召回（与当前任务最相关的记忆）

    深度研究不再调用此函数——研究聚焦于知识库+web_search，
    持久记忆仅由 auto_save_research() 写入，供聊天模式检索。

    Args:
        task: 当前任务描述，用于语义召回

    Returns:
        记忆上下文字符串，可直接追加到 System Prompt
    """
    parts: list[str] = []

    # 1. MEMORY.md 索引
    index = read_memory_index()
    parts.append(f"## 记忆索引\n\n{index}")

    # 2. ChromaDB 召回
    recalled = recall_memories(task, n_results=3)
    if recalled:
        parts.append("\n## 相关记忆\n")
        for i, mem in enumerate(recalled, 1):
            parts.append(
                f"### {i}. {mem['name']}（相关度: {mem['score']:.0%}）\n\n"
                f"{mem['content']}\n"
            )

    return "\n".join(parts)
