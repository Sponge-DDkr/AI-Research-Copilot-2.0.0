"""Chat API — 聊天对话接口

记忆策略（四层）：
1. 对话历史自动存档：每轮对话自动存入 chat_history collection，无需 LLM 主动 save_memory
2. 自动预检索：每条用户消息到达时，两阶段检索对话历史（优先）和 agent_memory
   - 粗排：向量检索 top-30（bi-encoder，速度快）
   - 精排：Cross-Encoder Reranker 重排序 top-5（精度高）
3. LLM 手动检索：recall_memory 工具仍可用，满足深度检索需求
4. LLM 主动保存：save_memory 工具用于保存用户明确要求记住的信息
"""

import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from config import get_config

# 导入工具以触发注册
import tools.search  # noqa: F401
import tools.memory  # noqa: F401
import tools.knowledge  # noqa: F401
from tools.registry import registry

router = APIRouter(tags=["chat"])

# 北京时间
CST = timezone(timedelta(hours=8))

# 语义召回最低分数阈值（Reranker 归一化分数 或 Cosine 相似度，均为 [0,1] 范围）
# Reranker 精排后：相关文档 0.50-0.99，不相关 <0.20
# 无 Reranker 降级时：BGE-large-zh cosine 相关对 0.40-0.66，无关对 <0.30
MEMORY_SCORE_THRESHOLD = 0.40


def _fetch_relevant_context(user_message: str, n: int = 5) -> str:
    """用用户消息做语义召回，两阶段检索对话历史（优先）+ agent_memory

    检索链路：
    1. 粗排：BGE-large-zh 向量检索 top-30（bi-encoder）
    2. 精排：BGE Reranker Cross-Encoder 重排序 top-n（精度显著高于纯向量检索）
    3. 阈值过滤：Reranker 分数 ≥ 0.40 的结果才注入 System Prompt

    对话历史优先：之前的聊天记录匹配度最高，应排在前面。
    agent_memory 是 LLM 显式保存的记忆，作为补充。
    Reranker 不可用时自动降级为纯向量检索 + cosine 分数阈值。
    """
    try:
        from agent_engine.memory import recall_memories, recall_chat_history

        lines: list[str] = []

        # 1. 对话历史（优先）
        chat_turns = recall_chat_history(user_message, n_results=n)
        relevant_chat = [t for t in chat_turns if t["score"] >= MEMORY_SCORE_THRESHOLD]
        if relevant_chat:
            lines.append("## 历史对话（自动检索，优先参考）\n")
            for i, turn in enumerate(relevant_chat, 1):
                ts = turn.get("timestamp", "")
                lines.append(f"### {i}. 对话记录（{ts}，匹配度: {turn['score']:.0%}）")
                lines.append(f"**用户说**：{turn['user_message'][:300]}")
                lines.append(f"**助手回**：{turn['assistant_reply'][:300]}")
                lines.append("")

        # 2. Agent 记忆（补充）
        memories = recall_memories(user_message, n_results=n)
        relevant_mem = [m for m in memories if m["score"] >= MEMORY_SCORE_THRESHOLD]
        if relevant_mem:
            lines.append("## 持久记忆（补充参考）\n")
            for i, mem in enumerate(relevant_mem, 1):
                lines.append(f"### {i}. {mem['name']}（匹配度: {mem['score']:.0%}）")
                lines.append(f"{mem['content'][:400]}")
                lines.append("")

        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


def _build_chat_system_prompt(user_message: str) -> str:
    """构建 System Prompt — 含自动检索的对话历史（优先）+ 持久记忆"""
    today = datetime.now(CST).strftime("%Y年%m月%d日")

    # 自动检索：对话历史优先 + 持久记忆补充
    context_section = _fetch_relevant_context(user_message)
    context_block = ""
    if context_section:
        context_block = (
            "\n\n---\n\n"
            + context_section
            + "\n**提示**：上述是系统自动检索到的相关上下文。"
            "「历史对话」是该用户之前的聊天记录（优先参考），"
            "「持久记忆」是之前显式保存的重要信息。"
            "如果用户问到了相关话题，可以自然引用。\n"
        )

    return (
        f"你是一个专业的研究助手。当前日期是 {today}（北京时间）。\n\n"
        "回复规则：\n"
        "- 回答简洁、准确、有帮助\n"
        "- 常识/知识类问题直接基于训练数据回答\n"
        "- 日期/时间类问题以系统提供的当前日期为准\n"
        "- 需要实时信息时（天气、新闻、股价等），使用 web_search 工具搜索后回答\n"
        "- 当用户使用「刚才」「刚刚」「上一次」「今天」等时间限定词询问对话历史时，优先参考时间戳最新的上下文；系统自动检索到的「历史对话」中若时间戳超过 24 小时，不要将其当作用户最近的问题来回答\n"
        "- **必须使用简体中文输出，禁止使用繁体中文**\n"
        "- 用户提到「我的文档」「知识库」「上传的资料」时，使用 search_knowledge_base 检索\n"
        "- **重要**：对话中发现用户个人信息（名字、偏好、习惯、职业等）时，必须主动调用 save_memory 保存\n"
        "- **重要**：如果用户要求生成分析报告、市场研究、技术调研等需要结构化的深度内容，请引导用户使用「深度研究」模式（页面顶部切换），而非在当前聊天中尝试输出长报告。聊天模式适合快速问答和信息检索，不适合生成需要分章节、引用来源、事实核查的结构化报告\n\n"
        "记忆使用原则：\n"
        "- 如果 System Prompt 中已包含「历史对话」或「持久记忆」区块，说明系统已自动检索到相关上下文，可直接引用\n"
        "- 如果需要更精确或更全面的检索，使用 recall_memory 工具\n"
        "- 仅在上下文确实存在且相关时才引用，不要编造内容"
        + context_block
    )


class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息", min_length=1, max_length=5000)


class ChatResponse(BaseModel):
    reply: str = Field(..., description="AI 回复")
    model: str = Field(..., description="使用的模型")


def _get_llm_client() -> AsyncOpenAI:
    """创建 DeepSeek API 客户端（兼容 OpenAI SDK）"""
    config = get_config()
    if not config.deepseek_api_key:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 .env 文件中设置",
        )
    return AsyncOpenAI(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    聊天对话接口。

    支持工具调用：web_search、recall_memory、save_memory、search_knowledge_base。
    每轮对话自动存档到 chat_history，无需手动 save_memory。
    深度研究请使用 /api/research/stream 端点。
    """
    try:
        response = await _do_chat(request)
        # 自动存档本轮对话（不阻塞响应）
        try:
            from agent_engine.memory import save_chat_turn
            save_chat_turn(request.message, response.reply)
        except Exception:
            pass
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat 处理异常: {str(e)}")


async def _do_chat(request: ChatRequest) -> ChatResponse:
    """聊天核心逻辑"""
    config = get_config()
    client = _get_llm_client()

    # 聊天模式可用工具：搜索 + 记忆 + 知识库
    chat_tool_names = {"web_search", "recall_memory", "save_memory", "search_knowledge_base"}
    chat_tools = [
        s for s in registry.get_all_schemas()
        if s["function"]["name"] in chat_tool_names
    ]

    messages = [
        {"role": "system", "content": _build_chat_system_prompt(request.message)},
        {"role": "user", "content": request.message},
    ]

    try:
        # 第一轮：LLM 可调用工具
        response = await client.chat.completions.create(
            model=config.deepseek_model,
            messages=messages,
            tools=chat_tools or None,
            temperature=0.7,
            max_tokens=1000,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM API 调用失败: {str(e)}")

    choice = response.choices[0]
    msg = choice.message

    # 如果 LLM 调用工具 → 执行 → 第二轮生成最终回答
    if msg.tool_calls:
        # 创建最小化的 dummy state（所有工具共享）
        class DummyState:
            tool_results: dict = {}
            plan: list = []
        dummy_state = DummyState()

        # 构建 assistant 消息（含所有 tool_calls）
        tool_call_blocks = []
        for tc in msg.tool_calls:
            tool_call_blocks.append({
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            })

        # 按照 OpenAI 格式：system → user → assistant(tool_calls) → tool → tool → ...
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_call_blocks,
        })

        # 执行每个工具并追加 tool 消息
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            try:
                tool_result = await registry.execute(
                    tool_name=tc.function.name, state=dummy_state, llm=client, **args
                )
            except Exception as e:
                tool_result = f"[Error] 工具 {tc.function.name} 执行失败: {str(e)}"
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(tool_result),
            })

        # 第二轮：基于工具结果生成最终回答
        try:
            response2 = await client.chat.completions.create(
                model=config.deepseek_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
            )
            msg = response2.choices[0].message
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LLM API 第二轮调用失败: {str(e)}")

    return ChatResponse(
        reply=msg.content or "（Agent 未生成回复，请重试）",
        model=config.deepseek_model,
    )


@router.get("/chat/health")
async def health_check():
    """健康检查 — 验证 DeepSeek API Key 是否有效"""
    config = get_config()
    if not config.deepseek_api_key:
        return {"status": "no_api_key", "message": "DEEPSEEK_API_KEY 未配置"}

    try:
        client = _get_llm_client()
        # 发一个最小的请求验证 key 有效
        response = await client.chat.completions.create(
            model=config.deepseek_model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        return {
            "status": "ok",
            "model": config.deepseek_model,
            "base_url": config.deepseek_base_url,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
