"""web_search 工具 — 通过 Tavily Search API 进行网络搜索"""

import json
from typing import Any

import httpx

from tools.registry import registry

TAVILY_API_URL = "https://api.tavily.com/search"

# 工具调用超时（秒）
SEARCH_TIMEOUT = 25.0


@registry.register(
    name="web_search",
    description="搜索互联网获取最新信息。适用于：查找最新新闻、事实核查、获取实时数据、查找资料。返回匹配的搜索结果列表（标题、URL、摘要）。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询词，支持中文或英文。建议使用简洁的关键词组合以获得最佳结果。",
            },
            "max_results": {
                "type": "integer",
                "description": "返回的最大结果数，默认 5，最大 10",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def web_search(
    state: Any,
    llm: Any,
    query: str = "",
    max_results: int = 5,
) -> str:
    """调用 Tavily Search API 执行网络搜索"""

    # 获取 API Key
    from config import get_config

    config = get_config()
    api_key = config.tavily_api_key

    if not api_key:
        return (
            "❌ 搜索功能未配置：缺少 TAVILY_API_KEY。\n"
            "请在 .env 文件中设置 TAVILY_API_KEY=你的key，然后重启服务。\n"
            "获取免费 API Key：https://tavily.com"
        )

    if not query.strip():
        return "❌ 搜索查询词不能为空。请提供一个具体的搜索关键词。"

    max_results = max(1, min(max_results, 10))

    try:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            response = await client.post(
                TAVILY_API_URL,
                json={
                    "api_key": api_key,
                    "query": query.strip(),
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": True,
                },
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        return f"❌ 搜索超时（{SEARCH_TIMEOUT}秒），请稍后重试或缩小搜索范围。"
    except httpx.HTTPStatusError as e:
        return f"❌ 搜索 API 返回错误：HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"❌ 搜索请求失败：{str(e)}"

    # 解析结果
    results = data.get("results", [])
    answer = data.get("answer", "")

    if not results:
        return f"🔍 搜索「{query}」没有找到相关结果。请尝试不同的关键词。"

    # 格式化输出
    lines = [f'## 🔍 搜索结果：「{query}」', ""]

    if answer:
        lines.append(f"**AI 摘要**：{answer}")
        lines.append("")

    lines.append(f"**共找到 {len(results)} 条结果：**")
    lines.append("")

    for i, r in enumerate(results, 1):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        content = r.get("content", "无摘要")
        # 截断过长摘要
        if len(content) > 300:
            content = content[:300] + "…"
        lines.append(f"{i}. **[{title}]({url})**")
        lines.append(f"   {content}")
        lines.append("")

    formatted = "\n".join(lines)

    # 存储到 Agent State 供后续步骤引用
    state.tool_results["web_search"] = {
        "query": query,
        "results": results,
        "answer": answer,
        "formatted": formatted,
    }

    return formatted
