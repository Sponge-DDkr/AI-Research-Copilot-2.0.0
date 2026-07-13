import { useEffect, useRef, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import type { TimelineStep, RagTracePayload } from '../types'

interface AgentTimelineProps {
  steps: TimelineStep[]
  loading: boolean
}

/** 单个时间线条目 */
function TimelineItem({ step, isLast }: { step: TimelineStep; isLast: boolean }) {
  const itemRef = useRef<HTMLDivElement>(null)

  // 自动滚动到最新步骤
  useEffect(() => {
    if (step.status === 'running') {
      itemRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [step.status])

  const statusColor = {
    running: 'border-blue-500 bg-blue-50',
    done: 'border-green-400 bg-white',
    error: 'border-red-400 bg-red-50',
  }[step.status]

  const dotColor = {
    running: 'bg-blue-500 shadow-[0_0_0_3px_rgba(59,130,246,0.3)] animate-pulse',
    done: 'bg-green-400',
    error: 'bg-red-400',
  }[step.status]

  return (
    <div ref={itemRef} className="flex gap-3 group">
      {/* 时间线竖线 + 圆点 */}
      <div className="flex flex-col items-center">
        <div className={`w-3 h-3 rounded-full border-2 border-white ${dotColor} flex-shrink-0 mt-1`} />
        {!isLast && <div className="w-0.5 flex-1 bg-gray-200 group-hover:bg-blue-200 transition-colors" />}
      </div>

      {/* 内容卡片 */}
      <div
        className={`flex-1 mb-3 rounded-lg border px-3 py-2 text-sm transition-all ${statusColor} ${
          step.status === 'running' ? 'shadow-md' : 'shadow-sm'
        }`}
      >
        <div className="flex items-center justify-between">
          <span className="font-medium text-gray-800 text-xs">{step.label}</span>
          <span className="text-[10px] text-gray-400">
            {new Date(step.timestamp).toLocaleTimeString()}
          </span>
        </div>
        {step.detail && (
          <p className="mt-1 text-xs text-gray-500 leading-relaxed break-words line-clamp-3">
            {step.detail}
          </p>
        )}
        {/* RAG Trace 卡片 */}
        {step.type === 'rag_trace' && step.ragTrace && (
          <RagTraceCard trace={step.ragTrace} />
        )}
      </div>
    </div>
  )
}

/** 检索片段得分色 — CrossEncoder v5.x 分数已在 [0,1]，阈值按实际区分度校准 */
function scoreColor(score: number): string {
  if (score >= 0.7) return 'text-green-600 bg-green-50'
  if (score >= 0.3) return 'text-yellow-600 bg-yellow-50'
  return 'text-red-500 bg-red-50'
}

/** RAG 检索 Trace 卡片 — 展示检索管线 + 片段列表 + 低相关度警告 */
function RagTraceCard({ trace }: { trace: RagTracePayload }) {
  if (!trace.chunks || trace.chunks.length === 0) return null

  const qualityBadge = {
    good: { text: '✓ 检索质量良好', color: 'bg-green-100 text-green-700 border-green-200' },
    borderline: { text: '⚠ 检索质量存疑', color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
    poor: { text: '✗ 检索质量差', color: 'bg-red-100 text-red-600 border-red-200' },
  }[trace.score_quality || 'good']

  return (
    <div className="mt-2 pt-2 border-t border-gray-100">
      {/* 管线标识 + 质量标签 */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className="text-[10px] font-mono bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">
          {trace.pipeline}
        </span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${qualityBadge.color}`}>
          {qualityBadge.text}
        </span>
        <span className="text-[10px] text-gray-400">
          Query: "{trace.query.slice(0, 60)}{trace.query.length > 60 ? '…' : ''}"
        </span>
      </div>

      {/* 低相关度警告 — 红色醒目 */}
      {trace.warning && (
        <div className="mb-2 p-2 rounded bg-red-50 border border-red-300 text-xs text-red-700 flex items-start gap-1.5 animate-pulse">
          <span className="flex-shrink-0 text-base">🚫</span>
          <div>
            <p className="font-semibold mb-0.5">检索质量不足 — 建议切换 web_search</p>
            <p className="text-red-600">{trace.warning}</p>
          </div>
        </div>
      )}

      {/* 片段列表 */}
      <div className="space-y-1.5">
        {trace.chunks.map((chunk, i) => (
          <div
            key={i}
            className="p-2 rounded bg-gray-50 border border-gray-100 hover:border-purple-200 transition-colors"
          >
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${scoreColor(chunk.score)}`}>
                #{chunk.rank} — {(chunk.score * 100).toFixed(0)}%
              </span>
              <span className="text-[10px] text-gray-500 font-mono truncate max-w-[180px]" title={chunk.source}>
                📄 {chunk.source}
              </span>
              {chunk.chunk_index && chunk.chunk_index !== '?' && (
                <span className="text-[10px] text-gray-400">片段 {chunk.chunk_index}</span>
              )}
            </div>
            <p className="text-[11px] text-gray-600 leading-relaxed line-clamp-2">
              {chunk.text}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 加载骨架屏 */
function SkeletonStep() {
  return (
    <div className="flex gap-3 animate-pulse">
      <div className="flex flex-col items-center">
        <div className="w-3 h-3 rounded-full bg-gray-300 mt-1" />
        <div className="w-0.5 flex-1 bg-gray-200" />
      </div>
      <div className="flex-1 mb-3 rounded-lg border border-gray-200 bg-white px-3 py-2">
        <div className="h-3 bg-gray-200 rounded w-24 mb-2" />
        <div className="h-2 bg-gray-100 rounded w-48" />
      </div>
    </div>
  )
}

/** Agent 执行过程时间线 */
export function AgentTimeline({ steps, loading }: AgentTimelineProps) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps.length])

  if (steps.length === 0 && !loading) return null

  return (
    <div className="border border-gray-200 rounded-xl bg-gray-50/50 p-3 sm:p-4 mb-4 transition-all">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-semibold text-gray-700">🤖 Agent 执行过程</span>
        {loading && (
          <span className="inline-flex items-center gap-1 text-xs text-blue-500">
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
            执行中...
          </span>
        )}
        {!loading && steps.length > 0 && (
          <span className="text-xs text-green-500 font-medium">✓ 完成</span>
        )}
      </div>

      <div className="max-h-64 overflow-y-auto">
        {steps.map((step, i) => (
          <TimelineItem key={step.id} step={step} isLast={i === steps.length - 1} />
        ))}

        {/* 加载占位 — 骨架屏 */}
        {loading && steps.length === 0 && (
          <div className="space-y-3 py-2">
            <SkeletonStep />
            <SkeletonStep />
          </div>
        )}

        <div ref={endRef} />
      </div>
    </div>
  )
}

/** 报告查看器 — 用 react-markdown 真正渲染 */
interface ReportViewerProps {
  report: string
}

export function ReportViewer({ report }: ReportViewerProps) {
  if (!report) return null

  // 清理 LLM 常见的格式问题：去除开头的引导语
  const cleanReport = useMemo(() => {
    let text = report
    // 去掉 "以下是完整的报告" / "最终报告如下" 等引导语
    text = text.replace(/^.*?(?:以下是|最终|完整).*?[：:]\s*/s, '')
    return text.trim()
  }, [report])

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-5 mb-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-gray-700">📄 研究报告</span>
        <ExportButton report={report} />
      </div>
      <div className="prose prose-sm max-w-none text-gray-800">
        <ReactMarkdown
          components={{
            // 表格渲染
            table: ({ children }) => (
              <div className="overflow-x-auto my-3">
                <table className="min-w-full border-collapse border border-gray-300 text-xs">
                  {children}
                </table>
              </div>
            ),
            th: ({ children }) => (
              <th className="border border-gray-300 bg-gray-100 px-3 py-1.5 text-left font-semibold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border border-gray-300 px-3 py-1.5">{children}</td>
            ),
            // 代码块
            code: ({ className, children, ...props }) => {
              const isInline = !className
              if (isInline) {
                return (
                  <code className="bg-gray-100 text-red-600 px-1 py-0.5 rounded text-xs" {...props}>
                    {children}
                  </code>
                )
              }
              return (
                <pre className="bg-gray-900 text-green-400 p-3 rounded-lg overflow-x-auto text-xs my-3">
                  <code className={className} {...props}>{children}</code>
                </pre>
              )
            },
            // 引用块
            blockquote: ({ children }) => (
              <blockquote className="border-l-4 border-blue-400 pl-4 py-1 my-3 bg-blue-50 rounded-r text-gray-600 text-sm">
                {children}
              </blockquote>
            ),
            // 链接在新窗口打开
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800 underline"
              >
                {children}
              </a>
            ),
            // 标题
            h1: ({ children }) => (
              <h1 className="text-xl font-bold mt-6 mb-3 text-gray-900 border-b pb-2">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-lg font-semibold mt-5 mb-2 text-gray-800">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-base font-semibold mt-4 mb-2 text-gray-700">{children}</h3>
            ),
            // 列表
            ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>,
            // 段落
            p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
            // 分割线
            hr: () => <hr className="my-4 border-gray-300" />,
          }}
        >
          {cleanReport}
        </ReactMarkdown>
      </div>
    </div>
  )
}

/** 导出按钮 — 下载 .md 文件 */
function ExportButton({ report }: { report: string }) {
  const handleExport = () => {
    // 清理引导语后提取第一行作为标题
    let text = report
    // 去掉 "以下是完整的报告" / "最终报告如下" 等引导语
    text = text.replace(/^.*?(?:以下是|最终|完整).*?[：:]\s*/s, '')

    const firstLine = text.trim().split('\n')[0] || '研究报告'
    let filename = firstLine.replace(/^#+\s*/, '').trim()

    // 清理文件名中的无效字符
    // Windows / macOS / Linux 共同禁用的字符：\/:*?"<>|
    filename = filename.replace(/[\\/:*?"<>|]/g, '-')
    // 多个连续空格/破折号合并
    filename = filename.replace(/\s+/g, ' ').replace(/-{2,}/g, '-')
    // 去掉首尾空格/点号
    filename = filename.replace(/^[.\s]+/, '').replace(/[.\s]+$/, '')
    // 截断到安全长度（留空间给 .md 后缀）
    filename = filename.slice(0, 80)

    if (!filename) filename = '研究报告'

    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <button
      onClick={handleExport}
      className="flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors cursor-pointer text-gray-600"
    >
      📥 下载 .md
    </button>
  )
}
