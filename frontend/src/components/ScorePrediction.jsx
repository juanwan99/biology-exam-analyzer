import { useState } from 'react'
import { Crosshair, AlertTriangle } from 'lucide-react'
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

/**
 * 分数预估展示组件
 *
 * 展示基于历史数据的分数预估结果
 */
function ScorePrediction({ prediction }) {
  const [showDetails, setShowDetails] = useState(false)
  const [showChart, setShowChart] = useState(false)

  if (!prediction) return null

  const {
    predicted_average,
    predicted_rate,
    confidence_interval,
    reliability_score,
    per_question_predictions,
    warnings,
    grade,
    total_score
  } = prediction

  // 可靠度颜色 (momowan palette)
  const getReliabilityColor = (score) => {
    if (score >= 0.8) return 'text-[#2d5a3d]'
    if (score >= 0.6) return 'text-[#92400e]'
    return 'text-[#991b1b]'
  }

  // 可靠度背景色 (momowan palette)
  const getReliabilityBgColor = (score) => {
    if (score >= 0.8) return 'bg-[#2d5a3d]'
    if (score >= 0.6) return 'bg-[#f59e0b]'
    return 'bg-[#dc3545]'
  }

  // 准备散点图数据（难度-得分率）
  const scatterData = per_question_predictions?.map((q) => ({
    difficulty: q.difficulty,
    predicted_rate: q.predicted_rate * 100,
    question_number: q.question_number,
    question_score: q.question_score
  })) || []

  return (
    <div className="bg-gradient-to-br from-[#e8f8ee] to-[#c8f0d4] rounded-xl p-6 border border-[#e2e8e4]">
      {/* 标题 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center">
          <Crosshair size={24} className="mr-2 text-[#2d5a3d]" />
          <h3 className="text-lg font-semibold text-[#1a2e1f]">预估分数</h3>
          <span className="ml-2 px-2 py-0.5 bg-[#ede9fe] text-[#2d5a3d] text-xs rounded-full">Beta</span>
        </div>
        {grade && (
          <span className="text-sm text-[#5a6b5e]">适用年级: {grade}</span>
        )}
      </div>

      {/* 主要预估结果 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {/* 预估均分 */}
        <div className="bg-white rounded-xl p-4 border border-[#f0f4f1]">
          <div className="text-center">
            <div className="text-3xl font-bold text-[#2d5a3d]">
              {predicted_average?.toFixed(1)}
            </div>
            <div className="text-sm text-[#5a6b5e] mt-1">预估均分</div>
            {total_score && (
              <div className="text-xs text-[#8a9a8e] mt-1">满分 {total_score}</div>
            )}
          </div>
        </div>

        {/* 置信区间 */}
        <div className="bg-white rounded-xl p-4 border border-[#f0f4f1]">
          <div className="text-center">
            <div className="text-xl font-semibold text-[#1a2e1f]">
              {confidence_interval?.[0]?.toFixed(1)} - {confidence_interval?.[1]?.toFixed(1)}
            </div>
            <div className="text-sm text-[#5a6b5e] mt-1">95% 置信区间</div>
            <div className="text-xs text-[#8a9a8e] mt-1">
              预估得分率: {((predicted_rate || 0) * 100).toFixed(1)}%
            </div>
          </div>
        </div>

        {/* 可靠度 */}
        <div className="bg-white rounded-xl p-4 border border-[#f0f4f1]">
          <div className="text-center">
            <div className={`text-xl font-semibold ${getReliabilityColor(reliability_score)}`}>
              {(reliability_score || 0) < 0.3 ? '冷启动' : `${((reliability_score || 0) * 100).toFixed(0)}%`}
            </div>
            <div className="text-sm text-[#5a6b5e] mt-1">预估可靠度</div>
            {(reliability_score || 0) < 0.3 && (
              <div className="text-xs text-[#8a9a8e] mt-1">暂无历史数据，基于经验值预估</div>
            )}
            {/* 进度条 */}
            <div className="mt-2 h-2 bg-[#e2e8e4] rounded-full overflow-hidden">
              <div
                className={`h-full ${getReliabilityBgColor(reliability_score)} transition-all duration-500`}
                style={{ width: `${Math.max((reliability_score || 0) * 100, 5)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 警告信息 */}
      {warnings && warnings.length > 0 && (
        <div className="bg-[#fdf6e3] border border-[#fef3c7] rounded-xl p-3 mb-4">
          <div className="flex items-start">
            <AlertTriangle size={16} className="text-[#f59e0b] mr-2 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-[#92400e]">
              <div className="font-medium mb-1">数据覆盖提示</div>
              <ul className="list-disc list-inside">
                {warnings.slice(0, 3).map((warning, idx) => (
                  <li key={idx}>{warning}</li>
                ))}
                {warnings.length > 3 && (
                  <li className="text-[#92400e]">还有 {warnings.length - 3} 条警告...</li>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* 展开/折叠按钮 */}
      <div className="flex space-x-4">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center text-sm text-[#2d5a3d] hover:text-[#0f1c13]"
        >
          <span className="mr-1">{showDetails ? '▼' : '▶'}</span>
          各题预估详情
        </button>
        <button
          onClick={() => setShowChart(!showChart)}
          className="flex items-center text-sm text-[#2d5a3d] hover:text-[#0f1c13]"
        >
          <span className="mr-1">{showChart ? '▼' : '▶'}</span>
          难度-得分率散点图
        </button>
      </div>

      {/* 各题预估详情 */}
      {showDetails && per_question_predictions && (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-[#e2e8e4] text-sm">
            <thead className="bg-[#f9fafb]">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-[#5a6b5e]">题号</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-[#5a6b5e]">难度</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-[#5a6b5e]">预估得分率</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-[#5a6b5e]">预估分数</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-[#5a6b5e]">置信区间</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-[#e2e8e4]">
              {per_question_predictions.map((q) => (
                <tr key={q.question_id} className="hover:bg-[#e8f8ee]">
                  <td className="px-3 py-2 font-medium">{q.question_number}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      q.difficulty <= 3.5 ? 'bg-[#e8f8ee] text-[#2d5a3d]' :
                      q.difficulty <= 6.5 ? 'bg-[#fdf6e3] text-[#92400e]' :
                      'bg-[#fef0f0] text-[#991b1b]'
                    }`}>
                      {q.difficulty?.toFixed(1)}
                    </span>
                  </td>
                  <td className="px-3 py-2">{((q.predicted_rate || 0) * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2">{q.predicted_score?.toFixed(2)} / {q.question_score}</td>
                  <td className="px-3 py-2 text-[#5a6b5e]">
                    {q.confidence_interval?.[0]?.toFixed(2)} - {q.confidence_interval?.[1]?.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 难度-得分率散点图 */}
      {showChart && scatterData.length > 0 && (
        <div className="mt-4 bg-white rounded-lg p-4">
          <h4 className="text-sm font-medium text-[#1a2e1f] mb-3">难度-得分率关系</h4>
          <ResponsiveContainer width="100%" height={300}>
            <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="difficulty"
                name="难度"
                domain={[0, 10]}
                label={{ value: '难度', position: 'bottom', offset: 0 }}
              />
              <YAxis
                type="number"
                dataKey="predicted_rate"
                name="预估得分率"
                domain={[0, 100]}
                unit="%"
                label={{ value: '得分率(%)', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload
                    return (
                      <div className="bg-white p-2 border border-[#e2e8e4] rounded-xl text-sm">
                        <p className="font-medium">题目 {data.question_number}</p>
                        <p>难度: {data.difficulty?.toFixed(1)}</p>
                        <p>预估得分率: {data.predicted_rate?.toFixed(1)}%</p>
                        <p>满分: {data.question_score}</p>
                      </div>
                    )
                  }
                  return null
                }}
              />
              <ReferenceLine y={70} stroke="#f59e0b" strokeDasharray="5 5" label="中等" />
              <ReferenceLine x={5} stroke="#888" strokeDasharray="3 3" />
              <Scatter
                name="题目"
                data={scatterData}
                fill="#2d5a3d"
                shape="circle"
              />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-xs text-[#5a6b5e] text-center mt-2">
            横轴为绝对难度(0-10)，纵轴为预估得分率(%)
          </p>
        </div>
      )}

      {/* 说明文字 */}
      <div className="mt-4 text-xs text-[#5a6b5e]">
        <p>* 预估结果基于历史考试数据的统计分析，仅供参考</p>
        <p>* 可靠度取决于历史数据覆盖程度，数据越多预估越准确</p>
      </div>
    </div>
  )
}

export default ScorePrediction
