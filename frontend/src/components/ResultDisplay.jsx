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
        <div className="mb-8 grid grid-cols-3 gap-4">
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
            <div className="text-sm text-gray-600">平均耗时</div>
            <div className="text-3xl font-bold text-purple-600">
              {(data.processing_time / data.total_count).toFixed(1)}s
            </div>
          </div>
        </div>

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
                {question.analysis?.difficulty && (
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
