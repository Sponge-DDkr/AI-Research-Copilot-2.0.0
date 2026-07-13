"""共享 LLM 客户端工厂 — 统一 DeepSeek API 调用"""

from openai import AsyncOpenAI

from config import get_config


def create_llm_client() -> AsyncOpenAI:
    """创建 AsyncOpenAI 客户端，附加 model 属性供 Agent Loop 使用"""
    config = get_config()

    if not config.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")

    client = AsyncOpenAI(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
    )

    # 附加 model 名，方便 Agent Loop 和 Tools 引用
    client.model = config.deepseek_model  # type: ignore[attr-defined]

    return client
