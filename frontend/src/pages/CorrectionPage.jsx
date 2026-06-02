import { useState, useEffect } from 'react'
import axios from 'axios'
import { useSearchParams } from 'react-router-dom'
import { Zap, Bot, AlertTriangle, Pencil, Link as LinkIcon, Scissors, Trash2, FileText, CheckCircle } from 'lucide-react'
import ResultDisplay from '../components/ResultDisplay'

function CorrectionPage() {
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session')

  const [questions, setQuestions] = useState([])
  const [confidence, setConfidence] = useState(0)
  const [warnings, setWarnings] = useState([])
  const [method, setMethod] = useState('')
  const [loading, setLoading] = useState(false)
  const [mode, setMode] = useState('deep')
  const [generateReport, setGenerateReport] = useState(false)
  const [result, setResult] = useState(null) // 新增：存储最终分析结果

  // 编辑状态
  const [editingId, setEditingId] = useState(null)
  const [editContent, setEditContent] = useState('')

  useEffect(() => {
    // 从session获取auto_split结果
    const fetchSplitResults = async () => {
      try {
        // 尝试从URL参数直接获取（兼容旧版）
        const questionsParam = searchParams.get('questions')
        if (questionsParam) {
          const parsedQuestions = JSON.parse(decodeURIComponent(questionsParam))
          setQuestions(parsedQuestions)
          setConfidence(parseFloat(searchParams.get('confidence') || 0))
          setWarnings(searchParams.get('warnings') ? JSON.parse(decodeURIComponent(searchParams.get('warnings'))) : [])
          setMethod(searchParams.get('method') || 'unknown')
          return
        }

        // 否则通过session_id从后端获取
        if (!sessionId) {
          alert('缺少session ID')
          return
        }

        const response = await axios.get(`/api/analyze/session/${sessionId}`)
        const data = response.data

        setQuestions(data.questions || [])
        setConfidence(data.confidence || 0)
        setWarnings(data.warnings || [])
        setMethod(data.method || 'unknown')
      } catch (e) {
        if (import.meta.env.DEV) console.error('Failed to fetch split results:', e)
        alert('加载拆分结果失败: ' + e.message)
      }
    }

    fetchSplitResults()
  }, [searchParams, sessionId])

  const handleEdit = (question) => {
    setEditingId(question.id)
    setEditContent(question.content)
  }

  const handleSaveEdit = (questionId) => {
    setQuestions(questions.map(q =>
      q.id === questionId ? { ...q, content: editContent } : q
    ))
    setEditingId(null)
    setEditContent('')
  }

  const handleCancelEdit = () => {
    setEditingId(null)
    setEditContent('')
  }

  const handleDelete = (questionId) => {
    if (window.confirm(`确定删除题目${questionId}吗？`)) {
      setQuestions(questions.filter(q => q.id !== questionId))
    }
  }

  const handleMerge = (questionId) => {
    const currentIndex = questions.findIndex(q => q.id === questionId)
    if (currentIndex < questions.length - 1) {
      const nextQuestion = questions[currentIndex + 1]
      const merged = {
        ...questions[currentIndex],
        content: questions[currentIndex].content + '\n\n' + nextQuestion.content
      }
      setQuestions(questions.filter((q, i) => i !== currentIndex + 1).map((q, i) =>
        i === currentIndex ? merged : q
      ))
    }
  }

  const handleSplit = (questionId) => {
    const question = questions.find(q => q.id === questionId)
    const splitPoint = prompt('输入拆分位置（字符数）：')
    if (splitPoint && !isNaN(parseInt(splitPoint))) {
      const pos = parseInt(splitPoint)
      const part1 = {
        ...question,
        content: question.content.substring(0, pos)
      }
      const part2 = {
        ...question,
        id: questions.length + 1,
        content: question.content.substring(pos)
      }
      const index = questions.findIndex(q => q.id === questionId)
      const newQuestions = [...questions]
      newQuestions.splice(index, 1, part1, part2)
      setQuestions(newQuestions)
    }
  }

  const handleConfirm = async () => {
    if (!sessionId) {
      alert('Session ID缺失')
      return
    }

    setLoading(true)

    try {
      const formData = new FormData()
      formData.append('session_id', sessionId)
      formData.append('corrected_questions', JSON.stringify(questions))
      formData.append('mode', mode)
      formData.append('generate_report', generateReport)

      const response = await axios.post('/api/analyze/confirm_split', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })

      // 保存结果并显示在当前页面
      if (import.meta.env.DEV) {
        console.log('=== 收到后端返回数据 ===')
        console.log('response.data:', response.data)
        console.log('questions数量:', response.data?.questions?.length)
        console.log('total_count:', response.data?.total_count)
      }
      setResult(response.data)
      // 滚动到页面顶部查看结果
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      alert(`确认失败: ${err.response?.data?.detail || err.message}`)
      if (import.meta.env.DEV) console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const getConfidenceColor = (conf) => {
    if (conf >= 0.9) return 'text-green-600'
    if (conf >= 0.7) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getConfidenceBadge = (conf) => {
    if (conf >= 0.9) return 'bg-green-100 text-green-800'
    if (conf >= 0.7) return 'bg-yellow-100 text-yellow-800'
    return 'bg-red-100 text-red-800'
  }

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      {/* 头部 */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-4">
          人工校准题目拆分结果
        </h1>
        <div className="bg-white shadow rounded-lg p-6">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <span className="text-sm text-gray-600">拆分方式</span>
              <p className="text-lg font-medium">
                {method === 'rule' ? <span className="flex items-center gap-1"><Zap size={16} className="inline" /> 规则引擎</span> : method === 'llm' ? <span className="flex items-center gap-1"><Bot size={16} className="inline" /> LLM</span> : <span className="flex items-center gap-1"><AlertTriangle size={16} className="inline" /> LLM降级</span>}
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">整体置信度</span>
              <p className={`text-lg font-medium ${getConfidenceColor(confidence)}`}>
                {(confidence * 100).toFixed(0)}%
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">题目数量</span>
              <p className="text-lg font-medium">{questions.length} 道</p>
            </div>
          </div>

          {/* 警告信息 */}
          {warnings.length > 0 && (
            <div className="mt-4 p-4 bg-yellow-50 border border-yellow-200 rounded">
              <p className="text-sm font-medium text-yellow-800 mb-2 flex items-center gap-1"><AlertTriangle size={14} className="inline" /> 警告信息：</p>
              <ul className="list-disc list-inside text-sm text-yellow-700">
                {warnings.map((warning, idx) => (
                  <li key={idx}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* 题目列表 */}
      <div className="space-y-4 mb-8">
        {questions.map((question, index) => (
          <div key={question.id} className="bg-white shadow rounded-lg p-6 border-l-4 border-[#2d5a3d]">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center space-x-3">
                <span className="text-2xl font-bold text-[#1a2e1f]">题目 {question.id}</span>
                {question.confidence && (
                  <span className={`px-2 py-1 rounded text-xs font-medium ${getConfidenceBadge(question.confidence)}`}>
                    置信度 {(question.confidence * 100).toFixed(0)}%
                  </span>
                )}
                {question.has_options && (
                  <span className="px-2 py-1 bg-[#c8f0d4] text-[#0a120c] rounded text-xs font-medium">
                    选择题
                  </span>
                )}
                {question.cross_page && (
                  <span className="px-2 py-1 bg-orange-100 text-orange-800 rounded text-xs font-medium">
                    跨页
                  </span>
                )}
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={() => handleEdit(question)}
                  className="px-3 py-1 bg-[#c8f0d4] text-[#0f1c13] rounded hover:bg-[#b8d1bf] text-sm"
                >
                  <Pencil size={14} className="inline mr-1" /> 编辑
                </button>
                <button
                  onClick={() => handleMerge(question.id)}
                  className="px-3 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200 text-sm"
                  disabled={index === questions.length - 1}
                >
                  <LinkIcon size={14} className="inline mr-1" /> 合并下一题
                </button>
                <button
                  onClick={() => handleSplit(question.id)}
                  className="px-3 py-1 bg-yellow-100 text-yellow-700 rounded hover:bg-yellow-200 text-sm"
                >
                  <Scissors size={14} className="inline mr-1" /> 拆分
                </button>
                <button
                  onClick={() => handleDelete(question.id)}
                  className="px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200 text-sm"
                >
                  <Trash2 size={14} className="inline mr-1" /> 删除
                </button>
              </div>
            </div>

            {/* 题目内容 */}
            {editingId === question.id ? (
              <div>
                <textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="w-full p-3 border border-gray-300 rounded-lg font-mono text-sm"
                  rows={10}
                />
                <div className="mt-3 flex space-x-2">
                  <button
                    onClick={() => handleSaveEdit(question.id)}
                    className="px-4 py-2 bg-[#1a2e1f] text-white rounded hover:bg-[#0f1c13]"
                  >
                    保存
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="px-4 py-2 bg-gray-300 text-gray-700 rounded hover:bg-gray-400"
                  >
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <div className="prose max-w-none">
                {/* 题目文本（v3.0：图表不再前端展示，已发送给AI分析） */}
                <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800 bg-gray-50 p-4 rounded">
                  {question.content}
                </pre>
              </div>
            )}

            {/* 警告信息 */}
            {question.warnings && question.warnings.length > 0 && (
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded">
                <p className="text-xs font-medium text-yellow-800 mb-1 flex items-center gap-1"><AlertTriangle size={12} className="inline" /> 该题警告：</p>
                <ul className="list-disc list-inside text-xs text-yellow-700">
                  {question.warnings.map((warning, idx) => (
                    <li key={idx}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 底部操作栏 */}
      <div className="bg-white shadow rounded-lg p-6 sticky bottom-4">
        <div className="flex items-center justify-between">
          <div className="flex space-x-6">
            {/* 评估模式 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                评估模式
              </label>
              <div className="flex space-x-3">
                <label className="flex items-center cursor-pointer">
                  <input
                    type="radio"
                    name="mode"
                    value="deep"
                    checked={mode === 'deep'}
                    onChange={() => setMode('deep')}
                    className="h-4 w-4 text-[#1a2e1f]"
                  />
                  <span className="ml-2 text-sm">深度模式</span>
                </label>
              </div>
            </div>

            {/* PDF报告 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                生成报告
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={generateReport}
                  onChange={(e) => setGenerateReport(e.target.checked)}
                  className="h-4 w-4 text-[#1a2e1f] rounded"
                />
                <span className="ml-2 text-sm flex items-center"><FileText size={14} className="inline mr-1" /> 生成PDF报告</span>
              </label>
            </div>
          </div>

          {/* 确认按钮 */}
          <button
            onClick={handleConfirm}
            disabled={loading || questions.length === 0}
            className="px-8 py-3 bg-[#1a2e1f] text-white rounded-lg hover:bg-[#0f1c13] disabled:bg-gray-300 disabled:cursor-not-allowed font-medium text-lg"
          >
            {loading ? '分析中...' : <span className="flex items-center justify-center gap-1"><CheckCircle size={16} className="inline" /> 确认并继续分析</span>}
          </button>
        </div>

        {loading && (
          <div className="mt-4 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[#1a2e1f]"></div>
            <p className="mt-2 text-sm text-gray-600">
              正在进行深度分析，请稍候...
              {mode === 'fast' && <span className="block text-xs mt-1">预计需要 75 秒</span>}
              {mode === 'deep' && <span className="block text-xs mt-1">预计需要 150 秒</span>}
            </p>
          </div>
        )}
      </div>

      {/* 分析结果展示区域 */}
      {result && (
        <div className="mt-12">
          <ResultDisplay data={result} />
        </div>
      )}
    </div>
  )
}

export default CorrectionPage
