import { useState, useEffect } from 'react'
import ExamStatisticsEnhanced from './ExamStatisticsEnhanced'

// 题目详情弹窗组件
function QuestionModal({ question, onClose }) {
  const hasError = question?.analysis?.error

  if (!question) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* 背景遮罩 */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* 弹窗内容 */}
      <div
        className="relative bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[85vh] overflow-hidden animate-scale-in"
        onClick={e => e.stopPropagation()}
      >
        {/* 弹窗头部 */}
        <div className="sticky top-0 bg-gradient-to-r from-[#2d5a3d] to-[#1a2e1f] text-white px-6 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xl font-bold">题目 {question.id || (question.index + 1)}</span>
            {question.difficulty?.final_difficulty && !hasError && (
              <span className="px-3 py-1 bg-white/20 rounded-full text-sm">
                难度 {question.difficulty.final_difficulty.toFixed(1)}/10
              </span>
            )}
            {question.competency?.primary_competency && !hasError && (
              <span className="px-3 py-1 bg-white/20 rounded-full text-sm">
                {question.competency.primary_competency}
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 弹窗内容区域 - 可滚动 */}
        <div className="p-6 overflow-y-auto" style={{ maxHeight: 'calc(85vh - 80px)' }}>
          {/* 题目内容 */}
          <div className="mb-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
            <h4 className="text-sm font-semibold text-gray-500 mb-2">题目内容</h4>
            <p className="text-gray-800 whitespace-pre-wrap leading-relaxed">
              {question.content || '暂无内容'}
            </p>
          </div>

          {/* 错误提示 */}
          {hasError && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
              <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div>
                <h4 className="font-semibold text-red-700 mb-1">分析失败</h4>
                <p className="text-sm text-red-600">{question.analysis?.error}</p>
              </div>
            </div>
          )}

          {/* 难度评估 */}
          {question.difficulty && !question.difficulty.error && (
            <div className="mb-6">
              <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                难度评估
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {question.difficulty.knowledge_complexity !== undefined && (
                  <div className="bg-[#e8f8ee] p-3 rounded-lg border border-[#c8f0d4] text-center">
                    <div className="text-xs text-gray-500 mb-1">知识复杂度</div>
                    <div className="text-2xl font-bold text-[#1a2e1f]">
                      {question.difficulty.knowledge_complexity.toFixed(1)}
                    </div>
                  </div>
                )}
                {question.difficulty.cognitive_level !== undefined && (
                  <div className="bg-green-50 p-3 rounded-lg border border-green-100 text-center">
                    <div className="text-xs text-gray-500 mb-1">认知层级</div>
                    <div className="text-2xl font-bold text-green-600">
                      {question.difficulty.cognitive_level.toFixed(1)}
                    </div>
                  </div>
                )}
                {question.difficulty.information_extraction !== undefined && (
                  <div className="bg-[#f3f0ff] p-3 rounded-lg border border-[#e2e8e4] text-center">
                    <div className="text-xs text-gray-500 mb-1">信息提取</div>
                    <div className="text-2xl font-bold text-[#2d5a3d]">
                      {question.difficulty.information_extraction.toFixed(1)}
                    </div>
                  </div>
                )}
                {question.difficulty.reasoning_steps !== undefined && (
                  <div className="bg-orange-50 p-3 rounded-lg border border-orange-100 text-center">
                    <div className="text-xs text-gray-500 mb-1">推理步骤</div>
                    <div className="text-2xl font-bold text-orange-600">
                      {question.difficulty.reasoning_steps.toFixed(1)}
                    </div>
                  </div>
                )}
              </div>
              {question.difficulty.difficulty_factors && question.difficulty.difficulty_factors.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {question.difficulty.difficulty_factors.map((factor, idx) => (
                    <span key={idx} className="px-2 py-1 bg-red-50 text-red-600 rounded-lg text-xs border border-red-100">
                      {factor}
                    </span>
                  ))}
                </div>
              )}
              {question.difficulty.estimated_solve_time && (
                <p className="mt-3 text-sm text-gray-600 flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  预计解题时间: {question.difficulty.estimated_solve_time}
                </p>
              )}
            </div>
          )}

          {/* 核心素养 */}
          {question.competency && !question.competency.error && (
            <div className="mb-6">
              <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-green-500 to-teal-500 rounded-full"></span>
                核心素养
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {question.competency['生命观念']?.涉及 && (
                  <div className="bg-green-50 p-3 rounded-lg border border-green-200 text-center">
                    <div className="text-xs text-gray-500 mb-1">生命观念</div>
                    <div className="text-2xl font-bold text-green-600">
                      {(question.competency['生命观念'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
                {question.competency['科学思维']?.涉及 && (
                  <div className="bg-[#e8f8ee] p-3 rounded-lg border border-[#b8d1bf] text-center">
                    <div className="text-xs text-gray-500 mb-1">科学思维</div>
                    <div className="text-2xl font-bold text-[#1a2e1f]">
                      {(question.competency['科学思维'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
                {question.competency['科学探究']?.涉及 && (
                  <div className="bg-[#f3f0ff] p-3 rounded-lg border border-[#e2e8e4] text-center">
                    <div className="text-xs text-gray-500 mb-1">科学探究</div>
                    <div className="text-2xl font-bold text-[#2d5a3d]">
                      {(question.competency['科学探究'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
                {question.competency['社会责任']?.涉及 && (
                  <div className="bg-orange-50 p-3 rounded-lg border border-orange-200 text-center">
                    <div className="text-xs text-gray-500 mb-1">社会责任</div>
                    <div className="text-2xl font-bold text-orange-600">
                      {(question.competency['社会责任'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 知识点 */}
          {question.analysis?.knowledge_points && question.analysis.knowledge_points.length > 0 && (
            <div className="mb-6">
              <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                知识点
              </h4>
              <div className="flex flex-wrap gap-2">
                {question.analysis.knowledge_points.map((point, idx) => (
                  <span
                    key={idx}
                    className="px-3 py-1.5 bg-[#e8f8ee] text-[#0f1c13] rounded-full text-sm font-medium border border-[#c8f0d4]"
                  >
                    {point}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 详细解析 */}
          {question.analysis?.detailed_analysis && (
            <div className="mb-6">
              <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-pink-500 to-rose-500 rounded-full"></span>
                详细解析
              </h4>
              <div className="p-4 bg-gray-50 rounded-xl border border-gray-100">
                <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                  {question.analysis.detailed_analysis}
                </p>
              </div>
            </div>
          )}

          {/* 参考答案 */}
          {question.analysis?.answer && (
            <div className="mb-6">
              <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-emerald-500 to-green-500 rounded-full"></span>
                参考答案
              </h4>
              <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-100">
                {typeof question.analysis.answer === 'string' ? (
                  <p className="text-gray-700">{question.analysis.answer}</p>
                ) : (
                  <div className="text-gray-700 space-y-2">
                    {Object.entries(question.analysis.answer).map(([key, value]) => (
                      <p key={key}>
                        <span className="font-medium text-emerald-700">{key}</span> {String(value)}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 易错点 */}
          {question.analysis?.common_mistakes && question.analysis.common_mistakes.length > 0 && (
            <div className="mb-6">
              <h4 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-amber-500 to-orange-500 rounded-full"></span>
                易错点
              </h4>
              <ul className="space-y-2">
                {question.analysis.common_mistakes.map((mistake, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-gray-700">
                    <span className="text-amber-500">⚠</span>
                    {mistake}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// 难度颜色
function getDifficultyColor(difficulty) {
  if (difficulty <= 3) return 'bg-green-100 text-green-700 border-green-200'
  if (difficulty <= 6) return 'bg-yellow-100 text-yellow-700 border-yellow-200'
  return 'bg-red-100 text-red-700 border-red-200'
}

function ResultDisplay({ data }) {
  const [selectedQuestion, setSelectedQuestion] = useState(null)

  // 按 ESC 关闭弹窗
  useEffect(() => {
    const handleEsc = (e) => {
      if (e.key === 'Escape') setSelectedQuestion(null)
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  // 禁止背景滚动
  useEffect(() => {
    if (selectedQuestion) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [selectedQuestion])

  if (!data || !data.questions) return null

  return (
    <div className="mt-12 max-w-7xl mx-auto">
      <div className="bg-white shadow-xl rounded-2xl p-8">
        {/* 整卷分析 */}
        {data.exam_statistics && (
          <ExamStatisticsEnhanced
            data={data.exam_statistics}
            questions={data.questions}
            scorePrediction={data.score_prediction}
          />
        )}

        {/* 统计信息 */}
        <div className="mb-8 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="stat-card stat-card-blue">
            <div className="text-sm text-gray-500 mb-1">题目总数</div>
            <div className="text-3xl font-bold text-[#1a2e1f]">{data.total_count || 0}</div>
          </div>
          <div className="stat-card stat-card-green">
            <div className="text-sm text-gray-500 mb-1">处理耗时</div>
            <div className="text-3xl font-bold text-emerald-600">
              {(data.processing_time || 0).toFixed(1)}s
            </div>
          </div>
          <div className="stat-card stat-card-purple">
            <div className="text-sm text-gray-500 mb-1">评估模式</div>
            <div className="text-2xl font-bold text-[#2d5a3d]">
              {data.mode === 'fast' ? '快速' : '深度'}
            </div>
          </div>
          <div className="stat-card stat-card-pink">
            <div className="text-sm text-gray-500 mb-1">平均耗时</div>
            <div className="text-3xl font-bold text-pink-600">
              {data.total_count ? (data.processing_time / data.total_count).toFixed(1) : 0}s
            </div>
          </div>
        </div>

        {/* 报告下载 */}
        {data.report_url && (
          <div className="mb-8 p-6 bg-gradient-to-r from-[#e8f8ee] to-[#f3f0ff] border border-[#b8d1bf] rounded-xl">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-1">
                  质量评估报告已生成
                </h3>
                <p className="text-sm text-gray-600">
                  包含难度曲线、素养分布等可视化图表
                </p>
              </div>
              <a
                href={data.report_url}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="btn-gradient flex items-center gap-2"
              >
                下载PDF报告
              </a>
            </div>
          </div>
        )}

        {/* 题目列表 */}
        <div>
          <h2 className="text-xl font-bold text-gray-800 mb-4">
            题目详细分析（共 {data.questions.length} 题）
          </h2>
          <p className="text-sm text-gray-500 mb-4">点击题目查看详细分析</p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.questions.map((question, index) => {
              const hasError = question.analysis?.error

              return (
                <button
                  key={question.id || index}
                  onClick={() => setSelectedQuestion({ ...question, index })}
                  className="text-left p-4 bg-white border border-gray-200 rounded-xl hover:border-[#b8d1bf] hover:shadow-lg transition-all"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-lg font-bold text-gray-800">
                      题目 {question.id || index + 1}
                    </span>
                    <span className="text-gray-400">→</span>
                  </div>

                  <div className="flex flex-wrap gap-2 mb-3">
                    {hasError ? (
                      <span className="px-2 py-1 bg-red-100 text-red-700 rounded text-xs">分析失败</span>
                    ) : (
                      <>
                        {question.difficulty?.final_difficulty && (
                          <span className={`px-2 py-1 rounded text-xs ${getDifficultyColor(question.difficulty.final_difficulty)}`}>
                            难度 {question.difficulty.final_difficulty.toFixed(1)}
                          </span>
                        )}
                        {question.competency?.primary_competency && (
                          <span className="px-2 py-1 bg-[#c8f0d4] text-[#0f1c13] rounded text-xs">
                            {question.competency.primary_competency}
                          </span>
                        )}
                      </>
                    )}
                  </div>

                  <p className="text-sm text-gray-600 overflow-hidden" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                    {question.content?.substring(0, 100) || '暂无内容'}
                  </p>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* 弹窗 */}
      {selectedQuestion && (
        <QuestionModal
          question={selectedQuestion}
          onClose={() => setSelectedQuestion(null)}
        />
      )}
    </div>
  )
}

export default ResultDisplay
