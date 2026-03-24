import { useState, useRef } from 'react'
import axios from 'axios'
import ResultDisplay from '../components/ResultDisplay'

function AnalyzerPage() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('deep') // 评估模式：fast/deep
  const [generateReport, setGenerateReport] = useState(false) // 是否生成PDF报告
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    if (selectedFile) {
      setFile(selectedFile)
      setError(null)
      setResult(null)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setDragOver(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && (droppedFile.name.endsWith('.docx') || droppedFile.name.endsWith('.pdf'))) {
      setFile(droppedFile)
      setError(null)
      setResult(null)
    } else {
      setError('请上传 DOCX 或 PDF 格式的文件')
    }
  }

  const handleUpload = async () => {
    if (!file) {
      setError('请先选择文件')
      return
    }

    setLoading(true)
    setError(null)

    try {
      // 新流程：规则拆分 + 自动分析（不显示校准页面）
      const formData = new FormData()
      formData.append('file', file)
      formData.append('mode', mode)
      formData.append('generate_report', generateReport)

      const response = await axios.post('/api/analyze_auto', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setResult(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || '分析失败，请检查文件格式或网络连接')
      if (import.meta.env.DEV) console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
      {/* 页面标题 */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-[#2d5a3d] to-[#1a2e1f] shadow-xl mb-6">
          <span className="text-4xl">🧬</span>
        </div>
        <h1 className="text-4xl font-bold bg-gradient-to-r from-[#1a2e1f] to-[#1a2e1f] bg-clip-text text-transparent mb-4">
          生物试卷智能分析系统
        </h1>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          上传生物试卷（支持 DOCX 和 PDF 格式），AI 自动拆分并深度分析每道题目
        </p>
      </div>

      {/* 上传区域 */}
      <div className="max-w-2xl mx-auto">
        <div className="card p-8">
          {/* 拖拽上传区域 */}
          <div
            className={`upload-zone ${dragOver ? 'drag-over' : ''} mb-6`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx,.pdf"
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-[#c8f0d4] mb-4">
                <svg className="w-8 h-8 text-[#1a2e1f]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-lg font-medium text-gray-700 mb-2">
                拖拽文件到这里，或点击选择文件
              </p>
              <p className="text-sm text-gray-500">
                支持 DOCX、PDF 格式，最大 50MB
              </p>
            </div>
          </div>

          {/* 已选文件信息 */}
          {file && (
            <div className="mb-6 p-4 bg-gradient-to-r from-[#e8f8ee] to-[#e8f8ee] border border-[#b8d1bf] rounded-xl animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="w-10 h-10 rounded-lg bg-[#c8f0d4] flex items-center justify-center mr-3">
                    <span className="text-xl">{file.name.endsWith('.pdf') ? '📄' : '📝'}</span>
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{file.name}</p>
                    <p className="text-sm text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  className="text-gray-400 hover:text-red-500 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* PDF报告生成选项 */}
          <div className="mb-6">
            <label className={`
              flex items-center cursor-pointer p-4 border-2 rounded-xl transition-all
              ${generateReport
                ? 'border-[#2d5a3d] bg-[#e8f8ee]'
                : 'border-gray-200 hover:border-[#b8d1bf] bg-white'
              }
            `}>
              <input
                type="checkbox"
                checked={generateReport}
                onChange={(e) => setGenerateReport(e.target.checked)}
                className="h-5 w-5 text-[#1a2e1f] focus:ring-[#c8f0d4] rounded"
              />
              <div className="ml-4">
                <span className="font-medium text-gray-900">📄 生成PDF质量评估报告</span>
                <p className="text-sm text-gray-500 mt-1">
                  包含难度曲线、素养分布等6张可视化图表（+10秒）
                </p>
              </div>
            </label>
          </div>

          {/* 开始分析按钮 */}
          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full btn-primary py-4 text-lg"
          >
            {loading ? (
              <span className="flex items-center justify-center">
                <div className="loader mr-3" style={{ width: '24px', height: '24px', borderWidth: '3px' }}></div>
                分析中...
              </span>
            ) : (
              <span className="flex items-center justify-center">
                <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                开始分析
              </span>
            )}
          </button>

          {/* 加载状态 */}
          {loading && (
            <div className="mt-8 text-center animate-fade-in">
              <div className="inline-block">
                <div className="flex items-center justify-center space-x-2 mb-4">
                  <div className="w-3 h-3 bg-[#1a2e1f] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-3 h-3 bg-[#1a2e1f] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-3 h-3 bg-[#1a2e1f] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
              <p className="text-gray-600 font-medium">正在拆分并分析试卷...</p>
              <p className="text-sm text-gray-500 mt-2">
                {mode === 'deep' ? '深度模式预计需要 2-3 分钟' : '快速模式预计需要 1 分钟'}
              </p>
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl animate-fade-in">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="ml-3 text-red-800">{error}</p>
              </div>
            </div>
          )}
        </div>

        {/* 功能特点 */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="stat-card stat-card-blue">
            <div className="text-3xl mb-3">🎯</div>
            <h3 className="font-semibold text-gray-900 mb-2">智能拆分</h3>
            <p className="text-sm text-gray-600">自动识别题目边界，精准拆分选择题和非选择题</p>
          </div>
          <div className="stat-card stat-card-green">
            <div className="text-3xl mb-3">📈</div>
            <h3 className="font-semibold text-gray-900 mb-2">难度评估</h3>
            <p className="text-sm text-gray-600">多维度分析题目难度，生成难度曲线图</p>
          </div>
          <div className="stat-card stat-card-purple">
            <div className="text-3xl mb-3">🧠</div>
            <h3 className="font-semibold text-gray-900 mb-2">素养分析</h3>
            <p className="text-sm text-gray-600">评估生命观念、科学思维等核心素养覆盖</p>
          </div>
        </div>
      </div>

      {/* 结果展示 */}
      {result && (
        <div className="mt-12 animate-fade-in">
          <ResultDisplay data={result} />
        </div>
      )}
    </div>
  )
}

export default AnalyzerPage
