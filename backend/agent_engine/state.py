"""Agent 状态数据结构 — AgentState + PlanStep"""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class PlanStep:
    """计划步骤 — 由 LLM 通过 create_plan 工具创建"""

    id: str
    description: str
    status: str = "pending"  # pending | in_progress | done | skipped
    content: str = ""  # 步骤产出内容（如 write_section 的结果）


@dataclass
class AgentState:
    """Agent 共享状态 — 在整个 Loop 中传递和更新"""

    task: str
    plan: list[PlanStep] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    final_report: str = ""
    emitter: Any = None  # SSE 事件发射器（Loop 注入，供工具发射 rag_trace 用）

    # ── 辅助方法 ──

    def add_plan_steps(self, descriptions: list[str]) -> list[PlanStep]:
        """批量创建 PlanStep 并追加到 plan 列表"""
        new_steps = [
            PlanStep(id=f"step_{uuid4().hex[:8]}", description=desc)
            for desc in descriptions
        ]
        self.plan.extend(new_steps)
        return new_steps

    def get_pending_steps(self) -> list[PlanStep]:
        return [s for s in self.plan if s.status == "pending"]

    def get_step_by_id(self, step_id: str) -> PlanStep | None:
        for s in self.plan:
            if s.id == step_id:
                return s
        return None

    def get_plan_summary(self) -> str:
        """生成 plan 状态摘要，注入 LLM 上下文"""
        if not self.plan:
            return "（暂无计划）"
        lines = []
        for s in self.plan:
            icon = {"pending": "⬜", "in_progress": "🔄", "done": "✅", "skipped": "⏭️"}.get(s.status, "❓")
            lines.append(f"  {icon} {s.id}: {s.description}")
        return "\n".join(lines)
