"""向量数据库基础设施 — ChromaDB 统一嵌入层 + Cross-Encoder Reranker + BM25 混合检索

架构：
- 一个 EmbeddingFunction 实例，三个 Collection：
  - agent_memory：存储 Agent 记忆（Episodic + Semantic 记忆）
  - knowledge_base：存储用户上传的文档切片
  - chat_history：自动存档的对话轮次
- Embedding 模型：BAAI/bge-large-zh-v1.5 (1024维)，专为中英文混合场景优化
- Reranker：BAAI/bge-reranker-v2-m3 Cross-Encoder
- BM25：rank_bm25 + jieba 中文分词，Sparse 关键词检索

三阶段检索（Dense 向量 + Sparse BM25 → RRF 融合 → Reranker 精排）：
- 第一阶段：Dense 向量检索 top-30（语义匹配）+ Sparse BM25 top-30（关键词匹配）
  - Dense：擅长同义词/概括查询，弱于精确术语/版本号/API 名
  - Sparse：擅长精确关键词匹配（如 "Python 3.13 asyncio"），弱于语义变体
- 第二阶段：RRF (Reciprocal Rank Fusion) 融合双路排名（k=60），互补覆盖
- 第三阶段：Cross-Encoder Reranker 精排 top-5，最终质量把关
- 精度：经多轮人工测试（精确检索、语义区分、否定逻辑等场景），三阶段混合检索相比纯向量检索质量明显提升
"""

import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

# ── 路径 ──
CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chroma"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# ── 单例 ──
_client: Optional[chromadb.ClientAPI] = None
_embedder: Optional[chromadb.EmbeddingFunction] = None
_reranker: Optional[object] = None
_bm25_cache: dict[str, tuple[int, object, list[str]]] = {}  # name -> (count, BM25Okapi, ids)

# bge-large-zh-v1.5 的 embedding 维度
EMBEDDING_DIM = 1024

# 三阶段检索配置
RETRIEVAL_COARSE_N = 30   # 粗排：Dense + Sparse 各自召回候选数
RETRIEVAL_FINE_N = 5      # 精排：Cross-Encoder 后保留数
RRF_K = 60                # RRF 融合常数（经典值）


def _create_embedder() -> chromadb.EmbeddingFunction:
    """创建本地 embedding 函数（sentence-transformers）

    使用 BAAI/bge-large-zh-v1.5：
    - 1024 维，专为中文优化，中英文混合场景表现优异
    - 比 all-MiniLM-L6-v2（纯英文模型）在中文语义理解上有质的提升
    - 首次加载会自动从 HuggingFace 下载模型（~1.3GB），后续使用缓存
    - 如需轻量替代：BAAI/bge-base-zh-v1.5 (768维) 或 bge-small-zh-v1.5 (512维)
    """
    from chromadb.utils import embedding_functions

    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="BAAI/bge-large-zh-v1.5",
            device="cpu",
            normalize_embeddings=True,
        )
    except Exception as e:
        # bge-large 下载/加载失败时，fallback 到 base 版本
        try:
            return embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="BAAI/bge-base-zh-v1.5",
                device="cpu",
                normalize_embeddings=True,
            )
        except Exception:
            raise RuntimeError(
                f"无法加载 BGE 中文 embedding 模型: {e}\n"
                "请确认已安装: pip install sentence-transformers>=2.0.0"
            )


def get_chroma_client() -> chromadb.ClientAPI:
    """获取 ChromaDB 客户端单例"""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_embedder() -> chromadb.EmbeddingFunction:
    """获取 embedding 函数单例"""
    global _embedder
    if _embedder is None:
        _embedder = _create_embedder()
    return _embedder


def get_reranker():
    """获取 Cross-Encoder Reranker 单例（延迟加载）

    使用 BAAI/bge-reranker-v2-m3：
    - 基于 bge-m3 的 Cross-Encoder，多语言（中英）支持
    - 对 query-doc 对做联合编码，逐对打分，精度远超 bi-encoder
    - 首次加载自动从 HuggingFace 下载（~1.8GB），后续复用缓存
    - 备选轻量模型：BAAI/bge-reranker-base / bge-reranker-v2-minicpm-layerwise
    - 后端：sentence_transformers.CrossEncoder（兼容 transformers 4.x/5.x）

    加载失败时返回 None，调用方应降级为纯向量检索。
    """
    global _reranker
    if _reranker is not None:
        return _reranker

    try:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(
            "BAAI/bge-reranker-v2-m3",
            device="cpu",
            trust_remote_code=True,
        )
        print("[Reranker] BAAI/bge-reranker-v2-m3 loaded (Cross-Encoder ready)")
        return _reranker
    except Exception as e:
        print(f"[Reranker] Model load failed: {e}, falling back to pure vector retrieval")
        _reranker = None
        return None


def _sigmoid(x: float) -> float:
    """数值稳定的 sigmoid 函数

    注意：sentence_transformers v5.x 的 CrossEncoder.predict() 已内置 Sigmoid 激活，
    rerank() 不再调用此函数。保留供其他需要 logit→概率转换的场景使用。
    """
    import math
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    else:
        exp_x = math.exp(x)
        return exp_x / (1.0 + exp_x)


def rerank(
    query: str,
    documents: list[str],
    top_n: int = 5,
) -> list[tuple[int, float]]:
    """Cross-Encoder 精排：对文档列表逐对打分并重排序

    Args:
        query: 用户查询文本
        documents: 粗排召回的文档列表
        top_n: 保留的文档数

    Returns:
        [(原始索引, rerank分数), ...]，按分数降序排列，长度 ≤ top_n。
        Reranker 不可用时返回空列表（调用方应 fallback 到原始排序）。

    分数范围：sentence_transformers v5.x 的 CrossEncoder.predict()
    已内置 Sigmoid 激活，返回 [0, 1] 区间分数。
    相关文档通常 0.7-0.99，不相关 0.001-0.2。
    """
    if not documents:
        return []

    reranker = get_reranker()
    if reranker is None:
        return []  # 调用方应 fallback

    try:
        pairs = [[query, doc] for doc in documents]
        # CrossEncoder.predict() 在 v5.x 已内置 Sigmoid，直接返回 [0,1] 分数
        scores = [float(s) for s in reranker.predict(pairs, show_progress_bar=False)]

        indexed = [(i, score) for i, score in enumerate(scores)]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed[:top_n]
    except Exception as e:
        print(f"[Reranker] Rerank failed: {e}, falling back to coarse ranking")
        return []


# ═══════════════════════════════════════════════════
# BM25 关键词检索（Sparse Retriever）
# ═══════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """中文分词（jieba）+ 空白字符 tokenize，支持中英混合"""
    try:
        import jieba
        tokens = list(jieba.cut(text))
    except ImportError:
        tokens = text.split()
    # 过滤纯标点/空白 token
    return [t.strip() for t in tokens if t.strip()]


def _get_or_build_bm25(
    collection: chromadb.Collection,
    collection_name: str,
) -> tuple[object, list[str], list[str]]:
    """获取或构建 BM25 索引（按 collection count 缓存，count 变化时自动重建）

    Args:
        collection: ChromaDB collection
        collection_name: 用于缓存 key

    Returns:
        (BM25Okapi, all_ids, all_documents) — BM25 索引 + ID 列表 + 文档列表（顺序一致）
    """
    from rank_bm25 import BM25Okapi

    count = collection.count()

    # 缓存命中
    if collection_name in _bm25_cache:
        cached_count, cached_bm25, cached_ids = _bm25_cache[collection_name]
        if cached_count == count:
            return cached_bm25, cached_ids, []

    # 重建索引：获取所有文档
    try:
        all_data = collection.get()
    except Exception:
        # collection 为空或获取失败
        _bm25_cache[collection_name] = (0, None, [])
        return None, [], []

    all_ids = all_data.get("ids", [])
    all_docs = all_data.get("documents", [])

    if not all_docs or not all_ids:
        _bm25_cache[collection_name] = (0, None, [])
        return None, [], []

    # 分词 + 建 BM25 索引
    tokenized_corpus = [_tokenize(doc) for doc in all_docs]
    bm25 = BM25Okapi(tokenized_corpus)

    # 缓存
    _bm25_cache[collection_name] = (count, bm25, list(all_ids))

    return bm25, list(all_ids), list(all_docs)


def bm25_search(
    collection: chromadb.Collection,
    collection_name: str,
    query: str,
    top_k: int = 30,
) -> list[tuple[str, float]]:
    """BM25 关键词检索（Sparse）

    Args:
        collection: ChromaDB collection
        collection_name: 用于 BM25 缓存 key
        query: 查询文本
        top_k: 返回候选数

    Returns:
        [(chroma_doc_id, bm25_score), ...]，按 BM25 分数降序。
        分数为原始 BM25 分（非归一化），仅用于排序，不用于跨查询比较。
    """
    if not query.strip():
        return []

    try:
        bm25, all_ids, _ = _get_or_build_bm25(collection, collection_name)
    except Exception:
        return []

    if bm25 is None or not all_ids:
        return []

    try:
        tokenized_query = _tokenize(query)
        scores = bm25.get_scores(tokenized_query)

        # 过滤零分文档，取 top_k
        indexed = [
            (all_ids[i], float(scores[i]))
            for i in range(len(all_ids))
            if scores[i] > 0
        ]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed[:top_k]
    except Exception as e:
        print(f"[BM25] Search failed: {e}")
        return []


def _invalidate_bm25_cache(collection_name: str):
    """文档变更时使 BM25 缓存失效（供外部调用）"""
    _bm25_cache.pop(collection_name, None)


# ═══════════════════════════════════════════════════
# RRF 融合（Reciprocal Rank Fusion）
# ═══════════════════════════════════════════════════

def rrf_fusion(
    dense_ranked: list[tuple[str, float]],
    sparse_ranked: list[tuple[str, float]],
    k: int = 60,
    top_n: int = 30,
) -> list[tuple[str, float]]:
    """RRF (Reciprocal Rank Fusion)：融合 Dense 和 Sparse 检索结果

    公式：RRF_score(d) = sum_{r} 1 / (k + rank_r(d))

    Args:
        dense_ranked: Dense 检索结果 [(id, score), ...]，按分数降序（score 仅用于初始排序）
        sparse_ranked: Sparse 检索结果 [(id, score), ...]，同上
        k: RRF 常数，默认 60（经典值，降低高排名优势）
        top_n: 融合后保留的候选数

    Returns:
        [(id, rrf_score), ...]，按 RRF 分数降序排列
    """
    if not dense_ranked and not sparse_ranked:
        return []

    rrf_scores: dict[str, float] = {}

    # Dense 排名 → RRF 分
    for rank, (doc_id, _score) in enumerate(dense_ranked, start=1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    # Sparse 排名 → RRF 分
    for rank, (doc_id, _score) in enumerate(sparse_ranked, start=1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k + rank)

    # 按 RRF 分降序
    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return fused[:top_n]


def hybrid_retrieve(
    collection: chromadb.Collection,
    collection_name: str,
    query: str,
    coarse_n: int = 30,
    rrf_k: int = 60,
    rrf_top_n: int = 30,
) -> tuple[list[str], list[float], dict[str, dict]]:
    """混合检索：Dense（向量）+ Sparse（BM25）→ RRF 融合

    一步完成：向量检索 + BM25 检索 → RRF 融合 → 返回候选 ID 列表。
    调用方拿到候选 ID 后，自行从 collection 获取完整数据，
    再送入 Reranker 做精排。

    Args:
        collection: ChromaDB collection
        collection_name: 用于缓存 key
        query: 查询文本
        coarse_n: Dense/Sparse 各自召回数
        rrf_k: RRF 常数
        rrf_top_n: RRF 融合后保留的候选数

    Returns:
        (fused_ids, rrf_scores, id_to_data)
        - fused_ids: RRF 融合后的候选 ID 列表（按 RRF 分降序）
        - rrf_scores: 对应 RRF 分数
        - id_to_data: {id: {"document": ..., "metadata": {...}, "cosine_score": ...}}
          （方便调用方构建 coarse_items 时直接使用）
    """
    # 1. Dense 向量检索
    n_dense = min(coarse_n, collection.count())
    if n_dense > 0:
        dense_results = collection.query(
            query_texts=[query.strip()],
            n_results=n_dense,
        )
    else:
        dense_results = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    # 2. Sparse BM25 检索
    sparse_ranked = bm25_search(collection, collection_name, query, top_k=coarse_n)

    # 3. 构建 Dense 排名列表 + id→data 映射
    dense_ranked: list[tuple[str, float]] = []
    id_to_data: dict[str, dict] = {}

    if dense_results.get("ids") and dense_results["ids"][0]:
        for i, doc_id in enumerate(dense_results["ids"][0]):
            meta = dense_results["metadatas"][0][i] if dense_results.get("metadatas") else {}
            doc = dense_results["documents"][0][i] if dense_results.get("documents") else ""
            distance = dense_results["distances"][0][i] if dense_results.get("distances") else 0
            cosine_score = max(0.0, 1.0 - distance / 2.0)

            dense_ranked.append((doc_id, cosine_score))
            id_to_data[doc_id] = {
                "document": doc,
                "metadata": meta,
                "cosine_score": cosine_score,
            }

    # 4. RRF 融合
    fused = rrf_fusion(dense_ranked, sparse_ranked, k=rrf_k, top_n=rrf_top_n)

    # 5. 补充 BM25-only 文档的数据（Dense 没召回的）
    all_dense_ids = {did for did, _ in dense_ranked}
    bm25_only_ids = [
        did for did, _ in fused
        if did not in all_dense_ids
    ]
    if bm25_only_ids:
        try:
            bm25_data = collection.get(ids=bm25_only_ids)
            if bm25_data.get("ids"):
                for i, doc_id in enumerate(bm25_data["ids"]):
                    meta = bm25_data["metadatas"][i] if bm25_data.get("metadatas") else {}
                    doc = bm25_data["documents"][i] if bm25_data.get("documents") else ""
                    id_to_data[doc_id] = {
                        "document": doc,
                        "metadata": meta,
                        "cosine_score": 0.0,  # BM25-only，无向量分
                    }
        except Exception:
            pass

    fused_ids = [did for did, _ in fused]
    rrf_scores = [score for _, score in fused]

    return fused_ids, rrf_scores, id_to_data


# ── Collection 名称常量 ──
COLLECTION_AGENT_MEMORY = "agent_memory"
COLLECTION_KNOWLEDGE_BASE = "knowledge_base"
COLLECTION_CHAT_HISTORY = "chat_history"


def get_memory_collection() -> chromadb.Collection:
    """获取 Agent 记忆 collection（懒初始化）"""
    client = get_chroma_client()
    embedder = get_embedder()
    return client.get_or_create_collection(
        name=COLLECTION_AGENT_MEMORY,
        embedding_function=embedder,
        metadata={"description": "Agent episodic & semantic memory"},
    )


def get_knowledge_collection() -> chromadb.Collection:
    """获取知识库 collection（懒初始化）"""
    client = get_chroma_client()
    embedder = get_embedder()
    return client.get_or_create_collection(
        name=COLLECTION_KNOWLEDGE_BASE,
        embedding_function=embedder,
        metadata={"description": "User-uploaded knowledge base documents"},
    )


def get_chat_history_collection() -> chromadb.Collection:
    """获取对话历史 collection（懒初始化）— 自动存档每轮对话"""
    client = get_chroma_client()
    embedder = get_embedder()
    return client.get_or_create_collection(
        name=COLLECTION_CHAT_HISTORY,
        embedding_function=embedder,
        metadata={"description": "Auto-saved chat conversation turns for recall"},
    )


def ensure_collections():
    """应用启动时初始化所有 collection（幂等）"""
    get_memory_collection()
    get_knowledge_collection()
    get_chat_history_collection()
    print(f"[ChromaDB] 初始化完成，持久化目录：{CHROMA_DIR}")
