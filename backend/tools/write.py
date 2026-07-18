"""写作工具 — write_section / format_markdown"""

from tools.registry import registry

# DeepSeek 写作专用 system prompt
WRITER_SYSTEM_PROMPT = """你是一个专业的内容写手。根据指定的主题和写作要求，生成高质量的内容。

要求：
- 内容准确、条理清晰
- 使用 Markdown 格式，包含适当的小标题、列表等
- 语言流畅自然，中文输出
- 只输出正文内容，不要加"好的""以下是"等引语"""


@registry.register(
    name="write_section",
    description=(
        "撰写报告的一个章节/段落。每次调用写一个章节。"
        "调用前请心里想清楚本章节的标题和要涵盖的内容点。"
        "写完所有章节后，在最后一条消息中将它们拼接为完整报告。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "章节标题，如「人工智能的定义」",
            },
            "description": {
                "type": "string",
                "description": "本章节要写什么内容，越具体越好。如「介绍AI的基本概念，包括定义、发展简史和主要分支」",
            },
        },
        "required": ["title", "description"],
    },
)
async def write_section(state, llm, title: str, description: str) -> str:
    """撰写报告章节 — 调用 LLM 生成内容"""
    try:
        response = await llm.chat.completions.create(
            model=llm.model,  # 使用配置的模型
            messages=[
                {"role": "system", "content": WRITER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"请撰写以下章节：\n\n标题：{title}\n要求：{description}",
                },
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        content = response.choices[0].message.content or ""
    except Exception as e:
        return f"[Error] 写作失败: {str(e)}"

    # 把产出存到对应的 plan step（按优先级匹配）
    # 1. 正在进行的步骤
    in_progress = [s for s in state.plan if s.status == "in_progress"]
    if in_progress:
        in_progress[0].content = content
    else:
        # 2. 第一个待开始的步骤
        pending = state.get_pending_steps()
        if pending:
            pending[0].content = content
        else:
            # 3. 兜底：所有步骤都 done 了 → 找标题最匹配的步骤覆盖
            best = None
            for s in state.plan:
                if title in s.description or s.description in title:
                    best = s
                    break
            if best is None and state.plan:
                # 没匹配到，找第一个 done 步骤（通常是同一轮重复写）
                done_steps = [s for s in state.plan if s.status == "done"]
                best = done_steps[-1] if done_steps else state.plan[-1]
            if best:
                best.content = content

    return f"## {title}\n\n{content}"
