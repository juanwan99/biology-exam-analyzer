import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle } from 'lucide-react'
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
            {question.difficulty?.features?.bloom && !hasError && (
              <span className="px-3 py-1 bg-white/20 rounded-full text-sm">
                {['', '识记', '理解', '应用', '分析', '评价', '创造'][question.difficulty.features.bloom] || ''}
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
          <div className="mb-6 p-4 bg-[#f9fafb] rounded-xl border border-[#e2e8e4]">
            <h4 className="text-sm font-semibold text-[#5a6b5e] mb-2">题目内容</h4>
            <p className="text-[#1a2e1f] whitespace-pre-wrap leading-relaxed">
              {question.content || '暂无内容'}
            </p>
          </div>

          {/* 错误提示 */}
          {hasError && (
            <div className="mb-6 p-4 bg-[#fef0f0] border border-[#fde8e8] rounded-xl flex items-start gap-3">
              <svg className="w-5 h-5 text-[#991b1b] flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <div>
                <h4 className="font-semibold text-[#991b1b] mb-1">分析失败</h4>
                <p className="text-sm text-[#991b1b]">{question.analysis?.error}</p>
              </div>
            </div>
          )}

          {/* 难度评估 */}
          {question.difficulty && !question.difficulty.error && (
            <div className="mb-6">
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                难度评估
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {question.difficulty.knowledge_complexity !== undefined && (
                  <div className="bg-[#e8f8ee] p-3 rounded-lg border border-[#c8f0d4] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">知识复杂度</div>
                    <div className="text-2xl font-bold text-[#1a2e1f]">
                      {question.difficulty.knowledge_complexity.toFixed(1)}
                    </div>
                  </div>
                )}
                {question.difficulty.cognitive_level !== undefined && (
                  <div className="bg-[#e8f8ee] p-3 rounded-lg border border-[#c8f0d4] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">认知层级</div>
                    <div className="text-2xl font-bold text-[#2d5a3d]">
                      {question.difficulty.cognitive_level.toFixed(1)}
                    </div>
                  </div>
                )}
                {question.difficulty.information_extraction !== undefined && (
                  <div className="bg-[#f3f0ff] p-3 rounded-lg border border-[#e2e8e4] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">信息提取</div>
                    <div className="text-2xl font-bold text-[#2d5a3d]">
                      {question.difficulty.information_extraction.toFixed(1)}
                    </div>
                  </div>
                )}
                {question.difficulty.reasoning_steps !== undefined && (
                  <div className="bg-[#fdf6e3] p-3 rounded-lg border border-[#fef3c7] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">推理步骤</div>
                    <div className="text-2xl font-bold text-[#92400e]">
                      {question.difficulty.reasoning_steps.toFixed(1)}
                    </div>
                  </div>
                )}
              </div>
              {question.difficulty.difficulty_factors && question.difficulty.difficulty_factors.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {question.difficulty.difficulty_factors.map((factor, idx) => (
                    <span key={idx} className="px-2 py-1 bg-[#fef0f0] text-[#991b1b] rounded-lg text-xs border border-[#fde8e8]">
                      {factor}
                    </span>
                  ))}
                </div>
              )}
              {question.difficulty.estimated_solve_time && (
                <p className="mt-3 text-sm text-[#5a6b5e] flex items-center gap-2">
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
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                核心素养
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {question.competency['生命观念']?.涉及 && (
                  <div className="bg-[#e8f8ee] p-3 rounded-lg border border-[#c8f0d4] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">生命观念</div>
                    <div className="text-2xl font-bold text-[#2d5a3d]">
                      {(question.competency['生命观念'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
                {question.competency['科学思维']?.涉及 && (
                  <div className="bg-[#e8f8ee] p-3 rounded-lg border border-[#b8d1bf] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">科学思维</div>
                    <div className="text-2xl font-bold text-[#1a2e1f]">
                      {(question.competency['科学思维'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
                {question.competency['科学探究']?.涉及 && (
                  <div className="bg-[#f3f0ff] p-3 rounded-lg border border-[#e2e8e4] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">科学探究</div>
                    <div className="text-2xl font-bold text-[#2d5a3d]">
                      {(question.competency['科学探究'].权重 * 100).toFixed(0)}%
                    </div>
                  </div>
                )}
                {question.competency['社会责任']?.涉及 && (
                  <div className="bg-[#fdf6e3] p-3 rounded-lg border border-[#fef3c7] text-center">
                    <div className="text-xs text-[#5a6b5e] mb-1">社会责任</div>
                    <div className="text-2xl font-bold text-[#92400e]">
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
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
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
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                详细解析
              </h4>
              <div className="p-4 bg-[#f9fafb] rounded-xl border border-[#f0f4f1]">
                <p className="text-[#1a2e1f] whitespace-pre-wrap leading-relaxed">
                  {question.analysis.detailed_analysis}
                </p>
              </div>
            </div>
          )}

          {/* 参考答案 */}
          {question.analysis?.answer && (
            <div className="mb-6">
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                参考答案
              </h4>
              <div className="p-4 bg-[#e8f8ee] rounded-xl border border-[#c8f0d4]">
                {typeof question.analysis.answer === 'string' ? (
                  <p className="text-[#1a2e1f]">{question.analysis.answer}</p>
                ) : (
                  <div className="text-[#1a2e1f] space-y-2">
                    {Object.entries(question.analysis.answer).map(([key, value]) => (
                      <p key={key}>
                        <span className="font-medium text-[#2d5a3d]">{key}</span> {String(value)}
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
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                易错点
              </h4>
              <ul className="space-y-2">
                {question.analysis.common_mistakes.map((mistake, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-[#1a2e1f]">
                    <AlertTriangle size={14} className="text-[#f59e0b] flex-shrink-0" />
                    {mistake}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 命题质量审查 */}
          {(() => {
            const f = question.difficulty?.features
            const items = []
            if (f?.quality_scientific) items.push({ label: '科学性', text: f.quality_scientific })
            if (f?.quality_normative) items.push({ label: '规范性', text: f.quality_normative })
            if (f?.quality_language) items.push({ label: '语言表述', text: f.quality_language })
            if (f?.quality_context) items.push({ label: '情境设计', text: f.quality_context })
            if (items.length === 0) return null
            const qs = f?.quality_score
            const scoreColors = {
              1: 'bg-[#fef0f0] text-[#991b1b] border-[#fde8e8]',
              2: 'bg-[#fef0f0] text-[#991b1b] border-[#fde8e8]',
              3: 'bg-[#fdf6e3] text-[#92400e] border-[#fef3c7]',
              4: 'bg-[#e8f8ee] text-[#2d5a3d] border-[#c8f0d4]',
              5: 'bg-[#e8f8ee] text-[#2d5a3d] border-[#c8f0d4]',
            }
            const scoreLabels = { 1: '严重缺陷', 2: '需修改', 3: '基本合格', 4: '较好', 5: '优秀' }
            return (
              <div className="mb-6">
                <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                  <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                  命题质量审查
                  {qs && (
                    <span className={`ml-2 px-2 py-0.5 text-xs font-semibold rounded-full border ${scoreColors[qs] || ''}`}>
                      {qs}/5 {scoreLabels[qs] || ''}
                    </span>
                  )}
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {items.map((item, idx) => (
                    <div key={idx} className="p-3 bg-[#f9fafb] rounded-lg border border-[#e2e8e4]">
                      <div className="text-xs font-semibold text-[#5a6b5e] mb-1">{item.label}</div>
                      <p className="text-sm text-[#1a2e1f] leading-relaxed">{item.text}</p>
                    </div>
                  ))}
                </div>
              </div>
            )
          })()}

          {/* 教师点评 */}
          {question.difficulty?.features?.teacher_comment && (
            <div className="mb-6">
              <h4 className="font-semibold text-[#1a2e1f] mb-3 flex items-center gap-2">
                <span className="w-1 h-5 bg-gradient-to-b from-[#2d5a3d] to-[#1a2e1f] rounded-full"></span>
                教师点评
              </h4>
              <div className="p-4 bg-[#fdf6e3] rounded-xl border border-[#fef3c7]">
                <p className="text-[#1a2e1f] leading-relaxed">
                  {question.difficulty.features.teacher_comment}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// 难度颜色
function getDifficultyColor(difficulty) {
  if (difficulty <= 3) return 'bg-[#e8f8ee] text-[#2d5a3d] border-[#c8f0d4]'
  if (difficulty <= 6) return 'bg-[#fdf6e3] text-[#92400e] border-[#fef3c7]'
  return 'bg-[#fef0f0] text-[#991b1b] border-[#fde8e8]'
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
    <div className="max-w-[1200px] mx-auto">
      <div
        className="bg-white"
        style={{
          borderRadius: '24px',
          border: '1px solid var(--color-border-light)',
          boxShadow: 'var(--shadow-lg)',
          padding: 'clamp(24px, 4vw, 48px)',
        }}
      >
        {/* 整卷分析 */}
        {data.exam_statistics && (
          <ExamStatisticsEnhanced
            data={data.exam_statistics}
            questions={data.questions}
            scorePrediction={data.score_prediction}
          />
        )}

        {/* 统计信息 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6" style={{ marginBottom: '48px' }}>
          <div className="stat-card stat-card-blue" style={{ padding: '28px 24px' }}>
            <div className="text-sm mb-2" style={{ color: 'var(--color-muted)' }}>题目总数</div>
            <div className="font-extrabold" style={{ fontSize: '2.25rem', color: 'var(--color-primary)', lineHeight: 1.1 }}>
              {data.total_count || 0}
            </div>
          </div>
          <div className="stat-card stat-card-green" style={{ padding: '28px 24px' }}>
            <div className="text-sm mb-2" style={{ color: 'var(--color-muted)' }}>处理耗时</div>
            <div className="font-extrabold" style={{ fontSize: '2.25rem', color: 'var(--color-primary-light)', lineHeight: 1.1 }}>
              {(data.processing_time || 0).toFixed(1)}<span className="text-lg font-semibold ml-0.5">s</span>
            </div>
          </div>
          <div className="stat-card stat-card-purple" style={{ padding: '28px 24px' }}>
            <div className="text-sm mb-2" style={{ color: 'var(--color-muted)' }}>评估模式</div>
            <div className="font-extrabold" style={{ fontSize: '1.75rem', color: 'var(--color-primary-light)', lineHeight: 1.1 }}>
              {data.mode === 'fast' ? '快速' : '深度'}
            </div>
          </div>
          <div className="stat-card stat-card-pink" style={{ padding: '28px 24px' }}>
            <div className="text-sm mb-2" style={{ color: 'var(--color-muted)' }}>平均耗时</div>
            <div className="font-extrabold" style={{ fontSize: '2.25rem', color: 'var(--color-primary)', lineHeight: 1.1 }}>
              {data.total_count ? (data.processing_time / data.total_count).toFixed(1) : 0}<span className="text-lg font-semibold ml-0.5">s</span>
            </div>
          </div>
        </div>

        {/* 报告下载 — 突出 CTA */}
        {data.report_url && (
          <div
            style={{
              marginBottom: '48px',
              padding: '32px 36px',
              background: 'linear-gradient(135deg, var(--macaron-mint-light), var(--macaron-mint))',
              border: '1px solid #b8d1bf',
              borderRadius: '20px',
              textAlign: 'center',
            }}
          >
            <h3 className="font-bold" style={{ color: 'var(--color-primary)', fontSize: '1.25rem', marginBottom: '8px' }}>
              质量评估报告已生成
            </h3>
            <p className="text-sm" style={{ color: 'var(--color-secondary)', marginBottom: '24px' }}>
              包含难度曲线、素养分布等可视化图表
            </p>
            <a
              href={data.report_url}
              download="试卷质量评估报告.pdf"
              className="btn-primary"
              style={{ padding: '14px 48px', fontSize: '16px', display: 'inline-block', textDecoration: 'none' }}
            >
              下载PDF报告
            </a>
          </div>
        )}

        {/* 题目列表 */}
        <div>
          <h2 className="section-title" style={{ marginBottom: '12px' }}>
            题目详细分析（共 {data.questions.length} 题）
          </h2>
          <p className="text-sm" style={{ color: 'var(--color-muted)', marginBottom: '24px' }}>
            点击题目查看详细分析
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {data.questions.map((question, index) => {
              const hasError = question.analysis?.error

              return (
                <button
                  key={question.id || index}
                  onClick={() => setSelectedQuestion({ ...question, index })}
                  className="text-left bg-white"
                  style={{
                    padding: '24px',
                    borderRadius: '24px',
                    border: '1px solid var(--color-border-light)',
                    boxShadow: 'var(--shadow-sm)',
                    transition: 'var(--transition)',
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => {
                    e.currentTarget.style.boxShadow = 'var(--shadow-lg)'
                    e.currentTarget.style.transform = 'translateY(-4px)'
                    e.currentTarget.style.borderColor = 'var(--color-primary-light)'
                  }}
                  onMouseLeave={e => {
                    e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
                    e.currentTarget.style.transform = 'translateY(0)'
                    e.currentTarget.style.borderColor = 'var(--color-border-light)'
                  }}
                >
                  <div className="flex items-center justify-between" style={{ marginBottom: '12px' }}>
                    <span className="font-bold" style={{ fontSize: '1.1rem', color: 'var(--color-primary)' }}>
                      题目 {question.id || index + 1}
                    </span>
                    <span
                      className="inline-flex items-center justify-center"
                      style={{
                        width: '28px',
                        height: '28px',
                        borderRadius: '50%',
                        background: 'var(--macaron-mint-light)',
                        color: 'var(--color-primary-light)',
                        fontSize: '14px',
                      }}
                    >
                      &rarr;
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2" style={{ marginBottom: '14px' }}>
                    {hasError ? (
                      <span
                        className="text-xs font-semibold"
                        style={{
                          padding: '4px 12px',
                          borderRadius: '50px',
                          background: 'var(--macaron-coral)',
                          color: '#991b1b',
                        }}
                      >
                        分析失败
                      </span>
                    ) : (
                      <>
                        {question.difficulty?.final_difficulty && (
                          <span
                            className={`text-xs font-semibold ${getDifficultyColor(question.difficulty.final_difficulty)}`}
                            style={{ padding: '4px 12px', borderRadius: '50px' }}
                          >
                            难度 {question.difficulty.final_difficulty.toFixed(1)}
                          </span>
                        )}
                        {question.competency?.primary_competency && (
                          <span
                            className="text-xs font-semibold"
                            style={{
                              padding: '4px 12px',
                              borderRadius: '50px',
                              background: 'var(--macaron-mint)',
                              color: 'var(--color-primary-dark)',
                            }}
                          >
                            {question.competency.primary_competency}
                          </span>
                        )}
                      </>
                    )}
                  </div>

                  <p
                    className="text-sm overflow-hidden"
                    style={{
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      color: 'var(--color-secondary)',
                      lineHeight: 1.6,
                    }}
                  >
                    {question.content?.substring(0, 100) || '暂无内容'}
                  </p>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* 弹窗 — Portal 到 body 避免父容器 stacking context 裁剪 */}
      {selectedQuestion && createPortal(
        <QuestionModal
          question={selectedQuestion}
          onClose={() => setSelectedQuestion(null)}
        />,
        document.body
      )}
    </div>
  )
}

export default ResultDisplay
