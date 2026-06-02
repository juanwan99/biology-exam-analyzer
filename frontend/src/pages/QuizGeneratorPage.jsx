import { useState, useEffect } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'

const QUIZ_HISTORY_KEY = 'quiz_history'
const MAX_HISTORY_COUNT = 10

function QuizGeneratorPage() {
  // 教材列表
  const [books, setBooks] = useState([])
  const [loadingBooks, setLoadingBooks] = useState(true)

  // 选择的教材（多选下拉）
  const [selectedBooks, setSelectedBooks] = useState([])

  // 配置参数
  const [config, setConfig] = useState({
    single_choice: 10,
    multiple_choice: 5,
    fill_blank: 3,
    short_answer: 2,
    difficulty: 'medium',
    use_ai_generation: false
  })

  // 生成状态
  const [generating, setGenerating] = useState(false)
  const [generatedQuiz, setGeneratedQuiz] = useState(null)
  const [error, setError] = useState(null)

  // 教材选择下拉框是否展开
  const [showBookDropdown, setShowBookDropdown] = useState(false)

  // 历史记录
  const [quizHistory, setQuizHistory] = useState([])
  const [showHistory, setShowHistory] = useState(false)

  // 加载教材列表和历史记录
  useEffect(() => {
    loadBooks()
    loadQuizHistory()
  }, [])

  const loadBooks = async () => {
    try {
      setLoadingBooks(true)
      const res = await axios.get('/api/textbook/books')
      if (res.data.success) {
        setBooks(res.data.data || [])
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载教材列表失败:', err)
      setError('加载教材列表失败')
    } finally {
      setLoadingBooks(false)
    }
  }

  // 加载历史记录
  const loadQuizHistory = () => {
    try {
      const saved = localStorage.getItem(QUIZ_HISTORY_KEY)
      if (saved) {
        setQuizHistory(JSON.parse(saved))
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载历史记录失败:', err)
    }
  }

  // 保存测验到历史记录
  const saveQuizToHistory = (quiz) => {
    try {
      const newHistory = [quiz, ...quizHistory].slice(0, MAX_HISTORY_COUNT)
      setQuizHistory(newHistory)
      localStorage.setItem(QUIZ_HISTORY_KEY, JSON.stringify(newHistory))
    } catch (err) {
      if (import.meta.env.DEV) console.error('保存历史记录失败:', err)
    }
  }

  // 从历史记录加载测验
  const loadQuizFromHistory = (quiz) => {
    setGeneratedQuiz(quiz)
    setShowHistory(false)
  }

  // 删除历史记录
  const deleteFromHistory = (index) => {
    const newHistory = quizHistory.filter((_, i) => i !== index)
    setQuizHistory(newHistory)
    localStorage.setItem(QUIZ_HISTORY_KEY, JSON.stringify(newHistory))
  }

  // 清空所有历史记录
  const clearAllHistory = () => {
    setQuizHistory([])
    localStorage.removeItem(QUIZ_HISTORY_KEY)
  }

  // 切换教材选择
  const toggleBook = (bookId) => {
    setSelectedBooks(prev =>
      prev.includes(bookId)
        ? prev.filter(id => id !== bookId)
        : [...prev, bookId]
    )
    // 选择后自动收起下拉框
    setShowBookDropdown(false)
  }

  // 获取选中教材的名称
  const getSelectedBookNames = () => {
    if (selectedBooks.length === 0) return '请选择教材'
    const names = selectedBooks.map(id => {
      const book = books.find(b => b.book_id === id)
      return book ? book.book_name.replace('生物学', '') : id
    })
    return names.join('、')
  }

  // 计算总题数
  const getTotalQuestions = () => {
    return config.single_choice + config.multiple_choice + config.fill_blank + config.short_answer
  }

  // 生成测验
  const generateQuiz = async () => {
    if (selectedBooks.length === 0) {
      setError('请至少选择一本教材')
      return
    }

    const totalQuestions = getTotalQuestions()
    if (totalQuestions === 0) {
      setError('请至少设置一种题型的数量')
      return
    }

    try {
      setGenerating(true)
      setError(null)

      const res = await axios.post('/api/quiz/generate', {
        book_ids: selectedBooks,
        question_types: {
          single_choice: config.single_choice,
          multiple_choice: config.multiple_choice,
          fill_blank: config.fill_blank,
          short_answer: config.short_answer
        },
        difficulty: config.difficulty,
        use_ai_generation: config.use_ai_generation
      })

      if (res.data.success) {
        const quiz = res.data.data
        setGeneratedQuiz(quiz)
        // 保存到历史记录
        saveQuizToHistory(quiz)
      } else {
        setError(res.data.message || '生成测验失败')
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('生成测验失败:', err)
      setError(err.response?.data?.detail || '生成测验失败，请稍后重试')
    } finally {
      setGenerating(false)
    }
  }

  // 导出测验
  const exportQuiz = () => {
    if (!generatedQuiz) return

    const content = formatQuizForExport(generatedQuiz)
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `测验_${new Date().toISOString().split('T')[0]}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  // 格式化测验用于导出
  const formatQuizForExport = (quiz) => {
    let content = `生物学测验\n生成时间: ${new Date().toLocaleString('zh-CN')}\n\n`
    content += `教材范围: ${quiz.metadata?.books?.join('、') || '未指定'}\n`
    content += `题目总数: ${quiz.questions?.length || 0}\n`
    content += `难度: ${quiz.metadata?.difficulty || '未指定'}\n`
    content += `\n${'='.repeat(60)}\n\n`

    quiz.questions?.forEach((q, idx) => {
      content += `${idx + 1}. [${q.question_type}] ${q.content}\n`

      if (q.options) {
        Object.entries(q.options).forEach(([key, value]) => {
          content += `   ${key}. ${value}\n`
        })
      }

      content += `\n答案: ${q.answer}\n`
      if (q.explanation) {
        content += `解析: ${q.explanation}\n`
      }
      content += `\n${'-'.repeat(60)}\n\n`
    })

    return content
  }

  // 渲染题目内容
  const renderQuestionContent = (content) => {
    if (!content) return null
    // 确保 content 是字符串，ReactMarkdown 只接受字符串
    const textContent = typeof content === 'string'
      ? content
      : (typeof content === 'object' ? JSON.stringify(content) : String(content))
    // react-markdown v10+ 不再支持 className prop，需要用外层 div 包裹
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown>{textContent}</ReactMarkdown>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 py-6">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* 标题 */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">智能测验生成器</h1>
          <p className="mt-1 text-sm text-gray-600">基于教材内容和向量检索，智能生成个性化测验</p>
        </div>

        {error && (
          <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* 左侧配置面板 */}
          <div className="lg:col-span-1 space-y-3">
            {/* 教材选择 - 多选下拉框 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  教材范围 <span className="text-red-500">*</span>
                </label>
                <div className="relative flex-1">
                  <button
                    type="button"
                    onClick={() => setShowBookDropdown(!showBookDropdown)}
                    className="w-full px-2 py-1.5 text-left bg-white border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                  >
                    <span className={selectedBooks.length === 0 ? 'text-gray-400' : 'text-gray-900'}>
                      {getSelectedBookNames()}
                    </span>
                    <svg className="absolute right-2 top-2 h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {showBookDropdown && (
                    <div className="absolute z-10 mt-1 w-full bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-auto">
                      {loadingBooks ? (
                        <div className="px-3 py-2 text-sm text-gray-500">加载中...</div>
                      ) : (
                        books.map(book => (
                          <label
                            key={book.book_id}
                            className="flex items-center px-3 py-2 hover:bg-gray-50 cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              checked={selectedBooks.includes(book.book_id)}
                              onChange={() => toggleBook(book.book_id)}
                              className="mr-2 h-4 w-4 text-[#1a2e1f] rounded"
                            />
                            <div className="flex-1 text-sm">
                              <div className="text-gray-900">{book.book_name}</div>
                              <div className="text-xs text-gray-500">{book.chunk_count} 个切片</div>
                            </div>
                          </label>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </div>
              {selectedBooks.length > 0 && (
                <div className="mt-1 text-xs text-gray-500 text-right">
                  已选 {selectedBooks.length} 本
                </div>
              )}
            </div>

            {/* 单选题数量 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  单选题
                </label>
                <select
                  value={config.single_choice}
                  onChange={(e) => setConfig(prev => ({ ...prev, single_choice: parseInt(e.target.value) }))}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                >
                  {[0, 5, 10, 15, 20, 25, 30].map(num => (
                    <option key={num} value={num}>{num} 题</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 多选题数量 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  多选题
                </label>
                <select
                  value={config.multiple_choice}
                  onChange={(e) => setConfig(prev => ({ ...prev, multiple_choice: parseInt(e.target.value) }))}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                >
                  {[0, 3, 5, 8, 10, 15, 20].map(num => (
                    <option key={num} value={num}>{num} 题</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 填空题数量 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  填空题
                </label>
                <select
                  value={config.fill_blank}
                  onChange={(e) => setConfig(prev => ({ ...prev, fill_blank: parseInt(e.target.value) }))}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                >
                  {[0, 2, 3, 5, 8, 10].map(num => (
                    <option key={num} value={num}>{num} 题</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 简答题数量 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  简答题
                </label>
                <select
                  value={config.short_answer}
                  onChange={(e) => setConfig(prev => ({ ...prev, short_answer: parseInt(e.target.value) }))}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                >
                  {[0, 1, 2, 3, 5, 8].map(num => (
                    <option key={num} value={num}>{num} 题</option>
                  ))}
                </select>
              </div>
            </div>

            {/* 难度选择 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  难度
                </label>
                <select
                  value={config.difficulty}
                  onChange={(e) => setConfig(prev => ({ ...prev, difficulty: e.target.value }))}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                >
                  <option value="easy">简单</option>
                  <option value="medium">中等</option>
                  <option value="hard">困难</option>
                  <option value="mixed">混合</option>
                </select>
              </div>
            </div>

            {/* AI生成 */}
            <div className="bg-white rounded-lg shadow p-3">
              <div className="flex items-center gap-3">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">
                  AI生成
                </label>
                <select
                  value={config.use_ai_generation ? 'yes' : 'no'}
                  onChange={(e) => setConfig(prev => ({ ...prev, use_ai_generation: e.target.value === 'yes' }))}
                  className="flex-1 px-2 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-[#c8f0d4] focus:border-[#2d5a3d] text-sm"
                >
                  <option value="no">关闭</option>
                  <option value="yes">开启</option>
                </select>
              </div>
            </div>

            {/* 总题数和生成按钮 */}
            <div className="bg-[#e8f8ee] border border-[#b8d1bf] rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">总题数</span>
                <span className="text-2xl font-bold text-[#1a2e1f]">{getTotalQuestions()}</span>
              </div>
              <button
                onClick={generateQuiz}
                disabled={generating || selectedBooks.length === 0 || getTotalQuestions() === 0}
                className="w-full bg-[#1a2e1f] text-white py-2 px-4 rounded-lg font-medium text-sm hover:bg-[#0f1c13] disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                {generating ? (
                  <span className="flex items-center justify-center">
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    生成中...
                  </span>
                ) : (
                  '生成测验'
                )}
              </button>
            </div>

            {/* 历史记录按钮 */}
            {quizHistory.length > 0 && (
              <div className="bg-white rounded-lg shadow p-3">
                <button
                  onClick={() => setShowHistory(!showHistory)}
                  className="w-full flex items-center justify-between text-sm text-gray-700 hover:text-[#1a2e1f]"
                >
                  <span className="flex items-center">
                    <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    历史记录
                  </span>
                  <span className="bg-gray-100 px-2 py-0.5 rounded text-xs">{quizHistory.length}</span>
                </button>

                {showHistory && (
                  <div className="mt-3 space-y-2 border-t pt-3">
                    {quizHistory.map((quiz, index) => (
                      <div
                        key={index}
                        className="flex items-center justify-between p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer group"
                      >
                        <div
                          className="flex-1 min-w-0"
                          onClick={() => loadQuizFromHistory(quiz)}
                        >
                          <div className="text-xs text-gray-900 truncate">
                            {quiz.metadata?.books?.join('、') || '未知教材'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {quiz.questions?.length || 0}题 · {new Date(quiz.metadata?.generated_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric' })}
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteFromHistory(index)
                          }}
                          className="ml-2 p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                          title="删除"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                    <button
                      onClick={clearAllHistory}
                      className="w-full text-xs text-red-500 hover:text-red-700 py-1"
                    >
                      清空所有历史
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 右侧测验预览 */}
          <div className="lg:col-span-3">
            {!generatedQuiz ? (
              <div className="bg-white rounded-lg shadow p-12 text-center">
                <svg className="mx-auto h-16 w-16 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <h3 className="mt-4 text-lg font-medium text-gray-900">暂无测验</h3>
                <p className="mt-2 text-sm text-gray-500">配置参数后点击"生成测验"开始</p>
              </div>
            ) : (
              <div className="bg-white rounded-lg shadow">
                {/* 测验头部 */}
                <div className="border-b border-gray-200 px-6 py-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h2 className="text-xl font-bold text-gray-900">生物学测验</h2>
                      <div className="mt-1 flex items-center space-x-3 text-xs text-gray-500">
                        <span>共 {generatedQuiz.questions?.length || 0} 题</span>
                        <span>•</span>
                        <span>{generatedQuiz.metadata?.books?.join('、')}</span>
                        <span>•</span>
                        <span>{new Date(generatedQuiz.metadata?.generated_at).toLocaleString('zh-CN')}</span>
                      </div>
                    </div>
                    <button
                      onClick={exportQuiz}
                      className="px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700 transition-colors"
                    >
                      导出
                    </button>
                  </div>
                </div>

                {/* 题目列表 */}
                <div className="divide-y divide-gray-200 max-h-[calc(100vh-200px)] overflow-y-auto">
                  {generatedQuiz.questions?.map((question, idx) => (
                    <div key={idx} className="p-4">
                      <div className="flex items-start">
                        <div className="flex-shrink-0 w-8 h-8 flex items-center justify-center bg-[#c8f0d4] text-[#1a2e1f] rounded font-semibold text-sm">
                          {idx + 1}
                        </div>
                        <div className="ml-3 flex-1">
                          <div className="flex items-center mb-2">
                            <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-gray-100 text-gray-700">
                              {question.question_type}
                            </span>
                            {question.difficulty_level && (
                              <span className={`ml-2 inline-block px-2 py-0.5 text-xs font-medium rounded ${
                                question.difficulty_level > 0.7 ? 'bg-red-100 text-red-700' :
                                question.difficulty_level > 0.4 ? 'bg-yellow-100 text-yellow-700' :
                                'bg-green-100 text-green-700'
                              }`}>
                                难度 {(question.difficulty_level * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>

                          <div className="text-sm text-gray-900 mb-2">
                            {renderQuestionContent(question.content)}
                          </div>

                          {question.options && (
                            <div className="space-y-1 mb-2">
                              {Object.entries(question.options).map(([key, value]) => (
                                <div key={key} className="flex items-start text-sm text-gray-700">
                                  <span className="font-medium mr-2">{key}.</span>
                                  <span>{value}</span>
                                </div>
                              ))}
                            </div>
                          )}

                          <div className="mt-3 p-3 bg-green-50 rounded text-sm">
                            <div className="flex items-start">
                              <span className="font-medium text-green-700 mr-2">答案:</span>
                              <span className="text-green-700">
                                {typeof question.answer === 'string'
                                  ? question.answer
                                  : JSON.stringify(question.answer)}
                              </span>
                            </div>
                            {question.explanation && (
                              <div className="mt-1 flex items-start">
                                <span className="font-medium text-green-700 mr-2">解析:</span>
                                <div className="text-green-700 flex-1">
                                  {renderQuestionContent(question.explanation)}
                                </div>
                              </div>
                            )}
                          </div>

                          {question.source && (
                            <div className="mt-2 text-xs text-gray-500">
                              来源: {question.source}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default QuizGeneratorPage
