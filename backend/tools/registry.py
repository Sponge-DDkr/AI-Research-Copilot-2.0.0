"""工具注册中心 — 单例模式，管理所有 Agent 可调用的工具"""

from typing import Any, Callable

# 工具函数签名: async def tool(state, llm, **kwargs) -> str


class ToolRegistry:
    """工具注册中心 — 装饰器注册 + schema 生成 + 调度执行"""

    _instance: "ToolRegistry | None" = None
    _tools: dict[str, dict[str, Any]] = {}

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, name: str, description: str, parameters: dict):
        """装饰器：注册一个工具函数

        用法:
            @registry.register(
                name="my_tool",
                description="...",
                parameters={"type": "object", "properties": {...}}
            )
            async def my_tool(state, llm, **kwargs) -> str:
                ...
        """

        def decorator(func: Callable):
            self._tools[name] = {
                "func": func,
                "schema": {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                },
            }
            return func

        return decorator

    def get_all_schemas(self) -> list[dict]:
        """返回所有工具的 OpenAI 兼容 function schema 列表"""
        return [t["schema"] for t in self._tools.values()]

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, tool_name: str, state, llm, **tool_args) -> str:
        """执行指定工具

        Args:
            tool_name: 工具名
            state: AgentState 实例
            llm: LLM 客户端（AsyncOpenAI）
            **tool_args: LLM 传入的工具参数

        Returns:
            工具执行结果字符串
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return f"[Error] 未知工具: {tool_name}，可用工具: {', '.join(self.get_tool_names())}"

        try:
            result = await tool["func"](state=state, llm=llm, **tool_args)
            return str(result) if result is not None else "（工具执行完毕，无返回内容）"
        except Exception as e:
            return f"[Error] 工具 {tool_name} 执行失败: {str(e)}"


# 全局单例
registry = ToolRegistry()
