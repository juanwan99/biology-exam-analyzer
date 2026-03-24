import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { Card, CardContent, Typography, Grid, Box } from '@mui/material'

function ExamStatistics({ data }) {
  if (!data) return null

  const {
    difficulty_distribution,
    difficulty_curve,
    avg_difficulty,
    avg_cognitive_level,
    top_knowledge_points,
    competency_distribution
  } = data

  // 难度分布数据转换为recharts格式
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

  // 知识点数据（取前10）
  const knowledgePointsData = top_knowledge_points ? top_knowledge_points.slice(0, 10) : []

  // 素养分布数据转换
  const competencyData = competency_distribution ? [
    { name: '生命观念', count: competency_distribution['生命观念']?.count || 0, fill: '#10b981' },
    { name: '科学思维', count: competency_distribution['科学思维']?.count || 0, fill: '#3b82f6' },
    { name: '科学探究', count: competency_distribution['科学探究']?.count || 0, fill: '#8b5cf6' },
    { name: '社会责任', count: competency_distribution['社会责任']?.count || 0, fill: '#f97316' }
  ] : []

  return (
    <div className="mb-12">
      <Typography variant="h5" className="mb-6 font-bold text-gray-800">
        整卷质量分析
      </Typography>

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
              <Typography variant="body2" color="text.secondary" className="mt-2">
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
              <Typography variant="body2" color="text.secondary" className="mt-2">
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
              难度曲线（题目顺序）
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
            <Typography variant="caption" color="text.secondary" className="mt-2 block text-center">
              建议：试卷难度应呈阶梯式上升，避免大幅波动
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* 难度分布 */}
      {difficultyDistData.length > 0 && (
        <Card elevation={2} className="mb-6">
          <CardContent>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              难度分布统计
            </Typography>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={difficultyDistData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis label={{ value: '题目数量', angle: -90, position: 'insideLeft' }} />
                <Tooltip
                  formatter={(value, name, props) => {
                    if (name === "题目数量") {
                      return [`${value}题 (${props.payload.percentage}%)`, name]
                    }
                    return [value, name]
                  }}
                />
                <Legend />
                <Bar dataKey="count" name="题目数量">
                  {difficultyDistData.map((entry, index) => (
                    <Bar key={`cell-${index}`} dataKey="count" fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <Box className="mt-4 p-3 bg-[#e8f8ee] rounded">
              <Typography variant="body2" color="text.secondary">
                <strong>理想比例：</strong>简单 30% • 中等 50% • 困难 20%（可根据考试目标调整）
              </Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* 知识点分布 */}
      {knowledgePointsData.length > 0 && (
        <Card elevation={2} className="mb-6">
          <CardContent>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              Top 10 知识点覆盖
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={knowledgePointsData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" label={{ value: '出现次数', position: 'insideBottom', offset: -5 }} />
                <YAxis type="category" dataKey="name" width={150} />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" fill="#8b5cf6" name="出现次数" />
              </BarChart>
            </ResponsiveContainer>
            <Typography variant="caption" color="text.secondary" className="mt-2 block">
              知识点覆盖度：{knowledgePointsData.length} 个核心知识点
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* 核心素养分布 */}
      {competencyData.length > 0 && (
        <Card elevation={2}>
          <CardContent>
            <Typography variant="h6" className="mb-4 font-semibold text-gray-700">
              核心素养分布
            </Typography>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={competencyData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis label={{ value: '题目数量', angle: -90, position: 'insideLeft' }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="count" name="题目数量">
                  {competencyData.map((entry, index) => (
                    <Bar key={`cell-${index}`} dataKey="count" fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <Box className="mt-4 p-3 bg-green-50 rounded">
              <Typography variant="body2" color="text.secondary">
                <strong>新课标要求：</strong>四大核心素养应均衡考查，避免单一素养占比过高
              </Typography>
            </Box>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default ExamStatistics
