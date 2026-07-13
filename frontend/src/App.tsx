import { useState, useRef, useEffect } from 'react'
import { sendMessage, healthCheck } from './api/client'
import { useResearchStream } from './hooks/useResearchStream'
import { AgentTimeline, ReportViewer } from './components/AgentTimeline'
import { HistoryPanel } from './components/HistoryPanel'
import { KnowledgeUpload } from './components/KnowledgeUpload'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

type AppMode = 'chat' | 'research'

function App() {
  const [mode, setMode] = useState<AppMode>('research')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [apiStatus, setApiStatus] = useState<string>('检查中...')
  const [showHistory, setShowHistory] = useState(false)
  const [showKnowledge, setShowKnowledge] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Research 模式 Hook
  const {
    steps,
    report,
    loading: researchLoading,
    error: researchError,
    stepCount,
    startResearch,
    reset: resetResearch,
  } = useResearchStream()

  // Chat 模式 loading
  const [chatLoading, setChatLoading] = useState(false)
  const loading = mode === 'research' ? researchLoading : chatLoading

  // 启动时检查后端联通性
  useEffect(() => {
    healthCheck().then((res) => {
      setApiStatus(res.status === 'ok' ? '✅ 已连接' : `⚠️ ${res.message || '未连接'}`)
    }).catch(() => {
      setApiStatus('❌ 后端未启动')
    })
  }, [])

  // 自动滚动到底部（chat 模式）
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    setInput('')

    if (mode === 'research') {
      await startResearch(text)
    } else {
      setMessages((prev) => [...prev, { role: 'user', content: text }])
      setChatLoading(true)

      try {
        const response = await sendMessage(text)
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: response.reply },
        ])
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : '未知错误'
        const hint = errMsg.includes('请求失败')
          ? '\n\n> 💡 提示：请确认后端服务是否已启动（`cd backend && python main.py`），或刷新页面重试。'
          : errMsg.includes('502') || errMsg.includes('503')
            ? '\n\n> 💡 提示：LLM API 调用异常，请检查 .env 中的 DEEPSEEK_API_KEY 是否有效，或稍后重试。'
            : '\n\n> 💡 提示：如持续出现此错误，请检查控制台或后端日志排查。'
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: `❌ 出错了：${errMsg}${hint}`,
          },
        ])
      } finally {
        setChatLoading(false)
      }
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleModeSwitch = (newMode: AppMode) => {
    setMode(newMode)
    // 不再清空研究状态，切换回来时可以继续查看
  }

  // 从历史面板加载的静态报告
  const [historyReport, setHistoryReport] = useState<string | null>(null)

  const handleSelectHistoryReport = (historyReportStr: string) => {
    setHistoryReport(historyReportStr)
    setMode('research')
    setShowHistory(false)
  }

  const displayReport = historyReport || report

  const isResearchMode = mode === 'research'

  return (
    <div className="flex flex-col h-dvh max-w-3xl mx-auto px-2 sm:px-0">
      {/* History Panel */}
      {showHistory && (
        <HistoryPanel
          onSelectReport={handleSelectHistoryReport}
          onClose={() => setShowHistory(false)}
        />
      )}

      {/* Knowledge Upload Modal */}
      {showKnowledge && (
        <KnowledgeUpload onClose={() => setShowKnowledge(false)} />
      )}

      {/* Header */}
      <header className="flex items-center justify-between px-3 sm:px-6 py-3 sm:py-4 border-b border-gray-200 gap-2">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-bold text-gray-900 truncate">
            AI Research Copilot
          </h1>
          <p className="text-xs sm:text-sm text-gray-500 hidden sm:block">单 Agent 多工具自主研究助手</p>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-3 flex-shrink-0">
          {/* 知识库按钮 */}
          <button
            onClick={() => setShowKnowledge(true)}
            className="px-2 sm:px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors cursor-pointer text-gray-600"
            title="上传知识库文档"
          >
            <span className="hidden sm:inline">📚 知识库</span>
            <span className="sm:hidden">📚</span>
          </button>
          {/* 历史按钮 */}
          <button
            onClick={() => setShowHistory(true)}
            className="px-2 sm:px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors cursor-pointer text-gray-600"
            title="查看历史报告"
          >
            <span className="hidden sm:inline">🕐 历史</span>
            <span className="sm:hidden">🕐</span>
          </button>
          {/* 模式切换 */}
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            <button
              className={`px-2 sm:px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                mode === 'chat'
                  ? 'bg-white text-gray-800 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              onClick={() => handleModeSwitch('chat')}
            >
              💬
            </button>
            <button
              className={`px-2 sm:px-3 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                mode === 'research'
                  ? 'bg-white text-blue-600 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              onClick={() => handleModeSwitch('research')}
            >
              🔬
            </button>
          </div>
          <span className="text-xs text-gray-400 hidden sm:inline">{apiStatus}</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {/* ===== Research 模式 ===== */}
        {isResearchMode && (
          <>
            {/* 空状态提示 */}
            {steps.length === 0 && !loading && !report && (
              <div className="text-center text-gray-400 mt-32">
                <p className="text-4xl mb-4">🔬</p>
                <p className="text-lg font-medium">AI Research Copilot</p>
                <p className="text-sm mt-2">
                  输入一个研究主题，Agent 将自主调用工具完成深度研究
                </p>
                <div className="mt-6 flex flex-wrap justify-center gap-2 text-xs">
                  {[
                    '新能源汽车市场趋势',
                    'AI Agent 技术发展现状',
                    '量子计算最新进展',
                  ].map((hint) => (
                    <button
                      key={hint}
                      className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-full text-gray-600 transition-colors cursor-pointer"
                      onClick={() => setInput(hint)}
                    >
                      {hint}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Agent 时间线 */}
            <AgentTimeline steps={steps} loading={loading} />

            {/* 状态栏 */}
            {(steps.length > 0 || report) && !loading && (
              <div className="text-center">
                <button
                  className="text-xs text-gray-400 hover:text-blue-500 transition-colors cursor-pointer"
                  onClick={resetResearch}
                >
                  🗑️ 清除结果，开始新研究
                </button>
              </div>
            )}
            {loading && (
              <div className="text-center py-3">
                <div className="inline-flex items-center gap-2 px-4 py-2 bg-blue-50 rounded-full">
                  <span className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  <span className="text-xs text-blue-600 font-medium">
                    Agent 正在工作中 · 已执行 {stepCount} 步
                  </span>
                </div>
              </div>
            )}

            {/* 错误提示 */}
            {researchError && (
              <div className="border border-red-200 rounded-xl bg-red-50 p-4 text-sm text-red-700">
                <p className="font-medium mb-1">❌ 研究执行失败</p>
                <p className="text-red-600">{researchError}</p>
                <p className="text-xs text-red-400 mt-2">
                  💡 常见原因：API Key 无效、网络超时、任务过于复杂。
                  请检查后端日志或尝试简化任务描述后重试。
                </p>
                <button
                  className="mt-2 text-xs text-red-500 hover:text-red-700 underline cursor-pointer"
                  onClick={resetResearch}
                >
                  清除结果，重新开始
                </button>
              </div>
            )}

            {/* 最终报告 */}
            <ReportViewer report={displayReport} />
          </>
        )}

        {/* ===== Chat 模式 ===== */}
        {!isResearchMode && (
          <>
            {messages.length === 0 && (
              <div className="text-center text-gray-400 mt-32">
                <p className="text-4xl mb-4">💬</p>
                <p className="text-lg font-medium">聊天模式</p>
                <p className="text-sm mt-2">快速问答，对话交流</p>
              </div>
            )}

            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {chatLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-2xl px-4 py-3">
                  <div className="flex items-center gap-1">
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                    <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </>
        )}
      </main>

      {/* Input */}
      <footer className="border-t border-gray-200 px-3 sm:px-6 py-3 sm:py-4">
        <div className="flex gap-2 sm:gap-3">
          <textarea
            className="flex-1 resize-none rounded-xl border border-gray-300 px-3 sm:px-4 py-2.5 sm:py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            rows={2}
            placeholder={
              isResearchMode
                ? '输入研究主题，例如：分析 2026 年新能源汽车市场趋势...'
                : '输入消息...'
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            className="px-4 sm:px-6 py-2.5 sm:py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium text-xs sm:text-sm cursor-pointer flex-shrink-0"
            disabled={!input.trim() || loading}
            onClick={handleSend}
          >
            {isResearchMode ? '▶ 研究' : '▶'}
          </button>
        </div>
        <p className="text-[10px] sm:text-xs text-gray-400 mt-1.5 sm:mt-2 text-center">
          {isResearchMode
            ? 'Agent 自动搜索→分析→撰写→审查→输出报告'
            : 'Enter 发送 · Shift+Enter 换行'}
        </p>
      </footer>
    </div>
  )
}

export default App
