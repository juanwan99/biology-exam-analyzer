import { TrendingUp, BarChart3 as BarChartIcon, Brain, Crosshair, Tags, Library } from 'lucide-react'
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar } from 'recharts'
import { Card, CardContent, Typography, Grid, Box, Chip, Accordion, AccordionSummary, AccordionDetails, Paper } from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ScorePrediction from './ScorePrediction'

// 气泡脉动动画样式（统一光晕大小）
const bubbleAnimationStyle = `
  @keyframes bubbleGlow {
    0%, 100% {
      filter: drop-shadow(0 0 6px rgba(59, 130, 246, 0.5));
      opacity: 0.85;
    }
    50% {
      filter: drop-shadow(0 0 10px rgba(59, 130, 246, 0.8));
      opacity: 1;
    }
  }

  .bubble-container .recharts-scatter-symbol {
    animation: bubbleGlow 3s ease-in-out infinite;
  }
`;

function ExamStatisticsEnhanced({ data, questions, scorePrediction }) {
  if (!data) return null

  const {
    difficulty_distribution,
    difficulty_distribution_by_score,  // 新增：分值分布数据
    difficulty_curve,
    avg_difficulty,
    avg_cognitive_level,
    top_knowledge_points,
    knowledge_textbook_distribution,  // v3.1新增：教材分布数据
    competency_distribution
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

  // 知识点数据（取前10，保留兼容性）
  const knowledgePointsData = top_knowledge_points ? top_knowledge_points.slice(0, 10) : []

  // v3.1新增：教材分布数据处理
  const textbookColors = {
    '必修1': '#10b981',
    '必修2': '#3b82f6',
    '选择性必修1': '#8b5cf6',
    '选择性必修2': '#f59e0b',
    '选择性必修3': '#ef4444'
  }

  const textbookDistData = knowledge_textbook_distribution ? [
    {
      name: '必修1',
      count: knowledge_textbook_distribution['必修1']?.count || 0,
      percentage: knowledge_textbook_distribution['必修1']?.percentage || 0,
      fill: textbookColors['必修1']
    },
    {
      name: '必修2',
      count: knowledge_textbook_distribution['必修2']?.count || 0,
      percentage: knowledge_textbook_distribution['必修2']?.percentage || 0,
      fill: textbookColors['必修2']
    },
    {
      name: '选修1',
      count: knowledge_textbook_distribution['选择性必修1']?.count || 0,
      percentage: knowledge_textbook_distribution['选择性必修1']?.percentage || 0,
      fill: textbookColors['选择性必修1']
    },
    {
      name: '选修2',
      count: knowledge_textbook_distribution['选择性必修2']?.count || 0,
      percentage: knowledge_textbook_distribution['选择性必修2']?.percentage || 0,
      fill: textbookColors['选择性必修2']
    },
    {
      name: '选修3',
      count: knowledge_textbook_distribution['选择性必修3']?.count || 0,
      percentage: knowledge_textbook_distribution['选择性必修3']?.percentage || 0,
      fill: textbookColors['选择性必修3']
    }
  ].filter(item => item.count > 0) : []

  // 素养分布数据转换（使用总权重而非题目数，因为一道题可能涉及多种素养）
  const competencyData = competency_distribution ? [
    { name: '生命观念', count: competency_distribution['生命观念']?.总权重 || 0, fill: '#10b981' },
    { name: '科学思维', count: competency_distribution['科学思维']?.总权重 || 0, fill: '#3b82f6' },
    { name: '科学探究', count: competency_distribution['科学探究']?.总权重 || 0, fill: '#8b5cf6' },
    { name: '社会责任', count: competency_distribution['社会责任']?.总权重 || 0, fill: '#f97316' }
  ] : []

  // 核心素养细分维度数据处理
  const competencyColors = {
    '生命观念': '#10b981',
    '科学思维': '#3b82f6',
    '科学探究': '#8b5cf6',
    '社会责任': '#f97316'
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

  const COGNITIVE_COLORS = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899']

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
      '推理复杂': '#3b82f6',   // 蓝色 - 更柔和
      '知识跨度': '#10b981',   // 绿色 - 更柔和
      '信息隐藏': '#a855f7',   // 紫色 - 更柔和
      '陌生情境': '#f59e0b'    // 橙色 - 保持
    }
    return colors[category] || '#6b7280'
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
    <div className="mb-12">
      <Typography variant="h5" className="mb-6 font-bold text-gray-800">
        整卷质量分析（增强版）
      </Typography>

      {/* 分数预估（如果有数据） */}
      {scorePrediction && (
        <div className="mb-6">
          <ScorePrediction prediction={scorePrediction} />
        </div>
      )}

      {/* 关键指标卡片 */}
      <Grid container spacing={3} className="mb-8">
        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                平均难度系数
              </Typography>
              <Typography variant="h3" component="div" className="text-[#1a2e1f] font-bold">
                {avg_difficulty !== undefined ? avg_difficulty.toFixed(2) : 'N/A'}
              </Typography>
              <Typography variant="body1" color="text.secondary" className="mt-2">
                满分10分制 • {avg_difficulty <= 3.5 ? '偏简单' : avg_difficulty <= 6.5 ? '适中' : '偏困难'}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography color="text.secondary" gutterBottom>
                平均认知层级
              </Typography>
              <Typography variant="h3" component="div" className="text-[#2d5a3d] font-bold">
                {avg_cognitive_level !== undefined ? avg_cognitive_level.toFixed(2) : 'N/A'}
              </Typography>
              <Typography variant="body1" color="text.secondary" className="mt-2">
                满分10分制 • 布鲁姆认知层级评估
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* 难度曲线图 */}
      {difficulty_curve && difficulty_curve.length > 0 && (
        <Card elevation={2} className="mb-6">
          <CardContent>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              <TrendingUp size={18} className="inline mr-1" /> 难度曲线（题目顺序）
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={difficulty_curve}>
                <CartesianGrid strokeDasharray="3 3" />
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
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="difficulty"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  name="难度系数"
                  dot={{ fill: '#3b82f6', r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
            <Typography variant="body1" color="text.secondary" className="mt-2 block text-center">
              建议：试卷难度应呈阶梯式上升，避免大幅波动
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* 双列布局：难度分布（分值） + 认知层级分布 */}
      <Grid container spacing={3} className="mb-6">
        {/* 难度分值分布柱状图（新增） */}
        <Grid item xs={12} md={6}>
          {hasScoreData && (
            <Card elevation={2} style={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
                  <BarChartIcon size={18} className="inline mr-1" /> 难度分值分布（细粒度）
                </Typography>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={difficultyScoreData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis label={{ value: '总分值', angle: -90, position: 'insideLeft' }} />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload
                          return (
                            <div className="bg-white p-3 border border-gray-300 rounded shadow">
                              <p className="font-semibold" style={{ color: data.fill }}>
                                {data.name}
                              </p>
                              <p className="text-lg">分值: {data.score.toFixed(1)}分</p>
                              <p className="text-lg">占比: {data.percentage}%</p>
                            </div>
                          )
                        }
                        return null
                      }}
                    />
                    <Bar dataKey="score" name="总分值">
                      {difficultyScoreData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
                <Box className="mt-4 p-3 bg-[#e8f8ee] rounded">
                  <Typography variant="body1" color="text.secondary">
                    <strong>理想比例：</strong>简单 30% • 中等 50% • 困难 20%
                  </Typography>
                  <Box className="mt-2 flex gap-4">
                    {difficultyScoreData.map(item => (
                      <Typography key={item.name} variant="body1" color="text.secondary">
                        {item.name}: {item.score.toFixed(1)}分 ({item.percentage}%)
                      </Typography>
                    ))}
                  </Box>
                </Box>
              </CardContent>
            </Card>
          )}
        </Grid>

        {/* 认知层级饼图（新增） */}
        <Grid item xs={12} md={6}>
          {cognitivePieData.length > 0 && (
            <Card elevation={2} style={{ height: '100%' }}>
              <CardContent>
                <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
                  <Brain size={18} className="inline mr-1" /> 认知层级分布（布鲁姆分类法）
                </Typography>
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={cognitivePieData}
                      cx="50%"
                      cy="50%"
                      labelLine={true}
                      label={(entry) => `${entry.name} ${entry.value}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {cognitivePieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COGNITIVE_COLORS[index % COGNITIVE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <Box className="mt-4 p-3 bg-[#f3f0ff] rounded">
                  <Typography variant="body1" color="text.secondary">
                    <strong>专业提示：</strong>高阶思维（分析/综合/评价）占比建议 ≥ 50%
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          )}
        </Grid>
      </Grid>

      {/* 难度因素气泡图（新增） */}
      {factorsData.length > 0 && (
        <Card elevation={2} className="mb-6">
          <CardContent>
            <style>{bubbleAnimationStyle}</style>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              <Crosshair size={18} className="inline mr-1" /> 难度因素分布（气泡大小 = 出现频次）
            </Typography>
            <ResponsiveContainer width="100%" height={350} className="bubble-container">
              <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" />
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
                        <div className="bg-white p-3 border border-gray-300 rounded shadow">
                          <p className="font-semibold">{data.factor}</p>
                          <p className="text-lg text-gray-600">出现次数: {data.count}</p>
                          <p className="text-lg text-gray-600">平均影响: {data.avgImpact.toFixed(1)}/3</p>
                          <p className="text-lg text-gray-600">类别: {data.category}</p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Scatter
                  name="难度因素"
                  data={factorsData}
                  fill="#8884d8"
                  shape="circle"
                  r={28}
                >
                  {factorsData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={getCategoryColor(entry.category)} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <Box className="mt-4 flex flex-wrap gap-2">
              <Chip label="推理复杂" size="small" style={{ backgroundColor: '#3b82f6', color: 'white' }} />
              <Chip label="知识跨度" size="small" style={{ backgroundColor: '#10b981', color: 'white' }} />
              <Chip label="信息隐藏" size="small" style={{ backgroundColor: '#a855f7', color: 'white' }} />
              <Chip label="陌生情境" size="small" style={{ backgroundColor: '#f59e0b', color: 'white' }} />
            </Box>
          </CardContent>
        </Card>
      )}

      {/* 题目标签云（新增，使用条形图模拟） */}
      {tagsData.length > 0 && (
        <Card elevation={2} className="mb-6">
          <CardContent>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              <Tags size={18} className="inline mr-1" /> 题目特征标签（Top 20）
            </Typography>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={tagsData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" label={{ value: '出现次数', position: 'insideBottom', offset: -5 }} />
                <YAxis type="category" dataKey="name" width={120} />
                <Tooltip />
                <Bar dataKey="count" fill="#3b82f6" name="出现次数" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* 知识点教材分布（v3.1新增，替换原Top 10展示） */}
      {textbookDistData.length > 0 && (
        <Card elevation={2} className="mb-6">
          <CardContent>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              <Library size={18} className="inline mr-1" /> 知识点教材分布（五本教材覆盖情况）
            </Typography>

            {/* 总览饼图 */}
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={textbookDistData}
                  dataKey="count"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
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
                        <div className="bg-white p-3 border border-gray-300 rounded shadow">
                          <p className="font-semibold" style={{ color: data.fill }}>
                            {data.name}
                          </p>
                          <p className="text-lg">知识点数: {data.count}</p>
                          <p className="text-lg">占比: {data.percentage}%</p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
              </PieChart>
            </ResponsiveContainer>

            {/* 各教材章节分布（折叠列表） */}
            <Box className="mt-6">
              <Typography variant="subtitle1" className="mb-3 text-gray-600 font-semibold">
                各教材章节分布详情（点击展开）
              </Typography>
              {Object.entries(knowledge_textbook_distribution || {}).map(([textbook, data]) => {
                if (data.count === 0) return null

                const chapters = Object.entries(data.chapters || {}).map(([chNum, chData]) => ({
                  number: chNum,
                  name: chData.name,
                  count: chData.count
                }))

                return (
                  <Accordion key={textbook} className="mb-2">
                    <AccordionSummary
                      expandIcon={<ExpandMoreIcon />}
                      style={{ backgroundColor: `${textbookColors[textbook]}10` }}
                    >
                      <Box className="flex items-center justify-between w-full pr-4">
                        <Box className="flex items-center gap-3">
                          <Box
                            style={{
                              width: 4,
                              height: 24,
                              backgroundColor: textbookColors[textbook],
                              borderRadius: 2
                            }}
                          />
                          <Typography className="font-semibold">{textbook}</Typography>
                        </Box>
                        <Box className="flex gap-3 items-center">
                          <Chip
                            label={`${data.count}个知识点`}
                            size="small"
                            style={{
                              backgroundColor: textbookColors[textbook],
                              color: 'white'
                            }}
                          />
                          <Typography variant="body1" color="text.secondary">
                            占比: {data.percentage}%
                          </Typography>
                        </Box>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      {chapters.length > 0 ? (
                        <Grid container spacing={2}>
                          {chapters.map(ch => (
                            <Grid item xs={12} md={6} key={ch.number}>
                              <Paper
                                className="p-3 hover:shadow-md transition-shadow cursor-default"
                                style={{ backgroundColor: `${textbookColors[textbook]}05` }}
                              >
                                <Typography variant="body1" className="font-medium text-gray-700">
                                  {ch.number} {ch.name}
                                </Typography>
                                <Typography
                                  variant="h6"
                                  style={{ color: textbookColors[textbook] }}
                                  className="font-bold mt-1"
                                >
                                  {ch.count}个知识点
                                </Typography>
                              </Paper>
                            </Grid>
                          ))}
                        </Grid>
                      ) : (
                        <Typography variant="body1" color="text.secondary">
                          暂无章节数据
                        </Typography>
                      )}
                    </AccordionDetails>
                  </Accordion>
                )
              })}
            </Box>

            <Box className="mt-4 p-3 bg-[#e8f8ee] rounded">
              <Typography variant="body1" color="text.secondary">
                <strong>说明：</strong>知识点已自动映射到对应教材章节，帮助教师全面把握试卷在五本教材中的分布情况，
                确保知识点覆盖的均衡性和全面性。
              </Typography>
            </Box>
          </CardContent>
        </Card>
      )}

    </div>
  )
}

export default ExamStatisticsEnhanced
