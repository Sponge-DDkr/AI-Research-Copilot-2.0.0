# AI Agent 技术选型决策记录

> 决策日期：2026-06-01 | 决策者：架构组（孙架构、钱后端、赵前端）
> 决策类型：架构决策 | 状态：已执行

---

## 决策背景

AI Research Copilot 项目启动前，需要确定 Agent 编排框架。市场上有多个选项，各有利弊。

---

## 候选方案

### 选项 1：LangChain + LangGraph

**简介**：Python AI 框架的事实标准，LangGraph 提供了 StateGraph 循环能力。

**优势**：
- 生态最丰富（200+ integrations，100+ 内置工具）
- 社区活跃（GitHub 90k+ stars）
- 文档相对完善
- 面试认可度最高

**劣势**：
- 抽象层太厚：`RunnablePassthrough` / `RunnableLambda` / `RunnableSequence` 等概念学习成本高
- 版本迭代快但不稳定：0.1 → 0.2 → 0.3 每次升级有破坏性变更
- 隐藏了太多细节：Agent 循环的具体行为对开发者不透明
- 对于我们的简单场景（10 个工具、单 Agent Loop），LangGraph 是杀鸡用牛刀
- 序列化限制：所有 State 必须可序列化（JSON），限制了工具返回复杂对象

### 选项 2：自研 Unified Agent Loop ✅（最终选择）

**简介**：200 行 Python 实现 ReAct + Plan-and-Execute 混合循环。

**优势**：
- **完全透明**：每一行代码都是自己写的，出问题能定位到具体行
- **极致可控**：Stop Gate、复杂度判断、工具过滤、记忆注入等定制逻辑天然集成
- **没有黑盒**：不依赖第三方框架的版本变更
- **学习价值**：自己实现一遍，面试时能把原理讲透
- **轻量**：0 额外依赖（除了 httpx 调 LLM API）

**劣势**：
- 功能不全：没有 LangSmith 那样的调试追踪
- 需要自己维护和演进
- 没有社区支持
- 工具生态需要自己搭建

### 选项 3：CrewAI / AutoGen 多 Agent 框架

**简介**：定义多个 Agent 角色，让它们自动协作。

**劣势（一票否决）**：
- Agent 之间的通信靠 LLM 生成的自然语言，一个研究任务可能要 30-50 次 LLM 调用
- 成本不可控：一次简单搜索可能触发 Agent 之间的「无限对话」
- 不确定性强：同样的输入输出差异大
- 不适合生产环境：更适合实验和 Demo

---

## 对比矩阵

| 维度 | LangChain+LangGraph | 自研 Unified Loop | CrewAI/AutoGen |
|------|-------------------|-------------------|----------------|
| 学习成本 | ⭐⭐ 高（框架概念多） | ⭐⭐⭐ 中（需要理解原理） | ⭐ 低（上手快） |
| 可控性 | ⭐⭐ 中 | ⭐⭐⭐ 高 | ⭐ 低 |
| 面试加分 | ⭐⭐⭐ 高（行业标准） | ⭐⭐⭐ 高（展示原理理解） | ⭐ 低（调 API 的印象） |
| 代码量 | 少（框架代码） | ~200 行 | 少（配置式） |
| 可调试性 | ⭐⭐ 中（LangSmith 加持） | ⭐⭐ 中（需自建日志） | ⭐ 低（黑盒） |
| 灵活度 | ⭐⭐ 中（框架约束） | ⭐⭐⭐ 高（任意定制） | ⭐ 低（固定模式） |
| 稳定性 | ⭐⭐ 中（版本变更频繁） | ⭐⭐⭐ 高（自己控制） | ⭐ 低（框架不成熟） |

---

## 最终决策：选项 2 —— 自研 Unified Agent Loop

### 核心理由

> "理解原理比使用框架更重要。自己实现一遍 Agent Loop，200 行代码换来的理解，比跟着 LangChain 教程跑 10 遍更深。面试时，能讲清楚 'Agent 循环的每一步发生了什么' 比 '我用过 LangGraph' 更能证明技术深度。"
>
> — 孙架构，决策会议上的总结

### 决策后的补充说明

这个决策**不等于否定 LangChain**。在以下场景中，我们仍然会使用 LangChain：
- 需要快速接入某小众 LLM 提供商时（LangChain 的 `ChatModel` 抽象屏蔽差异）
- 文档加载器（`PyPDFLoader` / `UnstructuredMarkdownLoader`）——没必要重复造轮子
- 评估框架（LangSmith 的 Tracing 能力在调试时很有用）

**核心原则**：核心逻辑（Agent Loop、工具调度、记忆管理）自己掌控。周边设施（文档加载、评估）可以用现成的。

---

## 后续演进计划

如果项目发展顺利（超过 20 个工具 / 需要多人协作），会考虑：
1. 将自研 Loop 抽象为内部框架，定义 Standard Tool Interface
2. 引入 LangGraph 但只用于复杂分支流程（如多 Agent 辩论模式），简单路径仍是自研
3. 不自研的工具部分（文档加载）继续用 LangChain 组件

---

## 关键参考资料

1. FastGPT v4.15 源码 `unifiedLoop.ts` — Agent 可自主回退的设计灵感来源
2. Anthropic 的 Building Effective Agents 博客（2024.12）— "简单方案优先"的设计哲学
3. LangGraph 的 StateGraph 设计 — Plan State 数据结构的参考
4. Lilian Weng 的 LLM Powered Autonomous Agents 博客 — ReAct vs Plan-and-Execute 的理论基础

---

## 附录：如果面试官问「为什么不用 LangChain」

**标准回答**：

> "我评估了 LangChain + LangGraph，它的 StateGraph 概念很好，但对我们当前 10 个工具的场景来说抽象层太厚。LangGraph 的每次版本升级都有破坏性变更（0.1→0.2→0.3），维护成本不低。
>
> 更重要的是，自己实现 Agent Loop 让我真正理解了每一步的原理——LLM 怎么决策、工具怎么注册和调度、Stop Gate 怎么设计、状态怎么管理。这段经历在面试时更能讲清楚技术细节。
>
> 我没有完全否定 LangChain——它的文档加载器（PyPDFLoader 等）我仍然在用，没必要重复造轮子。核心逻辑自己掌控，周边设施复用开源，这是我的策略。"
