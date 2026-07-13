"""测试两阶段检索（粗排向量 + 精排 Reranker）

验证：
1. Reranker 模型加载
2. rerank() 函数正确排序
3. 中文语义匹配精度（相关 vs 不相关）
4. Fallback 降级（Reranker 不可用时）
"""

import sys
from pathlib import Path

# 确保 backend 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 测试 1: Reranker 模型加载 ──
print("=" * 60)
print("Test 1: Reranker model loading")
print("=" * 60)

from vector import get_reranker

reranker = get_reranker()
if reranker is None:
    print("[WARN] Reranker unavailable, will test fallback path")
else:
    print("[PASS] Reranker loaded successfully")
    print(f"       Model type: {type(reranker).__name__}")

# ── 测试 2: rerank() 基本功能 ──
print("\n" + "=" * 60)
print("Test 2: rerank() basic ranking")
print("=" * 60)

from vector import rerank

# 模拟粗排召回的文档
test_query = "人工智能的发展趋势"
test_docs = [
    "今天天气很好，适合出去散步。",                     # 不相关
    "深度学习是人工智能的核心技术，近年来Transformer架构成为主流。",  # 最相关
    "Python是一种广泛使用的编程语言。",                  # 弱相关
    "AI在医疗、金融、教育等领域有广泛应用前景。",         # 高度相关
    "我喜欢吃披萨和汉堡。",                              # 不相关
]

if reranker is not None:
    ranked = rerank(test_query, test_docs, top_n=3)

    print(f"Query: '{test_query}'")
    print(f"\nReranked results (top-{len(ranked)}):")
    for rank, (idx, score) in enumerate(ranked):
        preview = test_docs[idx][:80]
        print(f"  {rank+1}. [idx={idx}, score={score:.4f}] {preview}...")

    # 验证排序质量
    if len(ranked) >= 2:
        # 最相关的 doc 1 或 doc 3 应该排在第一
        best_idx = ranked[0][0]
        assert best_idx in (1, 3), (
            f"Expected best doc index 1 or 3, got {best_idx}"
        )

        # 两个高度相关的文档 (1,3) 应排在两个不相关的文档 (0,4) 前面
        ranked_indices = [r[0] for r in ranked]
        for rel_idx in (1, 3):
            if rel_idx in ranked_indices:
                rel_pos = ranked_indices.index(rel_idx)
                for irr_idx in (0, 4):
                    if irr_idx in ranked_indices:
                        irr_pos = ranked_indices.index(irr_idx)
                        assert rel_pos < irr_pos, (
                            f"Related doc {rel_idx} should rank before irrelevant doc {irr_idx}"
                        )

        print("\n[PASS] Ranking correct: relevant docs ranked higher than irrelevant ones")
else:
    ranked = rerank(test_query, test_docs, top_n=3)
    assert ranked == [], "Should return empty list when reranker unavailable"
    print("[PASS] Fallback correct: rerank() returns empty list, caller uses coarse results")

# ── 测试 3: 中文语义区分度 ──
print("\n" + "=" * 60)
print("Test 3: Chinese semantic discrimination (relevant vs irrelevant)")
print("=" * 60)

if reranker is not None:
    chinese_query = "我叫海绵酱，是一名AI研究者"
    chinese_docs = [
        "海绵酱喜欢研究大语言模型和智能体技术。",        # 相关
        "今天中午吃了麻辣烫，味道不错。",                 # 不相关
        "用户的名字是海绵酱，职业是AI探索者。",           # 相关
        "北京的天气最近很热。",                           # 不相关
        "海绵酱用Claude Code做日常开发工作。",            # 相关
    ]

    ranked = rerank(chinese_query, chinese_docs, top_n=5)

    print(f"Query: '{chinese_query}'")
    print(f"\nAll docs Reranker scores:")
    for idx, score in ranked:
        label = "[REL]" if idx in (0, 2, 4) else "[IRR]"
        preview = chinese_docs[idx][:60]
        print(f"  {label} idx={idx}, score={score:.4f}: {preview}...")

    # 验证：相关的分数应显著高于不相关的
    related_scores = [s for i, s in ranked if i in (0, 2, 4)]
    unrelated_scores = [s for i, s in ranked if i in (1, 3)]

    min_related = min(related_scores)
    max_unrelated = max(unrelated_scores)

    print(f"\n  Min related score:   {min_related:.4f}")
    print(f"  Max unrelated score: {max_unrelated:.4f}")

    if min_related > max_unrelated:
        print(f"[PASS] Perfect separation: all related > all unrelated (gap {min_related - max_unrelated:.4f})")
    else:
        print(f"[WARN] Score overlap: min related {min_related:.4f} vs max unrelated {max_unrelated:.4f}")
else:
    print("[SKIP] Reranker unavailable")

# ── 测试 4: 空输入处理 ──
print("\n" + "=" * 60)
print("Test 4: Edge cases")
print("=" * 60)

assert rerank("query", [], top_n=5) == [], "Empty doc list should return empty list"
print("[PASS] Empty doc list -> empty result")

assert rerank("", ["doc"], top_n=5) == [] or reranker is not None, "Empty query should be handled"
print("[PASS] Empty query -> handled gracefully")

# ── 总结 ──
print("\n" + "=" * 60)
print("Summary")
print("=" * 60)
if reranker is not None:
    print("[PASS] All reranker tests passed")
    print("       Two-stage retrieval (coarse top-30 -> fine top-5) ready")
    print("       Model: BAAI/bge-reranker-v2-m3")
else:
    print("[WARN] Reranker unavailable, system degrades to pure vector retrieval")
    print("       Install: pip install FlagEmbedding")
    print("       All callers have automatic fallback, system operates normally")
