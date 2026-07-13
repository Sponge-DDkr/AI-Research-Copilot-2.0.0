/** SSE 事件类型 */
export interface AgentEvent {
  type: string
  [key: string]: unknown
}

/** Chat 请求 */
export interface ChatRequest {
  message: string
}

/** Chat 响应 */
export interface ChatResponse {
  reply: string
  model: string
}

/** Research 请求 */
export interface ResearchRequest {
  task: string
  max_iterations?: number
  depth?: 'auto' | 'quick' | 'deep'
}

/** Research 同步响应 */
export interface ResearchResponse {
  report: string
  iterations: number
  plan_steps: number
  events: AgentEvent[]
}

/** Agent 事件类型名 */
export type AgentEventType =
  | 'task_started'
  | 'complexity_hint'
  | 'plan_created'
  | 'step_started'
  | 'step_completed'
  | 'tool_executed'
  | 'tool_retry'
  | 'revision_requested'
  | 'stopgate_passed'
  | 'rag_trace'
  | 'error'
  | 'complete'

/** RAG 检索片段 */
export interface RagChunk {
  text: string
  source: string
  chunk_index: string
  score: number
  rank: number
}

/** RAG Trace 事件载荷 */
export interface RagTracePayload {
  tool: string
  query: string
  pipeline: string
  chunks: RagChunk[]
  warning: string
  /** 分数质量标签：good | borderline | poor */
  score_quality: string
}

/** Agent 时间线步骤 */
export interface TimelineStep {
  id: string
  type: AgentEventType
  label: string
  detail: string
  timestamp: number
  status: 'running' | 'done' | 'error'
  /** RAG 检索 Trace（仅 rag_trace 事件携带） */
  ragTrace?: RagTracePayload
}
