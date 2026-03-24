import { useState, useEffect, useCallback } from 'react'
import { ClipboardList, Upload, BarChart3, FileText } from 'lucide-react'
import apiClient from '../api/axios'

function HistoryDataPage() {
  // 状态管理
  const [historyList, setHistoryList] = useState([])
  const [selectedHistory, setSelectedHistory] = useState(null)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [activeTab, setActiveTab] = useState('list') // list, upload, stats

  // 筛选
  const [gradeFilter, setGradeFilter] = useState('')

  // 上传表单
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadForm, setUploadForm] = useState({
    name: '',
    grade: '高三',
    examDate: '',
    studentCount: '',
    totalScore: '100',
  })
  const [parsedQuestions, setParsedQuestions] = useState([])
  const [questionScores, setQuestionScores] = useState([])
  const [uploadStep, setUploadStep] = useState(1) // 1:上传文件 2:填写分数 3:确认提交

  // 加载历史数据列表
  const loadHistoryList = useCallback(async () => {
    try {
      setLoading(true)
      const params = gradeFilter ? { grade: gradeFilter } : {}
      const res = await apiClient.get('/api/prediction/history', { params })
      if (res.data.success) {
        setHistoryList(res.data.data)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载历史数据失败:', err)
      setMessage({ type: 'error', text: '加载历史数据失败' })
    } finally {
      setLoading(false)
    }
  }, [gradeFilter])

  // 加载统计数据
  const loadStats = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/prediction/stats')
      if (res.data.success) {
        setStats(res.data.data)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载统计数据失败:', err)
    }
  }, [])

  // 初始化加载
  useEffect(() => {
    loadHistoryList()
    loadStats()
  }, [loadHistoryList, loadStats])

  // 查看历史详情
  const handleViewHistory = async (id) => {
    try {
      setLoading(true)
      const res = await apiClient.get(`/api/prediction/history/${id}`)
      if (res.data.success) {
        setSelectedHistory(res.data.data)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载详情失败:', err)
      setMessage({ type: 'error', text: '加载详情失败' })
    } finally {
      setLoading(false)
    }
  }

  // 删除历史记录
  const handleDeleteHistory = async (id) => {
    if (!window.confirm('确定要删除这条历史记录吗？删除后映射模型将自动更新。')) {
      return
    }
    try {
      setLoading(true)
      const res = await apiClient.delete(`/api/prediction/history/${id}`)
      if (res.data.success) {
        setMessage({ type: 'success', text: '删除成功' })
        loadHistoryList()
        setSelectedHistory(null)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('删除失败:', err)
      setMessage({ type: 'error', text: '删除失败' })
    } finally {
      setLoading(false)
    }
  }

  // 上传文件并解析
  const handleFileUpload = async () => {
    if (!uploadFile) {
      setMessage({ type: 'error', text: '请先选择文件' })
      return
    }

    try {
      setLoading(true)
      const formData = new FormData()
      formData.append('file', uploadFile)

      // 使用自动拆分接口解析题目
      const res = await apiClient.post('/api/analyze/auto_split', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000
      })

      if (res.data.questions) {
        setParsedQuestions(res.data.questions)
        // 初始化每题分数
        setQuestionScores(res.data.questions.map((q, idx) => ({
          question_number: idx + 1,
          question_score: q.total_score || 0,
          actual_average: 0,
          question_content: q.content?.substring(0, 100) || '',
          knowledge_points: [],
          question_type: q.question_type || 'unknown'
        })))
        setUploadStep(2)
        setMessage({ type: 'success', text: `成功解析 ${res.data.questions.length} 道题目` })
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('文件解析失败:', err)
      setMessage({ type: 'error', text: '文件解析失败: ' + (err.response?.data?.detail || err.message) })
    } finally {
      setLoading(false)
    }
  }

  // 更新单题分数
  const handleScoreChange = (index, field, value) => {
    const newScores = [...questionScores]
    newScores[index][field] = parseFloat(value) || 0
    setQuestionScores(newScores)
  }

  // 提交历史数据
  const handleSubmitHistory = async () => {
    // 验证
    if (!uploadForm.name.trim()) {
      setMessage({ type: 'error', text: '请填写考试名称' })
      return
    }
    if (!uploadForm.totalScore || parseFloat(uploadForm.totalScore) <= 0) {
      setMessage({ type: 'error', text: '请填写有效的试卷总分' })
      return
    }

    // 检查是否所有题目都填写了分数
    const hasEmptyScores = questionScores.some(q => q.question_score <= 0 || q.actual_average < 0)
    if (hasEmptyScores) {
      if (!window.confirm('部分题目的分数未填写完整，确定要提交吗？')) {
        return
      }
    }

    try {
      setLoading(true)
      const payload = {
        name: uploadForm.name,
        grade: uploadForm.grade,
        total_score: parseFloat(uploadForm.totalScore),
        questions: questionScores,
        exam_date: uploadForm.examDate || null,
        student_count: uploadForm.studentCount ? parseInt(uploadForm.studentCount) : null
      }

      const res = await apiClient.post('/api/prediction/history', payload)
      if (res.data.success) {
        setMessage({ type: 'success', text: '历史数据上传成功，映射模型已更新' })
        // 重置表单
        setUploadStep(1)
        setUploadFile(null)
        setParsedQuestions([])
        setQuestionScores([])
        setUploadForm({
          name: '',
          grade: '高三',
          examDate: '',
          studentCount: '',
          totalScore: '100',
        })
        // 刷新列表
        loadHistoryList()
        loadStats()
        setActiveTab('list')
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('提交失败:', err)
      setMessage({ type: 'error', text: '提交失败: ' + (err.response?.data?.detail || err.message) })
    } finally {
      setLoading(false)
    }
  }

  // 渲染历史列表
  const renderHistoryList = () => (
    <div className="space-y-4">
      {/* 筛选器 */}
      <div className="flex items-center space-x-4">
        <label className="text-sm font-medium text-gray-700">年级筛选:</label>
        <select
          value={gradeFilter}
          onChange={(e) => setGradeFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#c8f0d4]"
        >
          <option value="">全部</option>
          <option value="高一">高一</option>
          <option value="高二">高二</option>
          <option value="高三">高三</option>
        </select>
      </div>

      {/* 列表 */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">考试名称</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">年级</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">考试日期</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">平均分</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">得分率</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {historyList.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-6 py-8 text-center text-gray-500">
                  暂无历史数据，请先上传历史试卷
                </td>
              </tr>
            ) : (
              historyList.map((item) => (
                <tr key={item.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{item.name}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{item.grade}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{item.exam_date || '-'}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {item.average_score?.toFixed(1) || '-'} / {item.total_score}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    {item.score_rate ? `${(item.score_rate * 100).toFixed(1)}%` : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <button
                      onClick={() => handleViewHistory(item.id)}
                      className="text-[#1a2e1f] hover:text-[#0a120c] mr-3"
                    >
                      查看
                    </button>
                    <button
                      onClick={() => handleDeleteHistory(item.id)}
                      className="text-red-600 hover:text-red-800"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 详情弹窗 */}
      {selectedHistory && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-4xl w-full max-h-[80vh] overflow-auto m-4">
            <div className="p-6 border-b border-gray-200 flex justify-between items-center">
              <h3 className="text-lg font-semibold">{selectedHistory.name}</h3>
              <button
                onClick={() => setSelectedHistory(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-gray-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-500">年级</div>
                  <div className="font-semibold">{selectedHistory.grade}</div>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-500">考试日期</div>
                  <div className="font-semibold">{selectedHistory.exam_date || '-'}</div>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-500">平均分</div>
                  <div className="font-semibold">{selectedHistory.average_score?.toFixed(1)} / {selectedHistory.total_score}</div>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <div className="text-sm text-gray-500">平均难度</div>
                  <div className="font-semibold">{selectedHistory.difficulty_avg?.toFixed(1) || '-'}</div>
                </div>
              </div>

              <h4 className="font-semibold mb-3">题目详情</h4>
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">题号</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">满分</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">平均分</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">得分率</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">绝对难度</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {selectedHistory.questions?.map((q) => (
                    <tr key={q.id}>
                      <td className="px-4 py-2 text-sm">{q.question_number}</td>
                      <td className="px-4 py-2 text-sm">{q.question_score}</td>
                      <td className="px-4 py-2 text-sm">{q.actual_average?.toFixed(2)}</td>
                      <td className="px-4 py-2 text-sm">{q.score_rate ? `${(q.score_rate * 100).toFixed(1)}%` : '-'}</td>
                      <td className="px-4 py-2 text-sm">{q.absolute_difficulty?.toFixed(1) || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )

  // 渲染上传表单
  const renderUploadForm = () => (
    <div className="space-y-6">
      {/* 步骤指示器 */}
      <div className="flex items-center justify-center space-x-4 mb-8">
        {[1, 2, 3].map((step) => (
          <div key={step} className="flex items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
              uploadStep >= step ? 'bg-[#1a2e1f] text-white' : 'bg-gray-200 text-gray-600'
            }`}>
              {step}
            </div>
            {step < 3 && <div className={`w-12 h-1 ${uploadStep > step ? 'bg-[#1a2e1f]' : 'bg-gray-200'}`} />}
          </div>
        ))}
      </div>

      {/* 步骤1: 上传文件 */}
      {uploadStep === 1 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-lg font-semibold mb-4">步骤1: 上传试卷文件</h3>

          <div className="space-y-4">
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
              <input
                type="file"
                accept=".docx"
                onChange={(e) => setUploadFile(e.target.files[0])}
                className="hidden"
                id="file-upload"
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                <div className="text-4xl mb-2 flex justify-center"><FileText size={36} className="text-gray-400" /></div>
                <p className="text-gray-600">点击选择 DOCX 文件</p>
                {uploadFile && (
                  <p className="mt-2 text-[#1a2e1f] font-medium">{uploadFile.name}</p>
                )}
              </label>
            </div>

            <button
              onClick={handleFileUpload}
              disabled={!uploadFile || loading}
              className="w-full py-3 bg-[#1a2e1f] text-white rounded-lg hover:bg-[#0f1c13] disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {loading ? '解析中...' : '解析试卷'}
            </button>
          </div>
        </div>
      )}

      {/* 步骤2: 填写分数 */}
      {uploadStep === 2 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-lg font-semibold mb-4">步骤2: 填写考试信息和每题得分</h3>

          {/* 基本信息 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">考试名称 *</label>
              <input
                type="text"
                value={uploadForm.name}
                onChange={(e) => setUploadForm({...uploadForm, name: e.target.value})}
                placeholder="如: 2024年高三一模"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#c8f0d4]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">年级 *</label>
              <select
                value={uploadForm.grade}
                onChange={(e) => setUploadForm({...uploadForm, grade: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#c8f0d4]"
              >
                <option value="高一">高一</option>
                <option value="高二">高二</option>
                <option value="高三">高三</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">试卷总分 *</label>
              <input
                type="number"
                value={uploadForm.totalScore}
                onChange={(e) => setUploadForm({...uploadForm, totalScore: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#c8f0d4]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">考试日期</label>
              <input
                type="date"
                value={uploadForm.examDate}
                onChange={(e) => setUploadForm({...uploadForm, examDate: e.target.value})}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#c8f0d4]"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">参考人数</label>
              <input
                type="number"
                value={uploadForm.studentCount}
                onChange={(e) => setUploadForm({...uploadForm, studentCount: e.target.value})}
                placeholder="可选"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#c8f0d4]"
              />
            </div>
          </div>

          {/* 每题分数 */}
          <h4 className="font-medium text-gray-700 mb-2">每题得分情况 *</h4>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">题号</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">题目预览</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">该题满分</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">实际平均分</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {questionScores.map((q, idx) => (
                  <tr key={idx}>
                    <td className="px-4 py-2 text-sm font-medium">{q.question_number}</td>
                    <td className="px-4 py-2 text-sm text-gray-500 max-w-xs truncate">
                      {q.question_content || '(无内容)'}
                    </td>
                    <td className="px-4 py-2">
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        value={q.question_score}
                        onChange={(e) => handleScoreChange(idx, 'question_score', e.target.value)}
                        className="w-20 px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-[#c8f0d4]"
                      />
                    </td>
                    <td className="px-4 py-2">
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={q.actual_average}
                        onChange={(e) => handleScoreChange(idx, 'actual_average', e.target.value)}
                        className="w-20 px-2 py-1 border border-gray-300 rounded focus:ring-2 focus:ring-[#c8f0d4]"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex justify-between mt-6">
            <button
              onClick={() => setUploadStep(1)}
              className="px-6 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              上一步
            </button>
            <button
              onClick={handleSubmitHistory}
              disabled={loading}
              className="px-6 py-2 bg-[#1a2e1f] text-white rounded-lg hover:bg-[#0f1c13] disabled:bg-gray-300"
            >
              {loading ? '提交中...' : '提交数据'}
            </button>
          </div>
        </div>
      )}
    </div>
  )

  // 渲染统计数据
  const renderStats = () => (
    <div className="space-y-6">
      {stats ? (
        <>
          {/* 历史数据统计 */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 className="text-lg font-semibold mb-4">历史数据统计</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-[#e8f8ee] p-4 rounded-lg">
                <div className="text-2xl font-bold text-[#1a2e1f]">{stats.exam_history?.total_exams || 0}</div>
                <div className="text-sm text-gray-600">历史试卷数</div>
              </div>
              <div className="bg-green-50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-green-600">{stats.exam_history?.total_questions || 0}</div>
                <div className="text-sm text-gray-600">总题目数</div>
              </div>
              <div className="bg-[#e8f8ee] p-4 rounded-lg">
                <div className="text-2xl font-bold text-[#1a2e1f]">{stats.mapping_coverage?.total_mappings || 0}</div>
                <div className="text-sm text-gray-600">映射规则数</div>
              </div>
              <div className="bg-orange-50 p-4 rounded-lg">
                <div className="text-2xl font-bold text-orange-600">
                  {stats.prediction_accuracy?.sample_count || 0}
                </div>
                <div className="text-sm text-gray-600">预估验证数</div>
              </div>
            </div>
          </div>

          {/* 按年级统计 */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 className="text-lg font-semibold mb-4">按年级统计</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {['高一', '高二', '高三'].map((grade) => {
                const gradeData = stats.exam_history?.by_grade?.[grade] || { exam_count: 0 }
                const mappingData = stats.mapping_coverage?.by_grade?.[grade] || { total: 0, with_data: 0 }
                return (
                  <div key={grade} className="border border-gray-200 rounded-lg p-4">
                    <div className="font-semibold text-lg mb-2">{grade}</div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600">历史试卷</span>
                        <span className="font-medium">{gradeData.exam_count}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">映射规则</span>
                        <span className="font-medium">{mappingData.total}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">有效映射</span>
                        <span className="font-medium">{mappingData.with_data}</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 预估准确度 */}
          {stats.prediction_accuracy?.sample_count > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
              <h3 className="text-lg font-semibold mb-4">预估准确度</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center">
                  <div className="text-2xl font-bold text-gray-800">
                    {stats.prediction_accuracy.avg_error?.toFixed(1) || '-'}
                  </div>
                  <div className="text-sm text-gray-600">平均误差(分)</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-gray-800">
                    {stats.prediction_accuracy.avg_error_percentage?.toFixed(1) || '-'}%
                  </div>
                  <div className="text-sm text-gray-600">平均误差率</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-gray-800">
                    {((stats.prediction_accuracy.within_confidence || 0) * 100).toFixed(0)}%
                  </div>
                  <div className="text-sm text-gray-600">置信区间内</div>
                </div>
              </div>
            </div>
          )}

          {/* 覆盖警告 */}
          {stats.mapping_coverage?.coverage_warnings?.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
              <h4 className="font-semibold text-yellow-800 mb-2">数据覆盖警告</h4>
              <ul className="list-disc list-inside text-sm text-yellow-700">
                {stats.mapping_coverage.coverage_warnings.map((warning, idx) => (
                  <li key={idx}>{warning}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-8 text-gray-500">加载中...</div>
      )}
    </div>
  )

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      {/* 页面标题 */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">历史数据管理</h1>
        <p className="text-gray-600 mt-1">上传历史考试数据，训练分数预估模型</p>
      </div>

      {/* 消息提示 */}
      {message && (
        <div className={`mb-4 p-4 rounded-lg ${
          message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
        }`}>
          {message.text}
          <button
            onClick={() => setMessage(null)}
            className="float-right"
          >
            &times;
          </button>
        </div>
      )}

      {/* 标签页 */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {[
            { key: 'list', label: '历史数据', icon: ClipboardList },
            { key: 'upload', label: '上传数据', icon: Upload },
            { key: 'stats', label: '数据统计', icon: BarChart3 },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center ${
                activeTab === tab.key
                  ? 'border-[#2d5a3d] text-[#1a2e1f]'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              <tab.icon size={16} className="mr-2" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* 内容区域 */}
      {activeTab === 'list' && renderHistoryList()}
      {activeTab === 'upload' && renderUploadForm()}
      {activeTab === 'stats' && renderStats()}

      {/* Loading遮罩 */}
      {loading && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 shadow-xl">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#1a2e1f] mx-auto"></div>
            <p className="mt-2 text-gray-600">处理中...</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default HistoryDataPage
