function ResultDisplay({ data }) {
  if (!data || !data.questions) return null

  // 渲染结构化内容（段落、表格、图片）
  const renderStructuredContent = (elements) => {
    if (!elements || !Array.isArray(elements)) return null

    return elements.map((element, idx) => {
      switch (element.type) {
        case 'paragraph':
          return (
            <p key={idx} className="mb-3 text-gray-800">
              {element.content}
            </p>
          )

        case 'table':
          return (
            <div key={idx} className="mb-4 overflow-x-auto">
              <div
                dangerouslySetInnerHTML={{ __html: element.html }}
                className="word-table-container"
              />
            </div>
          )

        case 'image':
          return (
            <div key={idx} className="mb-4 flex justify-center">
              <img
                src={`data:image/${element.format?.toLowerCase() || 'jpeg'};base64,${element.base64}`}
                alt={element.caption || `图片 ${element.index + 1}`}
                className="max-w-2xl w-auto h-auto rounded border border-gray-200"
                style={{ maxHeight: '500px' }}
              />
              {element.caption && (
                <p className="text-sm text-gray-500 mt-1 text-center">{element.caption}</p>
              )}
            </div>
          )

        default:
          return null
      }
    })
  }

  return (
    <div className="mt-12 max-w-7xl mx-auto">
      <div className="bg-white shadow rounded-lg p-8">
        {/* 统计信息 */}
        <div className="mb-8 grid grid-cols-4 gap-4">
          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">题目总数</div>
            <div className="text-3xl font-bold text-blue-600">{data.total_count}</div>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">处理耗时</div>
            <div className="text-3xl font-bold text-green-600">
              {data.processing_time.toFixed(1)}s
            </div>
          </div>
          <div className="bg-purple-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">评估模式</div>
            <div className="text-2xl font-bold text-purple-600">
              {data.mode === 'fast' ? '🚄 快速' : '🔬 深度'}
            </div>
          </div>
          <div className="bg-orange-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">平均耗时</div>
            <div className="text-3xl font-bold text-orange-600">
              {(data.processing_time / data.total_count).toFixed(1)}s
            </div>
          </div>
        </div>

        {/* 报告下载按钮 */}
        {data.report_url && (
          <div className="mb-8 p-6 bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-1">
                  📊 质量评估报告已生成
                </h3>
                <p className="text-sm text-gray-600">
                  包含难度曲线、素养分布等6张可视化图表
                </p>
              </div>
              <a
                href={data.report_url}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                下载PDF报告
              </a>
            </div>
          </div>
        )}

        {/* 素养分布汇总 */}
        {data.competency_summary && (
          <div className="mb-8 p-6 bg-gradient-to-r from-green-50 to-teal-50 border border-green-200 rounded-lg">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              🎯 核心素养分布
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {data.competency_summary['生命观念'] && (
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-sm text-gray-600">生命观念</div>
                  <div className="text-2xl font-bold text-green-600">
                    {data.competency_summary['生命观念'].count}题
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {data.competency_summary['生命观念'].percentage?.toFixed(1)}%
                  </div>
                </div>
              )}
              {data.competency_summary['科学思维'] && (
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-sm text-gray-600">科学思维</div>
                  <div className="text-2xl font-bold text-blue-600">
                    {data.competency_summary['科学思维'].count}题
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {data.competency_summary['科学思维'].percentage?.toFixed(1)}%
                  </div>
                </div>
              )}
              {data.competency_summary['科学探究'] && (
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-sm text-gray-600">科学探究</div>
                  <div className="text-2xl font-bold text-purple-600">
                    {data.competency_summary['科学探究'].count}题
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {data.competency_summary['科学探究'].percentage?.toFixed(1)}%
                  </div>
                </div>
              )}
              {data.competency_summary['社会责任'] && (
                <div className="bg-white p-4 rounded-lg shadow-sm">
                  <div className="text-sm text-gray-600">社会责任</div>
                  <div className="text-2xl font-bold text-orange-600">
                    {data.competency_summary['社会责任'].count}题
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {data.competency_summary['社会责任'].percentage?.toFixed(1)}%
                  </div>
                </div>
              )}
            </div>
            {data.competency_summary.primary_competency && (
              <div className="mt-4 text-sm text-gray-600">
                主要素养: <span className="font-semibold text-gray-900">
                  {data.competency_summary.primary_competency}
                </span>
              </div>
            )}
          </div>
        )}

        {/* 题目列表 */}
        <div className="space-y-6">
          {data.questions.map((question, index) => (
            <div
              key={question.id || index}
              className="border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-4">
                <h3 className="text-xl font-semibold text-gray-900">
                  题目 {question.id || index + 1}
                </h3>
                <div className="flex gap-2">
                  {/* 难度评分 */}
                  {question.difficulty?.final_difficulty && (
                    <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-medium">
                      难度: {question.difficulty.final_difficulty.toFixed(1)}/10
                    </span>
                  )}
                  {/* 原有难度标签（兼容） */}
                  {question.analysis?.difficulty && !question.difficulty?.final_difficulty && (
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium ${
                        question.analysis.difficulty === '简单'
                          ? 'bg-green-100 text-green-800'
                          : question.analysis.difficulty === '中等'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {question.analysis.difficulty}
                    </span>
                  )}
                  {/* 主要素养 */}
                  {question.competency?.primary_competency && (
                    <span className="px-3 py-1 bg-purple-100 text-purple-800 rounded-full text-sm font-medium">
                      {question.competency.primary_competency}
                    </span>
                  )}
                </div>
              </div>

              {/* 题目内容 */}
              <div className="mb-4 p-4 bg-gray-50 rounded">
                {/* 题干文字（始终显示） */}
                <p className="text-gray-800 whitespace-pre-wrap mb-4">{question.content}</p>

                {/* 结构化内容（表格和图片，如果存在则追加显示） */}
                {question.structured_content && question.structured_content.length > 0 && (
                  <div className="structured-content mt-4 border-t border-gray-200 pt-4">
                    {renderStructuredContent(question.structured_content)}
                  </div>
                )}
              </div>

              {/* 分析结果 */}
              {question.analysis && (
                <div className="space-y-3">
                  {/* 难度详情（新增） */}
                  {question.difficulty && !question.difficulty.error && (
                    <div>
                      <h4 className="font-semibold text-gray-700 mb-2">难度评估</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
                        {question.difficulty.knowledge_complexity !== undefined && (
                          <div className="bg-blue-50 p-2 rounded text-sm">
                            <div className="text-gray-600">知识复杂度</div>
                            <div className="font-semibold text-blue-700">
                              {question.difficulty.knowledge_complexity.toFixed(1)}/10
                            </div>
                          </div>
                        )}
                        {question.difficulty.cognitive_level !== undefined && (
                          <div className="bg-green-50 p-2 rounded text-sm">
                            <div className="text-gray-600">认知层级</div>
                            <div className="font-semibold text-green-700">
                              {question.difficulty.cognitive_level.toFixed(1)}/10
                            </div>
                          </div>
                        )}
                        {question.difficulty.information_extraction !== undefined && (
                          <div className="bg-purple-50 p-2 rounded text-sm">
                            <div className="text-gray-600">信息提取</div>
                            <div className="font-semibold text-purple-700">
                              {question.difficulty.information_extraction.toFixed(1)}/10
                            </div>
                          </div>
                        )}
                        {question.difficulty.reasoning_steps !== undefined && (
                          <div className="bg-orange-50 p-2 rounded text-sm">
                            <div className="text-gray-600">推理步骤</div>
                            <div className="font-semibold text-orange-700">
                              {question.difficulty.reasoning_steps.toFixed(1)}/10
                            </div>
                          </div>
                        )}
                      </div>
                      {question.difficulty.difficulty_factors && question.difficulty.difficulty_factors.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-2">
                          {question.difficulty.difficulty_factors.map((factor, idx) => (
                            <span key={idx} className="px-2 py-1 bg-red-50 text-red-700 rounded text-xs">
                              {factor}
                            </span>
                          ))}
                        </div>
                      )}
                      {question.difficulty.estimated_solve_time && (
                        <p className="text-sm text-gray-600">
                          预计解题时间: {question.difficulty.estimated_solve_time}
                        </p>
                      )}
                    </div>
                  )}

                  {/* 素养详情（新增） */}
                  {question.competency && !question.competency.error && (
                    <div>
                      <h4 className="font-semibold text-gray-700 mb-2">核心素养</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        {question.competency['生命观念']?.涉及 && (
                          <div className="bg-green-50 p-2 rounded text-sm border border-green-200">
                            <div className="text-gray-600">生命观念</div>
                            <div className="font-semibold text-green-700">
                              权重: {(question.competency['生命观念'].权重 * 100).toFixed(0)}%
                            </div>
                          </div>
                        )}
                        {question.competency['科学思维']?.涉及 && (
                          <div className="bg-blue-50 p-2 rounded text-sm border border-blue-200">
                            <div className="text-gray-600">科学思维</div>
                            <div className="font-semibold text-blue-700">
                              权重: {(question.competency['科学思维'].权重 * 100).toFixed(0)}%
                            </div>
                          </div>
                        )}
                        {question.competency['科学探究']?.涉及 && (
                          <div className="bg-purple-50 p-2 rounded text-sm border border-purple-200">
                            <div className="text-gray-600">科学探究</div>
                            <div className="font-semibold text-purple-700">
                              权重: {(question.competency['科学探究'].权重 * 100).toFixed(0)}%
                            </div>
                          </div>
                        )}
                        {question.competency['社会责任']?.涉及 && (
                          <div className="bg-orange-50 p-2 rounded text-sm border border-orange-200">
                            <div className="text-gray-600">社会责任</div>
                            <div className="font-semibold text-orange-700">
                              权重: {(question.competency['社会责任'].权重 * 100).toFixed(0)}%
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 知识点 */}
                  {question.analysis.knowledge_points && (
                    <div>
                      <h4 className="font-semibold text-gray-700 mb-2">知识点</h4>
                      <div className="flex flex-wrap gap-2">
                        {question.analysis.knowledge_points.map((point, idx) => (
                          <span
                            key={idx}
                            className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm"
                          >
                            {point}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 详细解析 */}
                  {question.analysis.detailed_analysis && (
                    <div>
                      <h4 className="font-semibold text-gray-700 mb-2">详细解析</h4>
                      <p className="text-gray-600 whitespace-pre-wrap">
                        {question.analysis.detailed_analysis}
                      </p>
                    </div>
                  )}

                  {/* 答案 */}
                  {question.analysis.answer && (
                    <div>
                      <h4 className="font-semibold text-gray-700 mb-2">参考答案</h4>
                      <p className="text-gray-600">{question.analysis.answer}</p>
                    </div>
                  )}

                  {/* 易错点 */}
                  {question.analysis.common_mistakes && (
                    <div>
                      <h4 className="font-semibold text-gray-700 mb-2">易错点</h4>
                      <ul className="list-disc list-inside text-gray-600 space-y-1">
                        {question.analysis.common_mistakes.map((mistake, idx) => (
                          <li key={idx}>{mistake}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* 原始JSON（可折叠） */}
              <details className="mt-4">
                <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700">
                  查看原始数据
                </summary>
                <pre className="mt-2 p-4 bg-gray-900 text-green-400 rounded text-xs overflow-auto">
                  {JSON.stringify(question, null, 2)}
                </pre>
              </details>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default ResultDisplay
