import { useState, useRef, useCallback } from 'react'
import type { AgentEvent, TimelineStep } from '../types'

/** 将 SSE 事件映射为时间线步骤 */
function eventToStep(event: AgentEvent, id: number): TimelineStep {
  const base = {
    id: `step-${id}`,
    timestamp: Date.now(),
    status: 'done' as const,
  }

  switch (event.type) {
    case 'task_started':
      return {
        ...base,
        status: 'running',
        type: 'task_started',
        label: '🎯 任务启动',
        detail: event.task as string || '',
      }

    case 'complexity_hint':
      return {
        ...base,
        type: 'complexity_hint',
        label: '🔍 复杂度预判',
        detail: `${event.bias || 'auto'} — ${event.reason || ''} (depth: ${event.depth || 'auto'})`,
      }

    case 'plan_created': {
      const steps = event.steps as Array<{ description: string }> | undefined
      return {
        ...base,
        type: 'plan_created',
        label: '📋 制定计划',
        detail: steps ? `${steps.length} 个步骤：${steps.map(s => s.description).join(' → ')}` : '',
      }
    }

    case 'step_started':
      return {
        ...base,
        status: 'running',
        type: 'step_started',
        label: '▶️ 步骤开始',
        detail: event.description as string || '',
      }

    case 'step_completed':
      return {
        ...base,
        type: 'step_completed',
        label: '✅ 步骤完成',
        detail: event.step_id as string || '',
      }

    case 'tool_executed': {
      const preview = (event.result_preview as string || '').slice(0, 120)
      return {
        ...base,
        type: 'tool_executed',
        label: `🔧 ${event.tool || '工具'}`,
        detail: preview || '执行完成',
      }
    }

    case 'rag_trace': {
      const payload = {
        tool: event.tool as string || '',
        query: event.query as string || '',
        pipeline: event.pipeline as string || '',
        chunks: (event.chunks || []) as Array<{
          text: string; source: string; chunk_index: string; score: number; rank: number;
        }>,
        warning: event.warning as string || '',
        score_quality: event.score_quality as string || 'good',
      }
      return {
        ...base,
        type: 'rag_trace',
        label: `🔬 RAG 检索 Trace`,
        detail: `${event.tool || ''}: "${(event.query as string || '').slice(0, 80)}"`,
        ragTrace: payload,
      }
    }

    case 'tool_retry':
      return {
        ...base,
        type: 'tool_retry',
        label: `🔄 重试：${event.tool || ''}`,
        detail: `第 ${event.attempt} 次重试 — ${event.reason || '未知原因'}`,
      }

    case 'revision_requested':
      return {
        ...base,
        type: 'revision_requested',
        label: '📝 Stop Gate 要求修正',
        detail: (event.feedback as string || '').slice(0, 200),
      }

    case 'error':
      return {
        ...base,
        status: 'error',
        type: 'error',
        label: '❌ 错误',
        detail: event.message as string || '未知错误',
      }

    case 'stopgate_passed':
      return {
        ...base,
        type: 'stopgate_passed',
        label: '🛡️ 质量检查通过',
        detail: `5项检查全部通过 | 字数: ${event.content_length || '?'} | 步骤: ${event.plan_done || 0}/${event.plan_total || 0} | URL引用: ${event.has_url ? '✅' : '❌'}`,
      }

    case 'complete':
      return {
        ...base,
        type: 'complete',
        label: '🎉 报告完成',
        detail: '最终报告已生成',
      }

    default:
      return {
        ...base,
        type: event.type as TimelineStep['type'],
        label: event.type,
        detail: JSON.stringify(event),
      }
  }
}

interface UseResearchStreamReturn {
  /** SSE 事件时间线 */
  steps: TimelineStep[]
  /** 最终报告内容 */
  report: string
  /** 是否正在执行 */
  loading: boolean
  /** 错误信息 */
  error: string
  /** 当前步骤计数 */
  stepCount: number
  /** 启动流式研究 */
  startResearch: (task: string, depth?: 'auto' | 'quick' | 'deep') => Promise<void>
  /** 重置状态 */
  reset: () => void
}

export function useResearchStream(): UseResearchStreamReturn {
  const [steps, setSteps] = useState<TimelineStep[]>([])
  const [report, setReport] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [stepCount, setStepCount] = useState(0)
  const abortRef = useRef<AbortController | null>(null)
  const stepIdRef = useRef(0)

  const reset = useCallback(() => {
    setSteps([])
    setReport('')
    setLoading(false)
    setError('')
    setStepCount(0)
    stepIdRef.current = 0
  }, [])

  const startResearch = useCallback(
    async (task: string, depth: 'auto' | 'quick' | 'deep' = 'auto') => {
      // 中断之前的请求
      abortRef.current?.abort()
      reset()

      const controller = new AbortController()
      abortRef.current = controller
      setLoading(true)

      try {
        const response = await fetch('/api/research/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task, depth }),
          signal: controller.signal,
        })

        if (!response.ok) {
          const err = await response.json().catch(() => ({ detail: '请求失败' }))
          throw new Error(err.detail || `HTTP ${response.status}`)
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error('浏览器不支持流式读取')

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // 解析 SSE 事件行
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // 保留未完成的行

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6).trim()
              if (data === '[DONE]') continue

              try {
                const event: AgentEvent = JSON.parse(data)
                stepIdRef.current += 1
                const step = eventToStep(event, stepIdRef.current)

                // 完成之前运行的步骤，标记当前为 running
                setSteps(prev => {
                  const updated = prev.map(s =>
                    s.status === 'running' ? { ...s, status: 'done' as const } : s
                  )
                  return [...updated, step]
                })
                setStepCount(prev => prev + 1)

                if (event.type === 'complete') {
                  setReport((event.report as string) || '')
                }
              } catch {
                // 忽略解析失败的行
              }
            }
          }
        }

        setSteps(prev =>
          prev.map(s => (s.status === 'running' ? { ...s, status: 'done' as const } : s))
        )
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        const msg = err instanceof Error ? err.message : '未知错误'
        setError(msg)
      } finally {
        setLoading(false)
      }
    },
    [reset]
  )

  return { steps, report, loading, error, stepCount, startResearch, reset }
}
