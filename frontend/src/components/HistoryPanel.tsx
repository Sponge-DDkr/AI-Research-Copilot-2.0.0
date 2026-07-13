import { useState, useEffect, useCallback } from 'react'

interface HistoryItem {
  id: number
  task: string
  depth: string
  iterations: number
  plan_steps: number
  created_at: string
  preview: string
}

interface HistoryDetail {
  id: number
  task: string
  report: string
  depth: string
  iterations: number
  plan_steps: number
  events_json: string
  created_at: string
}

interface HistoryPanelProps {
  /** 选中历史报告时的回调 */
  onSelectReport: (report: string) => void
  /** 关闭面板 */
  onClose: () => void
}

export function HistoryPanel({ onSelectReport, onClose }: HistoryPanelProps) {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<HistoryDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const fetchList = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/history?limit=50')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setItems(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchList()
  }, [fetchList])

  const handleViewDetail = async (id: number) => {
    setDetailLoading(true)
    setDetail(null)
    try {
      const res = await fetch(`/api/history/${id}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: HistoryDetail = await res.json()
      setDetail(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除这份报告？')) return
    try {
      await fetch(`/api/history/${id}`, { method: 'DELETE' })
      setItems((prev) => prev.filter((item) => item.id !== id))
      if (detail?.id === id) setDetail(null)
    } catch {
      setError('删除失败')
    }
  }

  const handleClearAll = async () => {
    if (!confirm('确认清空所有历史报告？此操作不可撤销！')) return
    try {
      const res = await fetch('/api/history', { method: 'DELETE' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setItems([])
      setDetail(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '清空失败')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      {/* 面板 */}
      <div className="relative w-full max-w-md h-full bg-white shadow-xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h2 className="text-base font-semibold text-gray-800">📚 历史报告</h2>
          <div className="flex items-center gap-2">
            {items.length > 0 && (
              <button
                onClick={handleClearAll}
                className="text-xs text-red-400 hover:text-red-600 cursor-pointer px-2 py-1 rounded hover:bg-red-50 transition-colors"
                title="清空全部"
              >
                清空全部
              </button>
            )}
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-lg cursor-pointer"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-12 text-sm text-gray-400">
              加载中...
            </div>
          )}

          {error && (
            <div className="mx-4 mt-4 p-3 bg-red-50 rounded-lg text-sm text-red-600">
              {error}
              <button
                onClick={fetchList}
                className="ml-2 underline cursor-pointer"
              >
                重试
              </button>
            </div>
          )}

          {!loading && items.length === 0 && (
            <div className="text-center py-12 text-sm text-gray-400">
              <p className="text-3xl mb-2">📭</p>
              <p>暂无历史报告</p>
              <p className="text-xs mt-1">完成一次深度研究后，报告将自动保存到这里</p>
            </div>
          )}

          {/* 报告列表 */}
          {items.map((item) => (
            <div
              key={item.id}
              className={`border-b border-gray-100 px-5 py-3 cursor-pointer hover:bg-gray-50 transition-colors ${
                detail?.id === item.id ? 'bg-blue-50' : ''
              }`}
              onClick={() => handleViewDetail(item.id)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-800 truncate">{item.task}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {item.created_at} · {item.iterations}轮 · {item.plan_steps}步 · {item.depth}
                  </p>
                  <p className="text-xs text-gray-500 mt-1 truncate">{item.preview}</p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(item.id)
                  }}
                  className="text-gray-300 hover:text-red-500 text-xs cursor-pointer flex-shrink-0 mt-1"
                  title="删除"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Detail Panel — 选中报告后展示 */}
        {detailLoading && (
          <div className="border-t border-gray-200 px-5 py-4 text-sm text-gray-400">
            加载详情...
          </div>
        )}

        {detail && !detailLoading && (
          <div className="border-t border-gray-200 max-h-64 overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-3 bg-gray-50">
              <span className="text-sm font-medium text-gray-700 truncate flex-1">
                {detail.task}
              </span>
              <div className="flex gap-2 flex-shrink-0">
                <button
                  onClick={() => onSelectReport(detail.report)}
                  className="px-3 py-1 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700 cursor-pointer"
                >
                  查看完整报告
                </button>
                <button
                  onClick={() => setDetail(null)}
                  className="px-3 py-1 text-xs bg-gray-200 text-gray-600 rounded-md hover:bg-gray-300 cursor-pointer"
                >
                  收起
                </button>
              </div>
            </div>
            <div className="px-5 py-3 text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">
              {detail.report.slice(0, 500)}
              {detail.report.length > 500 && (
                <span className="text-gray-400">...（点击上方按钮查看完整报告）</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
