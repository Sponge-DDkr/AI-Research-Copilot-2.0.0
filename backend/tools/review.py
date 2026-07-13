"""review_section + fact_check 工具 — Agent 质量自审

Day 8 新增：
- review_section：对已撰写章节进行质量评审（语法、一致性、完整性、可读性）
- fact_check：交叉验证章节中的事实声明与搜索结果的匹配度
"""

from typing import Any

from tools.registry import registry

# ── review_section ──

REVIEWER_SYSTEM_PROMPT = """你是一个严格的内容审核编辑。你的任务是评审一段文字的质量。

## 评审维度

1. **准确性**：内容是否与上下文/指令一致？有没有明显的事实错误？
2. **完整性**：是否覆盖了该主题的必要要点？有没有遗漏重要内容？
3. **可读性**：语言是否流畅？结构是否清晰？标题层级是否合理？
4. **格式规范**：Markdown 格式是否正确？链接是否有效？

## 输出格式

请严格按照以下格式输出：

### 📋 评审结果

**总体评分**：X/10

**优点**：
- （列出做得好的地方）

**问题**：
- （列出需要改进的地方，每条标注严重程度：🔴严重 🟡中等 🟢轻微）

**修改建议**：
- （具体可操作的修改方案）

## 注意事项
- 不要为了批评而批评，只有确实有问题才指出
- 修改建议要具体，不要说"写得更好一些"这种废话
- 用简体中文输出
- 如果内容质量很高（8/10 以上），简化输出，不要凑字数"""


@registry.register(
    name="review_section",
    description=(
        "对已撰写的章节进行质量评审。检查准确性、完整性、可读性和格式规范。"
        "适用于：写完一个章节后自我检查、最终报告定稿前的质量把关。"
        "返回评分（1-10）和具体修改建议。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "要评审的章节标题",
            },
            "content": {
                "type": "string",
                "description": "要评审的章节内容（完整文本）",
            },
            "context": {
                "type": "string",
                "description": "该章节的上下文/写作要求，用于判断内容是否偏离主题。可选。",
            },
        },
        "required": ["title", "content"],
    },
)
async def review_section(
    state: Any,
    llm: Any,
    title: str = "",
    content: str = "",
    context: str = "",
) -> str:
    """对章节内容进行质量评审"""
    if not content.strip():
        return "❌ 评审内容不能为空"

    # 截断过长内容
    max_len = 6000
    if len(content) > max_len:
        content = content[:max_len] + "\n\n…（内容过长，仅评审前 6000 字符）"

    user_prompt = f"""## 评审任务

**章节标题**：{title}

**写作要求/上下文**：{context if context else '（未提供）'}

**待评审内容**：

{content}"""

    try:
        response = await llm.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,  # 评审用低温度，保持一致性
            max_tokens=1200,
        )
        result = response.choices[0].message.content or ""
    except Exception as e:
        return f"❌ 评审调用失败：{str(e)}"

    return result


# ── fact_check ──

FACT_CHECKER_SYSTEM_PROMPT = """你是一个严格的事实核查员。你的任务是将文本中的事实声明与参考来源进行交叉验证。

## 核查流程

1. **提取声明**：从待核查文本中提取所有可验证的事实声明
2. **逐条对比**：将每条声明与参考数据逐一对比
3. **标注可信度**：
   - ✅ 正确：参考数据直接支持该声明
   - ⚠️ 部分正确：参考数据部分支持，但有出入
   - ❓ 无法验证：参考数据中没有相关信息
   - ❌ 错误：参考数据与该声明矛盾
4. **给出修正**：对有问题的地方给出修正文本

## 输出格式

### 🔍 事实核查报告

| # | 声明摘要 | 可信度 | 说明 |
|---|---------|--------|------|
| 1 | （声明内容摘要） | ✅/⚠️/❓/❌ | （与参考数据的对比说明） |

**需要修正的内容**：
- （具体修正建议，附修正后的文本）

## 注意事项
- 只核查可验证的事实声明（数据、事件、人名、时间等），不核查观点/主观判断
- 如果参考数据不足以验证，如实标注"无法验证"
- 用简体中文输出"""


@registry.register(
    name="fact_check",
    description=(
        "对章节内容中涉及的事实声明进行交叉验证。将声明与搜索结果或其他参考数据逐一对比，"
        "标注可信度（✅正确/⚠️部分正确/❓无法验证/❌错误），给出修正建议。"
        "适用于：搜索后写完章节需要确保数据准确、最终报告发布前的质量把关。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "要核查的章节标题",
            },
            "content": {
                "type": "string",
                "description": "要核查的章节内容",
            },
            "reference_data": {
                "type": "string",
                "description": "用于验证的参考数据。通常是 web_search 返回的搜索结果。如果未提供，系统会尝试从之前的搜索结果中获取。",
            },
        },
        "required": ["title", "content"],
    },
)
async def fact_check(
    state: Any,
    llm: Any,
    title: str = "",
    content: str = "",
    reference_data: str = "",
) -> str:
    """对章节内容进行事实核查"""
    if not content.strip():
        return "❌ 核查内容不能为空"

    # 如果没有提供参考数据，尝试从 state 中获取
    if not reference_data.strip():
        search_results = state.tool_results.get("web_search", {})
        if search_results:
            ref_parts = []
            results = search_results.get("results", [])
            answer = search_results.get("answer", "")
            if answer:
                ref_parts.append(f"AI 摘要：{answer}")
            for r in results[:5]:
                ref_parts.append(
                    f"- {r.get('title', '')}: {r.get('content', '')[:300]}"
                )
            reference_data = "\n".join(ref_parts)

    if not reference_data.strip():
        return (
            "⚠️ 未提供参考数据，无法进行事实核查。\n\n"
            "建议：先用 web_search 搜索相关信息，再将搜索结果作为 reference_data 传入。\n"
            "也可以直接调用 fact_check，系统会尝试使用之前搜索的结果。"
        )

    # 截断
    max_content = 5000
    max_ref = 6000
    if len(content) > max_content:
        content = content[:max_content] + "\n\n…（内容过长，已截断）"
    if len(reference_data) > max_ref:
        reference_data = reference_data[:max_ref] + "\n\n…（参考数据过长，已截断）"

    user_prompt = f"""## 事实核查任务

**章节标题**：{title}

**待核查内容**：

{content}

**参考数据（搜索获得的权威信息）**：

{reference_data}"""

    try:
        response = await llm.chat.completions.create(
            model=llm.model,
            messages=[
                {"role": "system", "content": FACT_CHECKER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,  # 事实核查用极低温度
            max_tokens=1500,
        )
        result = response.choices[0].message.content or ""
    except Exception as e:
        return f"❌ 核查调用失败：{str(e)}"

    return result
