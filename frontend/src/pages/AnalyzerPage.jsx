import { useState } from 'react'
import axios from 'axios'
import ResultDisplay from '../components/ResultDisplay'

function AnalyzerPage() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('fast') // 评估模式：fast/deep
  const [generateReport, setGenerateReport] = useState(false) // 是否生成PDF报告

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    setFile(selectedFile)
    setError(null)
    setResult(null)
  }

  const handleUpload = async () => {
    if (!file) {
      setError('请先选择文件')
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    formData.append('mode', mode) // 添加模式参数
    formData.append('generate_report', generateReport) // 添加报告生成参数

    setLoading(true)
    setError(null)

    try {
      const response = await axios.post('/api/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setResult(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || '分析失败，请检查文件格式或网络连接')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          生物试卷智能分析系统
        </h1>
        <p className="text-lg text-gray-600">
          上传PDF或Word格式的生物试卷，AI自动拆分并深度分析每道题目
        </p>
      </div>

      {/* 上传区域 */}
      <div className="max-w-2xl mx-auto">
        <div className="bg-white shadow rounded-lg p-8">
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              选择试卷文件（PDF/DOCX）
            </label>
            <input
              type="file"
              accept=".pdf,.docx"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 focus:outline-none p-2.5"
            />
          </div>

          {file && (
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded">
              <p className="text-sm text-blue-800">
                已选择: <span className="font-medium">{file.name}</span>
                <span className="ml-2 text-gray-600">
                  ({(file.size / 1024 / 1024).toFixed(2)} MB)
                </span>
              </p>
            </div>
          )}

          {/* 评估模式选择 */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-3">
              评估模式
            </label>
            <div className="space-y-3">
              <div
                onClick={() => setMode('fast')}
                className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${
                  mode === 'fast'
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <input
                      type="radio"
                      name="mode"
                      value="fast"
                      checked={mode === 'fast'}
                      onChange={() => setMode('fast')}
                      className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                    />
                    <div className="ml-3">
                      <span className="font-medium text-gray-900">🚄 快速模式</span>
                      <p className="text-sm text-gray-600 mt-1">
                        仅规则引擎评估难度，预估耗时 ~75秒
                      </p>
                    </div>
                  </div>
                  <span className="text-xs text-green-600 font-medium">推荐</span>
                </div>
              </div>

              <div
                onClick={() => setMode('deep')}
                className={`p-4 border-2 rounded-lg cursor-pointer transition-all ${
                  mode === 'deep'
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 hover:border-blue-300'
                }`}
              >
                <div className="flex items-center">
                  <input
                    type="radio"
                    name="mode"
                    value="deep"
                    checked={mode === 'deep'}
                    onChange={() => setMode('deep')}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                  />
                  <div className="ml-3">
                    <span className="font-medium text-gray-900">🔬 深度模式</span>
                    <p className="text-sm text-gray-600 mt-1">
                      规则引擎 + AI精调，识别隐性条件，预估耗时 ~150秒
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* PDF报告生成选项 */}
          <div className="mb-6">
            <label className="flex items-center cursor-pointer p-4 border-2 border-gray-200 rounded-lg hover:border-blue-300 transition-all">
              <input
                type="checkbox"
                checked={generateReport}
                onChange={(e) => setGenerateReport(e.target.checked)}
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 rounded"
              />
              <div className="ml-3">
                <span className="font-medium text-gray-900">📄 生成PDF质量评估报告</span>
                <p className="text-sm text-gray-600 mt-1">
                  包含难度曲线、素养分布等6张可视化图表（+10秒）
                </p>
              </div>
            </label>
          </div>

          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full bg-blue-600 text-white py-3 px-4 rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors font-medium"
          >
            {loading ? '分析中...' : '开始分析'}
          </button>

          {loading && (
            <div className="mt-6 text-center">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p className="mt-4 text-gray-600">
                正在处理试卷，请稍候...
                {mode === 'fast' && <span className="block text-sm mt-1">预计需要 75 秒</span>}
                {mode === 'deep' && <span className="block text-sm mt-1">预计需要 150 秒</span>}
              </p>
            </div>
          )}

          {error && (
            <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}
        </div>
      </div>

      {/* 结果展示 */}
      {result && <ResultDisplay data={result} />}
    </div>
  )
}

export default AnalyzerPage
