import { useState } from 'react'
import { TrendingUp, BarChart3 as BarChartIcon, Brain, Crosshair, Tags, Library, ChevronDown } from 'lucide-react'
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts'
import ScorePrediction from './ScorePrediction'

// 气泡脉动动画样式（momowan 绿色光晕）
const bubbleAnimationStyle = `
  @keyframes bubbleGlow {
    0%, 100% {
      filter: drop-shadow(0 0 6px rgba(45, 90, 61, 0.5));
      opacity: 0.85;
    }
    50% {
      filter: drop-shadow(0 0 10px rgba(45, 90, 61, 0.8));
      opacity: 1;
    }
  }

  .bubble-container .recharts-scatter-symbol {
    animation: bubbleGlow 3s ease-in-out infinite;
  }
`

// 自定义折叠面板组件
function Collapsible({ title, badge, badgeColor, percentage, barColor, children }) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="mb-3 overflow-hidden"
      style={{ borderRadius: '14px', border: '1px solid var(--color-border-light)' }}
    >
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3 text-left transition-colors hover:bg-[#f9fafb]"
        style={{ backgroundColor: barColor ? `${barColor}08` : 'transparent' }}
      >
        <div className="flex items-center gap-3">
          <span
            style={{
              width: 4,
              height: 24,
              backgroundColor: barColor || 'var(--color-primary-light)',
              borderRadius: 2,
              display: 'inline-block',
              flexShrink: 0
            }}
          />
          <span className="font-semibold text-[#1a2e1f]">{title}</span>
        </div>
        <div className="flex gap-3 items-center">
          {badge && (
            <span
              className="px-3 py-1 text-xs font-semibold text-white"
              style={{ borderRadius: '50px', backgroundColor: badgeColor || barColor }}
            >
              {badge}
            </span>
          )}
          {percentage !== undefined && (
            <span className="text-sm text-[#5a6b5e]">
              占比: {percentage}%
            </span>
          )}
          <ChevronDown
            size={18}
            className="text-[#5a6b5e] transition-transform"
            style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.25s cubic-bezier(0.4, 0, 0.2, 1)' }}
          />
        </div>
      </button>
      {open && (
        <div className="px-5 py-4" style={{ borderTop: '1px solid var(--color-border-light)' }}>
          {children}
        </div>
      )}
    </div>
  )
}

function ExamStatisticsEnhanced({ data, questions, scorePrediction }) {
  if (!data) return null

  const {
    difficulty_distribution,
    difficulty_distribution_by_score,
    difficulty_curve,
    avg_difficulty,
    avg_cognitive_level,
    top_knowledge_points,
    knowledge_textbook_distribution,
    competency_distribution,
    bloom_distribution,
  } = data

  // 难度分布数据转换为recharts格式（题目数量）
  const difficultyDistData = difficulty_distribution ? [
    { name: '简单', count: difficulty_distribution['简单'] || 0, fill: '#10b981', percentage: 0 },
    { name: '中等', count: difficulty_distribution['中等'] || 0, fill: '#f59e0b', percentage: 0 },
    { name: '困难', count: difficulty_distribution['困难'] || 0, fill: '#ef4444', percentage: 0 }
  ] : []

  // 计算百分比
  if (difficultyDistData.length > 0) {
    const total = difficultyDistData.reduce((sum, item) => sum + item.count, 0)
    difficultyDistData.forEach(item => {
      item.percentage = total > 0 ? ((item.count / total) * 100).toFixed(1) : 0
    })
  }

  // 新增：难度分值分布数据
  const difficultyScoreData = difficulty_distribution_by_score ? [
    {
      name: '简单',
      score: difficulty_distribution_by_score['简单']?.total_score || 0,
      percentage: difficulty_distribution_by_score['简单']?.percentage || 0,
      fill: '#10b981'
    },
    {
      name: '中等',
      score: difficulty_distribution_by_score['中等']?.total_score || 0,
      percentage: difficulty_distribution_by_score['中等']?.percentage || 0,
      fill: '#f59e0b'
    },
    {
      name: '困难',
      score: difficulty_distribution_by_score['困难']?.total_score || 0,
      percentage: difficulty_distribution_by_score['困难']?.percentage || 0,
      fill: '#ef4444'
    }
  ] : []

  // 检查是否有实际分值数据（总分大于0才显示）
  const hasScoreData = difficultyScoreData.length > 0 && difficultyScoreData.some(item => item.score > 0)

  // 知识点数据（取前10，V1 返回 weighted_score，兼容旧 count）
  const knowledgePointsData = top_knowledge_points
    ? top_knowledge_points.slice(0, 10).map(item => ({
        ...item,
        score: item.weighted_score ?? item.count ?? 0,
      }))
    : []

  // Bloom 认知层级分布（分值加权占比，来自后端 V1）
  const BLOOM_COLORS_BAR = ['#a3c4bc', '#5a9a6d', '#10b981', '#2d5a3d', '#f59e0b', '#ef4444']
  const bloomData = bloom_distribution
    ? Object.entries(bloom_distribution)
        .filter(([_, v]) => v > 0)
        .map(([name, value], i) => ({ name, value: Math.round(value * 100), fill: BLOOM_COLORS_BAR[i] }))
    : []

  // v3.1新增：教材分布数据处理
  const textbookColors = {
    '必修1': '#2d5a3d',
    '必修2': '#10b981',
    '选择性必修1': '#5a9a6d',
    '选择性必修2': '#f59e0b',
    '选择性必修3': '#ef4444'
  }

  const textbookDistData = knowledge_textbook_distribution ? [
    {
      name: '必修1',
      score: knowledge_textbook_distribution['必修1']?.weighted_score ?? knowledge_textbook_distribution['必修1']?.count ?? 0,
      percentage: knowledge_textbook_distribution['必修1']?.percentage || 0,
      fill: textbookColors['必修1']
    },
    {
      name: '必修2',
      score: knowledge_textbook_distribution['必修2']?.weighted_score ?? knowledge_textbook_distribution['必修2']?.count ?? 0,
      percentage: knowledge_textbook_distribution['必修2']?.percentage || 0,
      fill: textbookColors['必修2']
    },
    {
      name: '选修1',
      score: knowledge_textbook_distribution['选择性必修1']?.weighted_score ?? knowledge_textbook_distribution['选择性必修1']?.count ?? 0,
      percentage: knowledge_textbook_distribution['选择性必修1']?.percentage || 0,
      fill: textbookColors['选择性必修1']
    },
    {
      name: '选修2',
      score: knowledge_textbook_distribution['选择性必修2']?.weighted_score ?? knowledge_textbook_distribution['选择性必修2']?.count ?? 0,
      percentage: knowledge_textbook_distribution['选择性必修2']?.percentage || 0,
      fill: textbookColors['选择性必修2']
    },
    {
      name: '选修3',
      score: knowledge_textbook_distribution['选择性必修3']?.weighted_score ?? knowledge_textbook_distribution['选择性必修3']?.count ?? 0,
      percentage: knowledge_textbook_distribution['选择性必修3']?.percentage || 0,
      fill: textbookColors['选择性必修3']
    }
  ].filter(item => item.score > 0) : []

  // 素养分布数据转换（使用总权重而非题目数，因为一道题可能涉及多种素养）
  const competencyData = competency_distribution ? [
    { name: '生命观念', count: competency_distribution['生命观念']?.总权重 || 0, fill: '#2d5a3d' },
    { name: '科学思维', count: competency_distribution['科学思维']?.总权重 || 0, fill: '#10b981' },
    { name: '科学探究', count: competency_distribution['科学探究']?.总权重 || 0, fill: '#5a9a6d' },
    { name: '社会责任', count: competency_distribution['社会责任']?.总权重 || 0, fill: '#f59e0b' }
  ] : []

  // 核心素养细分维度数据处理
  const competencyColors = {
    '生命观念': '#2d5a3d',
    '科学思维': '#10b981',
    '科学探究': '#5a9a6d',
    '社会责任': '#f59e0b'
  }

  const getCompetencySubdimensionData = (competency) => {
    if (!competency_distribution || !competency_distribution[competency]) return []
    const data = competency_distribution[competency]
    if (!data.细分) return []

    return Object.entries(data.细分)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
  }

  // ===== 新增：认知层级分布（聚合所有题目的cognitive_breakdown）=====
  const cognitiveAggregated = {
    '记忆': 0, '理解': 0, '应用': 0,
    '分析': 0, '综合': 0, '评价': 0
  }

  if (questions && questions.length > 0) {
    questions.forEach(q => {
      if (q.difficulty?.cognitive_breakdown) {
        Object.keys(cognitiveAggregated).forEach(key => {
          cognitiveAggregated[key] += (q.difficulty.cognitive_breakdown[key] || 0)
        })
      }
    })

    // 计算平均值
    const total = Object.values(cognitiveAggregated).reduce((a, b) => a + b, 0)
    if (total > 0) {
      Object.keys(cognitiveAggregated).forEach(key => {
        cognitiveAggregated[key] = Math.round((cognitiveAggregated[key] / questions.length))
      })
    }
  }

  const cognitivePieData = Object.entries(cognitiveAggregated)
    .filter(([_, value]) => value > 0)
    .map(([name, value]) => ({ name, value }))

  // momowan palette cognitive colors
  const COGNITIVE_COLORS = ['#ef4444', '#f59e0b', '#10b981', '#2d5a3d', '#5a9a6d', '#8ab596']

  // ===== 新增：难度因素统计（聚合所有题目）=====
  const factorsMap = new Map()

  if (questions && questions.length > 0) {
    questions.forEach(q => {
      if (q.difficulty?.difficulty_factors_weighted) {
        q.difficulty.difficulty_factors_weighted.forEach(item => {
          const key = item.factor
          if (factorsMap.has(key)) {
            const existing = factorsMap.get(key)
            factorsMap.set(key, {
              factor: key,
              count: existing.count + 1,
              totalImpact: existing.totalImpact + item.impact,
              category: item.category
            })
          } else {
            factorsMap.set(key, {
              factor: key,
              count: 1,
              totalImpact: item.impact,
              category: item.category
            })
          }
        })
      }
    })
  }

  const factorsData = Array.from(factorsMap.values())
    .map(item => ({
      ...item,
      avgImpact: item.totalImpact / item.count
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 15) // 取前15个

  const getCategoryColor = (category) => {
    const colors = {
      '推理复杂': '#2d5a3d',
      '知识跨度': '#10b981',
      '信息隐藏': '#5a9a6d',
      '陌生情境': '#f59e0b'
    }
    return colors[category] || '#8a9a8e'
  }

  // 调试：打印气泡数据和类别
  if (import.meta.env.DEV) {
    console.log('=== 难度因素气泡数据 ===')
    factorsData.forEach(item => {
      console.log(`因素: ${item.factor}, 类别: ${item.category}, 颜色应为: ${getCategoryColor(item.category)}`)
    })
  }

  // ===== 新增：题目标签云数据 =====
  const tagsMap = new Map()

  if (questions && questions.length > 0) {
    questions.forEach(q => {
      if (q.difficulty?.question_tags) {
        q.difficulty.question_tags.forEach(tag => {
          tagsMap.set(tag, (tagsMap.get(tag) || 0) + 1)
        })
      }
    })
  }

  const tagsData = Array.from(tagsMap.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 20)

  return (
    <div style={{ marginBottom: '56px' }}>
      <h2 className="section-title" style={{ marginBottom: '32px' }}>
        整卷质量分析（增强版）
      </h2>

      {/* 分数预估（如果有数据） */}
      {scorePrediction && (
        <div style={{ marginBottom: '32px' }}>
          <ScorePrediction prediction={scorePrediction} />
        </div>
      )}

      {/* 关键指标卡片 — 突出大数字 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ marginBottom: '48px' }}>
        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'linear-gradient(135deg, #ffffff 0%, var(--macaron-mint-light) 100%)',
            transition: 'var(--transition)',
            overflow: 'hidden',
          }}
          onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = 'var(--shadow-lg)' }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'var(--shadow-sm)' }}
        >
          <div style={{ padding: '32px' }}>
            <p className="text-sm font-medium" style={{ color: 'var(--color-muted)', marginBottom: '8px' }}>
              平均难度系数（分值加权）
            </p>
            <div className="font-extrabold" style={{ fontSize: '3rem', color: 'var(--color-primary)', lineHeight: 1.1 }}>
              {avg_difficulty !== undefined ? avg_difficulty.toFixed(2) : 'N/A'}
            </div>
            <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '12px' }}>
              满分10分制 {avg_difficulty <= 3.5 ? '偏简单' : avg_difficulty <= 6.5 ? '适中' : '偏困难'}
            </p>
          </div>
        </div>

        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'linear-gradient(135deg, #ffffff 0%, var(--macaron-blue-light) 100%)',
            transition: 'var(--transition)',
            overflow: 'hidden',
          }}
          onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = 'var(--shadow-lg)' }}
          onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'var(--shadow-sm)' }}
        >
          <div style={{ padding: '32px' }}>
            <p className="text-sm font-medium" style={{ color: 'var(--color-muted)', marginBottom: '8px' }}>
              平均认知层级（分值加权）
            </p>
            <div className="font-extrabold" style={{ fontSize: '3rem', color: 'var(--color-primary-light)', lineHeight: 1.1 }}>
              {avg_cognitive_level !== undefined ? avg_cognitive_level.toFixed(2) : 'N/A'}
            </div>
            <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '12px' }}>
              满分10分制 布鲁姆认知层级评估
            </p>
          </div>
        </div>
      </div>

      {/* 难度曲线图 */}
      {difficulty_curve && difficulty_curve.length > 0 && (
        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'var(--color-bg)',
            marginBottom: '32px',
            transition: 'var(--transition)',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '32px' }}>
            <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
              <TrendingUp size={18} className="inline mr-1" /> 难度曲线（题目顺序）
            </h3>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={difficulty_curve}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8e4" />
                <XAxis
                  dataKey="question_id"
                  label={{ value: '题目编号', position: 'insideBottom', offset: -5 }}
                />
                <YAxis
                  domain={[0, 10]}
                  label={{ value: '难度系数', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip
                  formatter={(value) => [value.toFixed(2), '难度系数']}
                  labelFormatter={(label) => `题目 ${label}`}
                  contentStyle={{ borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="difficulty"
                  stroke="#2d5a3d"
                  strokeWidth={2.5}
                  name="难度系数"
                  dot={{ fill: '#2d5a3d', r: 5, strokeWidth: 2, stroke: '#fff' }}
                  activeDot={{ r: 7, stroke: '#2d5a3d', strokeWidth: 2, fill: '#c8f0d4' }}
                />
              </LineChart>
            </ResponsiveContainer>
            <p className="text-sm text-center" style={{ color: 'var(--color-muted)', marginTop: '16px' }}>
              建议：试卷难度应呈阶梯式上升，避免大幅波动
            </p>
          </div>
        </div>
      )}

      {/* 双列布局：难度分布（分值） + 认知层级分布 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6" style={{ marginBottom: '32px' }}>
        {/* 难度分值分布柱状图 */}
        {hasScoreData && (
          <div
            style={{
              height: '100%',
              borderRadius: '24px',
              border: '1px solid var(--color-border-light)',
              boxShadow: 'var(--shadow-sm)',
              background: 'var(--color-bg)',
              overflow: 'hidden',
            }}
          >
            <div style={{ padding: '32px' }}>
              <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
                <BarChartIcon size={18} className="inline mr-1" /> 难度分值分布（细粒度）
              </h3>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={difficultyScoreData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8e4" />
                  <XAxis dataKey="name" />
                  <YAxis label={{ value: '总分值', angle: -90, position: 'insideLeft' }} />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload
                        return (
                          <div style={{ background: '#fff', padding: '12px 16px', borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}>
                            <p className="font-semibold" style={{ color: data.fill }}>
                              {data.name}
                            </p>
                            <p className="text-sm" style={{ color: 'var(--color-primary)' }}>分值: {data.score.toFixed(1)}分</p>
                            <p className="text-sm" style={{ color: 'var(--color-primary)' }}>占比: {data.percentage}%</p>
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                  <Bar dataKey="score" name="总分值" radius={[8, 8, 0, 0]}>
                    {difficultyScoreData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div style={{ marginTop: '20px', padding: '14px 16px', background: 'var(--macaron-mint-light)', borderRadius: '14px' }}>
                <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                  <strong>理想比例：</strong>简单 30% 中等 50% 困难 20%
                </p>
                <div className="flex flex-wrap gap-4" style={{ marginTop: '8px' }}>
                  {difficultyScoreData.map(item => (
                    <span key={item.name} className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                      {item.name}: {item.score.toFixed(1)}分 ({item.percentage}%)
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 认知层级饼图 */}
        {cognitivePieData.length > 0 && (
          <div
            style={{
              height: '100%',
              borderRadius: '24px',
              border: '1px solid var(--color-border-light)',
              boxShadow: 'var(--shadow-sm)',
              background: 'var(--color-bg)',
              overflow: 'hidden',
            }}
          >
            <div style={{ padding: '32px' }}>
              <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
                <Brain size={18} className="inline mr-1" /> 认知层级分布（布鲁姆分类法）
              </h3>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={cognitivePieData}
                    cx="50%"
                    cy="50%"
                    labelLine={true}
                    label={(entry) => `${entry.name} ${entry.value}%`}
                    outerRadius={85}
                    fill="#2d5a3d"
                    dataKey="value"
                  >
                    {cognitivePieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COGNITIVE_COLORS[index % COGNITIVE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ marginTop: '20px', padding: '14px 16px', background: 'var(--macaron-mint-light)', borderRadius: '14px' }}>
                <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                  <strong>专业提示：</strong>高阶思维（分析/综合/评价）占比建议 &ge; 50%
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bloom 认知层级分布（分值加权） */}
      {bloomData.length > 0 && (
        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'var(--color-bg)',
            marginBottom: '32px',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '32px' }}>
            <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
              <Brain size={18} className="inline mr-1" /> Bloom 认知层级分布（分值加权）
            </h3>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={bloomData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8e4" />
                <XAxis dataKey="name" />
                <YAxis label={{ value: '占比 %', angle: -90, position: 'insideLeft' }} domain={[0, 100]} />
                <Tooltip
                  formatter={(value) => [`${value}%`, '占比']}
                  contentStyle={{ borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}
                />
                <Bar dataKey="value" name="分值占比" radius={[8, 8, 0, 0]}>
                  {bloomData.map((entry, index) => (
                    <Cell key={`bloom-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div style={{ marginTop: '20px', padding: '14px 16px', background: 'var(--macaron-mint-light)', borderRadius: '14px' }}>
              <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                <strong>说明：</strong>按 Bloom 分类法展示各认知层级占试卷总分的比例（1识记→6创造）
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 难度因素气泡图 */}
      {factorsData.length > 0 && (
        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'var(--color-bg)',
            marginBottom: '32px',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '32px' }}>
            <style>{bubbleAnimationStyle}</style>
            <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
              <Crosshair size={18} className="inline mr-1" /> 难度因素分布（气泡大小 = 出现频次）
            </h3>
            <ResponsiveContainer width="100%" height={360} className="bubble-container">
              <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8e4" />
                <XAxis
                  type="number"
                  dataKey="count"
                  name="出现次数"
                  label={{ value: '出现次数', position: 'insideBottom', offset: -5 }}
                />
                <YAxis
                  type="number"
                  dataKey="avgImpact"
                  name="平均影响"
                  label={{ value: '平均难度影响', angle: -90, position: 'insideLeft' }}
                  domain={[0, 3.5]}
                />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload
                      return (
                        <div style={{ background: '#fff', padding: '14px 18px', borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}>
                          <p className="font-semibold" style={{ color: 'var(--color-primary)', marginBottom: '4px' }}>{data.factor}</p>
                          <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>出现次数: {data.count}</p>
                          <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>平均影响: {data.avgImpact.toFixed(1)}/3</p>
                          <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>类别: {data.category}</p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Scatter
                  name="难度因素"
                  data={factorsData}
                  fill="#2d5a3d"
                  shape="circle"
                  r={28}
                >
                  {factorsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getCategoryColor(entry.category)} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-3" style={{ marginTop: '20px' }}>
              <span className="badge" style={{ backgroundColor: '#2d5a3d', color: 'white', borderRadius: '50px', padding: '6px 16px' }}>推理复杂</span>
              <span className="badge" style={{ backgroundColor: '#10b981', color: 'white', borderRadius: '50px', padding: '6px 16px' }}>知识跨度</span>
              <span className="badge" style={{ backgroundColor: '#5a9a6d', color: 'white', borderRadius: '50px', padding: '6px 16px' }}>信息隐藏</span>
              <span className="badge" style={{ backgroundColor: '#f59e0b', color: 'white', borderRadius: '50px', padding: '6px 16px' }}>陌生情境</span>
            </div>
          </div>
        </div>
      )}

      {/* 题目标签云（使用条形图模拟） */}
      {tagsData.length > 0 && (
        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'var(--macaron-purple-light)',
            marginBottom: '32px',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '32px' }}>
            <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
              <Tags size={18} className="inline mr-1" /> 题目特征标签（Top 20）
            </h3>
            <div style={{ background: '#fff', borderRadius: '16px', padding: '20px' }}>
              <ResponsiveContainer width="100%" height={360}>
                <BarChart data={tagsData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8e4" />
                  <XAxis type="number" label={{ value: '出现次数', position: 'insideBottom', offset: -5 }} />
                  <YAxis type="category" dataKey="name" width={120} />
                  <Tooltip
                    contentStyle={{ borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}
                  />
                  <Bar dataKey="count" fill="#2d5a3d" name="出现次数" radius={[0, 8, 8, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* 知识点教材分布 */}
      {textbookDistData.length > 0 && (
        <div
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-sm)',
            background: 'var(--color-bg)',
            marginBottom: '32px',
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '32px' }}>
            <h3 className="section-title text-lg" style={{ marginBottom: '24px' }}>
              <Library size={18} className="inline mr-1" /> 知识点教材分布（五本教材覆盖情况）
            </h3>

            {/* 总览饼图 */}
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={textbookDistData}
                  dataKey="score"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={95}
                  label={({ name, percentage }) => `${name} ${percentage}%`}
                  labelLine
                >
                  {textbookDistData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload
                      return (
                        <div style={{ background: '#fff', padding: '14px 18px', borderRadius: '14px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-md)' }}>
                          <p className="font-semibold" style={{ color: data.fill }}>
                            {data.name}
                          </p>
                          <p className="text-sm" style={{ color: 'var(--color-primary)' }}>加权分值: {data.score.toFixed(1)}分</p>
                          <p className="text-sm" style={{ color: 'var(--color-primary)' }}>占比: {data.percentage}%</p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
              </PieChart>
            </ResponsiveContainer>

            {/* 各教材章节分布（折叠列表） */}
            <div style={{ marginTop: '32px' }}>
              <p className="font-semibold text-sm" style={{ color: 'var(--color-secondary)', marginBottom: '16px' }}>
                各教材章节分布详情（点击展开）
              </p>
              {Object.entries(knowledge_textbook_distribution || {}).map(([textbook, data]) => {
                const tbScore = data.weighted_score ?? data.count ?? 0
                if (tbScore === 0) return null

                const chapters = Object.entries(data.chapters || {}).map(([chNum, chData]) => ({
                  number: chNum,
                  name: chData.name,
                  score: chData.weighted_score ?? chData.count ?? 0,
                }))

                return (
                  <Collapsible
                    key={textbook}
                    title={textbook}
                    badge={`${tbScore.toFixed(1)}分`}
                    badgeColor={textbookColors[textbook]}
                    barColor={textbookColors[textbook]}
                    percentage={data.percentage}
                  >
                    {chapters.length > 0 ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {chapters.map(ch => (
                          <div
                            key={ch.number}
                            style={{
                              padding: '18px 20px',
                              borderRadius: '16px',
                              border: '1px solid var(--color-border-light)',
                              backgroundColor: `${textbookColors[textbook]}08`,
                              boxShadow: 'var(--shadow-sm)',
                              transition: 'var(--transition)',
                            }}
                            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--macaron-mint)'; e.currentTarget.style.transform = 'translateY(-2px)' }}
                            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--color-border-light)'; e.currentTarget.style.transform = 'translateY(0)' }}
                          >
                            <p className="font-medium text-sm" style={{ color: 'var(--color-primary)' }}>
                              {ch.number} {ch.name}
                            </p>
                            <p
                              className="font-bold text-lg"
                              style={{ color: textbookColors[textbook], marginTop: '6px' }}
                            >
                              {ch.score.toFixed(1)}分
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
                        暂无章节数据
                      </p>
                    )}
                  </Collapsible>
                )
              })}
            </div>

            <div style={{ marginTop: '24px', padding: '16px 20px', background: 'var(--macaron-mint-light)', borderRadius: '14px' }}>
              <p className="text-sm" style={{ color: 'var(--color-secondary)' }}>
                <strong>说明：</strong>知识点已按题目分值加权映射到教材章节。高分题的知识点获得更高权重，
                更准确反映试卷对各教材的考查力度。
              </p>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

export default ExamStatisticsEnhanced
