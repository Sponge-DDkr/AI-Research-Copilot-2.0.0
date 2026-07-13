import { useState, useRef, useEffect, useCallback } from 'react'

interface UploadStatus {
  loading: boolean
  result: { filename: string; chunks: number; message: string } | null
  error: string
}

interface KnowledgeFile {
  filename: string
  chunks: number
}

export function KnowledgeUpload({ onClose }: { onClose: () => void }) {
  const [status, setStatus] = useState<UploadStatus>({
    loading: false,
    result: null,
    error: '',
  })
  const [dragOver, setDragOver] = useState(false)
  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [filesLoading, setFilesLoading] = useState(true)
  const [deletingFile, setDeletingFile] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const ALLOWED_TYPES = '.pdf,.txt,.md,.markdown'

  // ── 获取文件列表 ──
  const fetchFiles = useCallback(async () => {
    setFilesLoading(true)
    try {
      const res = await fetch('/api/knowledge/files')
      if (res.ok) {
        const data: KnowledgeFile[] = await res.json()
        setFiles(data)
      }
    } catch {
      // 静默失败，不影响上传功能
    } finally {
      setFilesLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchFiles()
  }, [fetchFiles])

  // ── 上传 ──
  const handleUpload = async (file: File) => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    const allowed = ['.pdf', '.txt', '.md', '.markdown']
    if (!allowed.includes(ext)) {
      setStatus({ loading: false, result: null, error: `不支持的文件类型「${ext}」。支持：${allowed.join(', ')}` })
      return
    }

    if (file.size > 20 * 1024 * 1024) {
      setStatus({ loading: false, result: null, error: `文件过大（${(file.size / 1024 / 1024).toFixed(1)} MB），限制 20 MB` })
      return
    }

    setStatus({ loading: true, result: null, error: '' })

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/knowledge/upload', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: '上传失败' }))
        throw new Error(err.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()
      setStatus({ loading: false, result: data, error: '' })
      // 刷新文件列表
      fetchFiles()
    } catch (err) {
      setStatus({
        loading: false,
        result: null,
        error: err instanceof Error ? err.message : '上传失败',
      })
    }
  }

  // ── 删除文件 ──
  const handleDeleteFile = async (filename: string) => {
    if (!confirm(`确认删除「${filename}」？此操作不可撤销。`)) return

    setDeletingFile(filename)
    try {
      const res = await fetch(`/api/knowledge/files/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: '删除失败' }))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      // 从列表中移除
      setFiles((prev) => prev.filter((f) => f.filename !== filename))
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeletingFile(null)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleUpload(file)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleUpload(file)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => setDragOver(false)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-5 sm:p-6 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <h2 className="text-lg font-semibold text-gray-900">📚 上传知识库</h2>
          <button
            className="text-gray-400 hover:text-gray-600 transition-colors cursor-pointer text-xl leading-none"
            onClick={onClose}
          >
            ✕
          </button>
        </div>

        <p className="text-sm text-gray-500 mb-4 flex-shrink-0">
          上传 PDF、TXT 或 Markdown 文档，Agent 在研究时可自动引用本地知识库内容。
        </p>

        {/* Drop Zone */}
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer flex-shrink-0 ${
            dragOver
              ? 'border-blue-400 bg-blue-50'
              : 'border-gray-300 hover:border-blue-300 hover:bg-gray-50'
          }`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept={ALLOWED_TYPES}
            className="hidden"
            onChange={handleFileChange}
            disabled={status.loading}
          />

          {status.loading ? (
            <div>
              <div className="flex items-center justify-center gap-2 text-blue-600">
                <span className="w-5 h-5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm font-medium">正在处理...</span>
              </div>
              <p className="text-xs text-gray-400 mt-2">提取文本 → 切片 → 向量化</p>
            </div>
          ) : (
            <div>
              <p className="text-3xl mb-2">📄</p>
              <p className="text-sm text-gray-600 font-medium">拖拽文件到此处或点击上传</p>
              <p className="text-xs text-gray-400 mt-1">
                支持 PDF、TXT、Markdown（≤20MB）
              </p>
            </div>
          )}
        </div>

        {/* Result */}
        {status.result && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-xl text-sm flex-shrink-0">
            <p className="text-green-700 font-medium">✅ 上传成功</p>
            <p className="text-green-600 text-xs mt-1">
              {status.result.filename} — 已索引 {status.result.chunks} 个文本片段
            </p>
          </div>
        )}

        {/* Error */}
        {status.error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex-shrink-0">
            ❌ {status.error}
          </div>
        )}

        {/* ── 已上传文件列表 ── */}
        <div className="mt-4 flex-1 min-h-0 overflow-y-auto border-t border-gray-100 pt-4">
          <h3 className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1">
            📋 已上传文件
            {!filesLoading && files.length > 0 && (
              <span className="text-xs text-gray-400 font-normal">({files.length})</span>
            )}
          </h3>

          {filesLoading && (
            <p className="text-xs text-gray-400 py-2">加载中...</p>
          )}

          {!filesLoading && files.length === 0 && (
            <p className="text-xs text-gray-400 py-2">暂无文件，上传一个试试吧</p>
          )}

          {!filesLoading && files.length > 0 && (
            <ul className="space-y-1">
              {files.map((f) => (
                <li
                  key={f.filename}
                  className="flex items-center justify-between px-3 py-2 bg-gray-50 rounded-lg text-sm group hover:bg-gray-100 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <span className="text-gray-700 truncate block text-xs">📄 {f.filename}</span>
                    <span className="text-xs text-gray-400">{f.chunks} 个切片</span>
                  </div>
                  <button
                    onClick={() => handleDeleteFile(f.filename)}
                    disabled={deletingFile === f.filename}
                    className="text-gray-300 hover:text-red-500 text-xs cursor-pointer flex-shrink-0 ml-2 disabled:opacity-50"
                    title="删除此文件"
                  >
                    {deletingFile === f.filename ? '⏳' : '🗑️'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="mt-3 text-xs text-gray-400 flex-shrink-0">
          Agent 通过 <code className="bg-gray-100 px-1 rounded">search_knowledge_base</code> 工具检索上传的文档。
        </div>
      </div>
    </div>
  )
}
