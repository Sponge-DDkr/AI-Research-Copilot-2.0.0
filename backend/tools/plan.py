"""计划管理工具 — create_plan / update_plan"""

from tools.registry import registry


@registry.register(
    name="create_plan",
    description=(
        "将复杂的用户任务拆解为可执行的计划步骤。"
        "对于需要多步才能完成的复杂任务（如写报告、做研究），必须先调用此工具制定计划。"
        "对于简单的一问一答（如问定义、翻译），不需要计划，直接回答即可。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "description": "计划步骤列表，每个步骤一句话描述要做的事。建议 2-5 个步骤。",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 10,
            }
        },
        "required": ["steps"],
    },
)
async def create_plan(state, llm, steps: list[str]) -> str:
    """创建研究计划 — 将 LLM 提供的步骤写入 AgentState"""
    new_steps = state.add_plan_steps(steps)

    lines = ["✅ 计划已创建，共 {} 个步骤：".format(len(new_steps))]
    for i, s in enumerate(new_steps, 1):
        lines.append(f"  {i}. [{s.id}] {s.description}")

    lines.append("")
    lines.append("下一步：请按计划逐步执行。使用 write_section 工具撰写每个章节。")
    return "\n".join(lines)


@registry.register(
    name="update_plan",
    description="更新计划状态：标记步骤完成、跳过或添加新步骤。",
    parameters={
        "type": "object",
        "properties": {
            "step_id": {
                "type": "string",
                "description": "要更新的步骤 ID",
            },
            "status": {
                "type": "string",
                "enum": ["done", "skipped", "in_progress"],
                "description": "新状态",
            },
        },
        "required": ["step_id", "status"],
    },
)
async def update_plan(state, llm, step_id: str, status: str) -> str:
    """更新计划步骤状态"""
    step = state.get_step_by_id(step_id)
    if not step:
        return f"[Error] 未找到步骤 {step_id}，当前步骤: {[s.id for s in state.plan]}"

    step.status = status
    return f"✅ 步骤 [{step_id}] {step.description} → {status}"
