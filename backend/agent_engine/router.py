"""复杂度预检 — 0 token 消耗的规则判断，在进入 Agent Loop 前给出初始 bias

三层防御中的第三层（最外层），用关键词和规则做快速判断，
结果注入 System Prompt 作为 LLM 的初始倾向提示。
"""

from typing import Literal

BiasType = Literal["simple", "medium", "complex", "auto"]


def quick_classify(task: str) -> dict:
    """零 token 消耗的复杂度预检。

    基于规则和关键词快速判断任务复杂度，给 System Prompt 提供初始 bias。

    Args:
        task: 用户输入的任务文本

    Returns:
        {"bias": "simple"|"medium"|"complex"|"auto", "reason": str}
    """
    task_lower = task.lower().strip()

    # ── 信号一：任务长度 ──
    short_task = len(task) < 30

    # ── 信号二：简单关键词 → 快速回答即可 ──
    simple_keywords = [
        "是什么", "什么是", "什么意思", "怎么样", "如何", "怎么",
        "翻译", "解释", "定义", "区别", "对比",
        "推荐", "为什么", "能不能", "可不可以",
        "有没有", "好不好", "对不对", "怎么样",
    ]
    has_simple_kw = any(kw in task for kw in simple_keywords)

    # ── 信号三：复杂关键词 → 需要深入研究 ──
    complex_keywords = [
        "分析", "研究", "报告", "趋势", "市场",
        "调查", "深度", "详细", "全面", "对比分析",
        "预测", "评估", "调研", "行业", "格局",
        "战略", "方案", "规划", "展望",
    ]
    has_complex_kw = any(kw in task for kw in complex_keywords)

    # ── 信号四：是否需要实时信息 ──
    realtime_keywords = [
        "最新", "今天", "现在", "当前", "最近",
        "2025", "2026", "今年", "本月", "实时",
        "新闻", "刚刚", "近期", "当下",
    ]
    needs_realtime = any(kw in task for kw in realtime_keywords)

    # ── 信号五：闲聊/问候 ──
    chat_keywords = [
        "你好", "嗨", "哈喽", "谢谢", "再见",
        "天气", "心情", "无聊", "好玩",
    ]
    is_chat = any(kw in task for kw in chat_keywords) and not has_complex_kw

    # ── 决策矩阵 ──

    # 闲聊 → 直接答
    if is_chat and short_task:
        return {"bias": "simple", "reason": "闲聊/问候，直接回答"}

    # 短问题 + 简单关键词 + 无复杂信号 → 简单
    if short_task and has_simple_kw and not has_complex_kw and not needs_realtime:
        return {"bias": "simple", "reason": "短问题 + 简单关键词，无需工具"}

    # 有复杂关键词 → 复杂
    if has_complex_kw:
        return {"bias": "complex", "reason": "检测到复杂分析关键词"}

    # 需要实时信息但无复杂分析 → 中等
    if needs_realtime and not has_complex_kw:
        return {"bias": "medium", "reason": "需要实时信息，但不需要深度分析"}

    # 长问题但无法判定
    if not short_task and not has_simple_kw:
        return {"bias": "auto", "reason": "较长问题，倾向复杂但由 LLM 决定"}

    # 兜底
    return {"bias": "auto", "reason": "无法预判，由 LLM 自主决定"}
