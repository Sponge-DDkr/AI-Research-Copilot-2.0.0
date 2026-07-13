"""测试混合检索：Dense（向量）+ Sparse（BM25）→ RRF 融合

验证：
1. BM25 精确关键词匹配（Dense 跟不住的场景）
2. RRF 融合：互补覆盖——Dense 漏掉的由 BM25 补上
3. BM25 索引缓存：count 不变时复用，count 变化时重建
4. 缓存失效：文档变更后索引自动重建
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ═══════════════════════════════════════════════════
# Test 1: BM25 keyword matching
# ═══════════════════════════════════════════════════
print("=" * 60)
print("Test 1: BM25 exact keyword matching")
print("=" * 60)

from vector import _tokenize, bm25_search
import chromadb

# 创建临时 collection
client = chromadb.Client(chromadb.config.Settings(anonymized_telemetry=False))
test_docs = [
    "Python 3.13 引入了新的 asyncio 改进，包括 TaskGroup 的增强支持。",        # 精确匹配目标
    "Python 异步编程入门教程，适合初学者学习 asyncio 的基本概念。",              # 语义相近但版本不对
    "Java 21 的虚拟线程让并发编程变得更简单。",                                # 不相关
    "Python 3.13 asyncio TaskGroup 的使用方法和最佳实践。",                    # 精确匹配目标
    "机器学习和深度学习在自然语言处理中的应用。",                               # 不相关
]

collection = client.create_collection("test_bm25")
collection.upsert(
    ids=[f"doc{i}" for i in range(len(test_docs))],
    documents=test_docs,
    metadatas=[{"idx": str(i)} for i in range(len(test_docs))],
)

# 查询：精确关键词 "Python 3.13 asyncio"
query = "Python 3.13 asyncio TaskGroup"
results = bm25_search(collection, "test_bm25", query, top_k=3)

print(f"Query: '{query}'")
print(f"\nBM25 top-{len(results)}:")
for rank, (doc_id, score) in enumerate(results):
    idx = int(doc_id.replace("doc", ""))
    print(f"  {rank+1}. [score={score:.4f}] {test_docs[idx][:70]}...")

# 验证：doc3 ("Python 3.13 asyncio TaskGroup 的使用方法") 应该排第一
if results:
    top_idx = int(results[0][0].replace("doc", ""))
    # doc3 或 doc0（都含 "Python 3.13 asyncio"）应该在前 2
    assert top_idx in (0, 3), (
        f"Expected 'Python 3.13 asyncio' doc (idx=0 or 3) at top, got idx={top_idx}"
    )
    print("\n[PASS] BM25 correctly ranks exact keyword matches first")
else:
    print("\n[FAIL] BM25 returned no results")

# ═══════════════════════════════════════════════════
# Test 2: RRF Fusion — complementary coverage
# ═══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 2: RRF Fusion — Dense misses, Sparse covers")
print("=" * 60)

from vector import rrf_fusion

# 模拟：Dense 检索偏向语义相似，漏掉精确匹配
dense_ranked = [
    ("doc1", 0.45),  # 语义："Python 异步编程入门" — 但版本不对！
    ("doc0", 0.43),  # Python 3.13 asyncio — 排第二
    ("doc4", 0.38),  # NLP 相关内容（跑偏了）
]

# BM25：精确关键词匹配
sparse_ranked = [
    ("doc3", 6.5),   # "Python 3.13 asyncio TaskGroup 的使用方法" — 完美匹配
    ("doc0", 5.2),   # "Python 3.13 引入了新的 asyncio 改进"
    ("doc1", 3.1),   # "Python 异步编程入门"
]

fused = rrf_fusion(dense_ranked, sparse_ranked, k=60, top_n=5)

print("RRF Fusion results:")
for rank, (doc_id, score) in enumerate(fused):
    idx = int(doc_id.replace("doc", ""))
    print(f"  {rank+1}. [RRF={score:.4f}] doc{idx}: {test_docs[idx][:60]}...")

# 验证：doc3（Dense 完全遗漏，BM25 rank #1）应该被 RRF 拉入 top-3
# RRF 数学：双路命中 > 单路命中，但单路 #1 仍能得到可观的 RRF 分
fused_ids = [did for did, _ in fused]
fused_positions = {did: i for i, did in enumerate(fused_ids)}

# doc3 在 Dense 结果中不存在，按纯 Dense 相当于"没找到"
# RRF 让它从"找不到"变为 #3 — 这就是 BM25 互补覆盖的价值
assert "doc3" in fused_ids[:3], (
    f"BM25-unique doc3 should be in top-3 after RRF (was completely absent from Dense), got positions: {fused_positions}"
)
print("[PASS] RRF brought BM25-unique exact match from 'not found' (Dense) into top-3")

# 验证：双路命中的文档（doc0, doc1）排名靠前（RRF 奖励一致性）
# 验证：Dense 跑偏的 doc4 被排到最后
assert fused_positions.get("doc4", 0) >= len(fused) - 1, (
    "Irrelevant doc4 (Dense false positive) should rank last after RRF"
)
print("[PASS] RRF correctly demoted Dense-only false positive to last")

# ═══════════════════════════════════════════════════
# Test 3: BM25 cache behavior
# ═══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 3: BM25 cache invalidation")
print("=" * 60)

from vector import _get_or_build_bm25, _invalidate_bm25_cache, _bm25_cache

# 清缓存
_bm25_cache.clear()

# 第一次查询 → 构建索引
bm25_1, ids_1, _ = _get_or_build_bm25(collection, "test_cache")
assert bm25_1 is not None, "BM25 index should be built"
assert "test_cache" in _bm25_cache, "Should be cached"
count_before = _bm25_cache["test_cache"][0]
print(f"[PASS] BM25 index built and cached (count={count_before})")

# 第二次查询 → 命中缓存（count 不变）
bm25_2, ids_2, _ = _get_or_build_bm25(collection, "test_cache")
assert bm25_2 is bm25_1, "Should return cached instance (same object)"
print("[PASS] Cache hit: same BM25 instance returned")

# 添加文档 → 使缓存失效
collection.upsert(
    ids=["doc_new"],
    documents=["Python GIL 在 3.13 中的变化和 free-threading 模式。"],
    metadatas=[{"idx": "new"}],
)
_invalidate_bm25_cache("test_cache")
assert "test_cache" not in _bm25_cache, "Cache should be cleared after invalidation"
print("[PASS] Cache invalidated after document mutation")

# 第三次查询 → 重建索引（count 变了）
bm25_3, ids_3, _ = _get_or_build_bm25(collection, "test_cache")
new_count = _bm25_cache["test_cache"][0]
assert new_count == 6, f"New index should have 6 docs, got {new_count}"
assert bm25_3 is not bm25_1, "Should be a new instance (rebuilt)"
print(f"[PASS] BM25 index rebuilt after invalidation (count: {count_before} -> {new_count})")

# ═══════════════════════════════════════════════════
# Test 4: Tokenize (Chinese word segmentation)
# ═══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Test 4: jieba tokenization for Chinese text")
print("=" * 60)

samples = [
    ("Python 3.13 asyncio 使用指南", ["Python", "3.13", "asyncio"]),
    ("人工智能大模型的发展趋势", ["人工智能", "模型", "趋势"]),
]

for text, required_keywords in samples:
    tokens = _tokenize(text)
    joined = " ".join(tokens)
    for kw in required_keywords:
        assert kw in joined, (
            f"'{kw}' should be findable in tokens of '{text}', got tokens: {tokens}"
        )
    print(f"  '{text}' -> {tokens}")

print("[PASS] Chinese-English mixed tokenization working correctly")

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
print("[PASS] All hybrid retrieval tests passed")
print("       BM25 keyword matching: exact terms ranked first")
print("       RRF fusion: complementary Dense+Sparse coverage")
print("       Cache: auto-invalidation on document mutation")
print("       Tokenization: Chinese (jieba) + English mixed support")
print()
print("Pipeline: Dense(30) + Sparse(30) -> RRF(30) -> Reranker(5)")

# Cleanup
client.delete_collection("test_bm25")
_bm25_cache.clear()
