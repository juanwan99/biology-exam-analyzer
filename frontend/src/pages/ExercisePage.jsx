import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'

function ExercisePage() {
  // 状态管理
  const [exercises, setExercises] = useState([])
  const [statistics, setStatistics] = useState(null)
  const [sources, setSources] = useState([])
  const [selectedExercise, setSelectedExercise] = useState(null)
  const [loading, setLoading] = useState(false)

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const pageSize = 20

  // 筛选条件
  const [filters, setFilters] = useState({
    question_type: '',
    year: '',
    tag: '',
    keyword: ''
  })

  // 加载统计信息
  const loadStatistics = useCallback(async () => {
    try {
      const res = await axios.get('/api/exercises/statistics')
      setStatistics(res.data)
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载统计信息失败:', err)
    }
  }, [])

  // 加载来源列表
  const loadSources = useCallback(async () => {
    try {
      const res = await axios.get('/api/exercises/sources')
      setSources(res.data.items || [])
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载来源列表失败:', err)
    }
  }, [])

  // 加载题目列表
  const loadExercises = useCallback(async (page = 1) => {
    try {
      setLoading(true)
      const params = {
        page,
        page_size: pageSize,
        ...Object.fromEntries(
          Object.entries(filters).filter(([_, v]) => v !== '')
        )
      }
      const res = await axios.get('/api/exercises/list', { params })
      setExercises(res.data.items || [])
      setTotalPages(res.data.total_pages || 1)
      setTotalCount(res.data.total || 0)
      setCurrentPage(page)
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载题目列表失败:', err)
    } finally {
      setLoading(false)
    }
  }, [filters])

  // 初始化加载
  useEffect(() => {
    loadStatistics()
    loadSources()
    loadExercises(1)
  }, [])

  // 筛选条件变化时重新加载
  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleSearch = () => {
    loadExercises(1)
  }

  const handleReset = () => {
    setFilters({
      question_type: '',
      year: '',
      tag: '',
      keyword: ''
    })
    setTimeout(() => loadExercises(1), 0)
  }

  // 渲染题目内容（处理特殊格式）
  const renderContent = (content) => {
    if (!content) return null
    // 处理空格标记
    const processed = content.replace(/\s{2,}/g, ' ________ ')
    return (
      <div className="whitespace-pre-wrap text-gray-800 leading-relaxed">
        {processed}
      </div>
    )
  }

  // 渲染选项
  const renderOptions = (options) => {
    if (!options || typeof options !== 'object') return null
    return (
      <div className="mt-3 space-y-2">
        {Object.entries(options).map(([key, value]) => (
          <div key={key} className="flex">
            <span className="font-medium text-[#1a2e1f] mr-2">{key}.</span>
            <span>{value}</span>
          </div>
        ))}
      </div>
    )
  }

  // 渲染难度星级
  const renderDifficulty = (level) => {
    if (!level) return <span className="text-gray-400">未知</span>
    const stars = Math.round(level * 5)
    return (
      <div className="flex items-center">
        {[1, 2, 3, 4, 5].map(i => (
          <span
            key={i}
            className={`text-lg ${i <= stars ? 'text-yellow-500' : 'text-gray-300'}`}
          >
            ★
          </span>
        ))}
        <span className="ml-2 text-sm text-gray-500">
          ({(level * 100).toFixed(0)}%)
        </span>
      </div>
    )
  }

  // 渲染标签
  const renderTags = (tags) => {
    if (!tags || tags.length === 0) return null
    return (
      <div className="flex flex-wrap gap-1 mt-2">
        {tags.slice(0, 5).map((tag, idx) => (
          <span
            key={idx}
            className="px-2 py-0.5 bg-[#c8f0d4] text-[#0f1c13] text-xs rounded"
          >
            {tag}
          </span>
        ))}
        {tags.length > 5 && (
          <span className="px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded">
            +{tags.length - 5}
          </span>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* 统计信息卡片 */}
      {statistics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-3xl font-bold text-[#1a2e1f]">
              {statistics.total_count}
            </div>
            <div className="text-gray-500 text-sm">题目总数</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-3xl font-bold text-green-600">
              {statistics.source_count}
            </div>
            <div className="text-gray-500 text-sm">试卷来源</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-2xl font-bold text-[#1a2e1f]">
              {Object.keys(statistics.type_distribution || {}).length}
            </div>
            <div className="text-gray-500 text-sm">题型分类</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-2xl font-bold text-orange-600">
              {Object.keys(statistics.year_distribution || {}).length}
            </div>
            <div className="text-gray-500 text-sm">年份跨度</div>
          </div>
        </div>
      )}

      {/* 筛选区域 */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <select
            className="border rounded px-3 py-2"
            value={filters.question_type}
            onChange={e => handleFilterChange('question_type', e.target.value)}
          >
            <option value="">所有题型</option>
            <option value="单选题">单选题</option>
            <option value="多选题">多选题</option>
            <option value="填空题">填空题</option>
            <option value="简答题">简答题</option>
          </select>

          <select
            className="border rounded px-3 py-2"
            value={filters.year}
            onChange={e => handleFilterChange('year', e.target.value)}
          >
            <option value="">所有年份</option>
            {statistics?.year_distribution &&
              Object.keys(statistics.year_distribution)
                .sort((a, b) => b - a)
                .map(year => (
                  <option key={year} value={year}>
                    {year}年 ({statistics.year_distribution[year]}题)
                  </option>
                ))}
          </select>

          <select
            className="border rounded px-3 py-2"
            value={filters.tag}
            onChange={e => handleFilterChange('tag', e.target.value)}
          >
            <option value="">所有标签</option>
            {statistics?.top_tags?.map(tag => (
              <option key={tag.name} value={tag.name}>
                {tag.name} ({tag.count})
              </option>
            ))}
          </select>

          <input
            type="text"
            className="border rounded px-3 py-2"
            placeholder="关键词搜索..."
            value={filters.keyword}
            onChange={e => handleFilterChange('keyword', e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSearch()}
          />

          <div className="flex gap-2">
            <button
              className="flex-1 bg-[#2d5a3d] text-white px-4 py-2 rounded hover:bg-[#2d5a3d]"
              onClick={handleSearch}
            >
              搜索
            </button>
            <button
              className="px-4 py-2 border rounded hover:bg-gray-100"
              onClick={handleReset}
            >
              重置
            </button>
          </div>
        </div>
      </div>

      {/* 题目列表 */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b flex justify-between items-center">
          <h2 className="text-lg font-medium">
            题目列表
            <span className="text-gray-500 text-sm ml-2">
              (共 {totalCount} 道)
            </span>
          </h2>
        </div>

        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : exercises.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无题目</div>
        ) : (
          <div className="divide-y">
            {exercises.map((ex, idx) => (
              <div
                key={ex.id}
                className="p-4 hover:bg-gray-50 cursor-pointer"
                onClick={() => setSelectedExercise(ex)}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    {/* 题目头部信息 */}
                    <div className="flex items-center gap-2 mb-2">
                      <span className="px-2 py-0.5 bg-[#2d5a3d] text-white text-xs rounded">
                        {ex.question_type}
                      </span>
                      {ex.year && (
                        <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded">
                          {ex.year}年
                        </span>
                      )}
                      {ex.exam_source && (
                        <span className="px-2 py-0.5 bg-[#c8f0d4] text-[#0f1c13] text-xs rounded">
                          {ex.exam_source}
                        </span>
                      )}
                      {ex.question_number && (
                        <span className="text-gray-400 text-xs">
                          第{ex.question_number}题
                        </span>
                      )}
                      {ex.images && ex.images.length > 0 && (
                        <span className="px-2 py-0.5 bg-orange-100 text-orange-700 text-xs rounded">
                          {ex.images.length}张图
                        </span>
                      )}
                      {ex.table_html && (
                        <span className="px-2 py-0.5 bg-cyan-100 text-cyan-700 text-xs rounded">
                          含表格
                        </span>
                      )}
                    </div>

                    {/* 题目内容预览 */}
                    <div className="text-gray-800 line-clamp-3">
                      {ex.content?.substring(0, 200)}
                      {ex.content?.length > 200 && '...'}
                    </div>

                    {/* 标签 */}
                    {renderTags(ex.tags)}
                  </div>

                  {/* 难度 */}
                  <div className="ml-4 text-right">
                    {renderDifficulty(ex.difficulty_level)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 分页 */}
        {totalPages > 1 && (
          <div className="p-4 border-t flex justify-center gap-2">
            <button
              className="px-3 py-1 border rounded disabled:opacity-50"
              disabled={currentPage <= 1}
              onClick={() => loadExercises(currentPage - 1)}
            >
              上一页
            </button>
            <span className="px-3 py-1">
              {currentPage} / {totalPages}
            </span>
            <button
              className="px-3 py-1 border rounded disabled:opacity-50"
              disabled={currentPage >= totalPages}
              onClick={() => loadExercises(currentPage + 1)}
            >
              下一页
            </button>
          </div>
        )}
      </div>

      {/* 题目详情弹窗 */}
      {selectedExercise && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedExercise(null)}
        >
          <div
            className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white border-b p-4 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <span className="px-2 py-1 bg-[#2d5a3d] text-white text-sm rounded">
                  {selectedExercise.question_type}
                </span>
                {selectedExercise.year && (
                  <span className="text-gray-500">
                    {selectedExercise.year}年 {selectedExercise.exam_source}
                  </span>
                )}
              </div>
              <button
                className="text-gray-400 hover:text-gray-600 text-2xl"
                onClick={() => setSelectedExercise(null)}
              >
                ×
              </button>
            </div>

            <div className="p-6">
              {/* 题目内容 */}
              <div className="mb-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">题目</h3>
                {renderContent(selectedExercise.content)}
              </div>

              {/* 选项 */}
              {selectedExercise.options && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-500 mb-2">选项</h3>
                  {renderOptions(selectedExercise.options)}
                </div>
              )}

              {/* 答案 */}
              <div className="mb-6 p-4 bg-green-50 rounded-lg">
                <h3 className="text-sm font-medium text-green-700 mb-2">答案</h3>
                <div className="text-green-800 whitespace-pre-wrap">
                  {selectedExercise.answer || '暂无答案'}
                </div>
              </div>

              {/* 解析 */}
              {selectedExercise.explanation && (
                <div className="mb-6 p-4 bg-[#e8f8ee] rounded-lg">
                  <h3 className="text-sm font-medium text-[#0f1c13] mb-2">解析</h3>
                  <div className="text-[#0a120c] whitespace-pre-wrap">
                    {selectedExercise.explanation}
                  </div>
                </div>
              )}

              {/* 表格 */}
              {selectedExercise.table_html && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-500 mb-2">相关表格</h3>
                  <div
                    className="overflow-x-auto"
                    dangerouslySetInnerHTML={{ __html: selectedExercise.table_html }}
                  />
                </div>
              )}

              {/* 图片 */}
              {selectedExercise.images && selectedExercise.images.length > 0 && (
                <div className="mb-6">
                  <h3 className="text-sm font-medium text-gray-500 mb-2">
                    相关图片 ({selectedExercise.images.length})
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    {selectedExercise.images.map((img, idx) => {
                      const imgUrl = '/' + img.path.split('/').map(p => encodeURIComponent(p)).join('/')
                      if (import.meta.env.DEV) console.log('Loading image:', imgUrl)
                      return (
                        <img
                          key={idx}
                          src={imgUrl}
                          alt={`图${idx + 1}`}
                          className="rounded border max-h-64 object-contain"
                          onError={(e) => {
                            if (import.meta.env.DEV) console.error('Image load failed. Path:', img.path, 'URL:', imgUrl)
                          }}
                          onLoad={() => { if (import.meta.env.DEV) console.log('Image loaded successfully:', imgUrl) }}
                        />
                      )
                    })}
                  </div>
                </div>
              )}

              {/* 元信息 */}
              <div className="mt-6 pt-4 border-t">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">难度:</span>
                    <span className="ml-2">
                      {renderDifficulty(selectedExercise.difficulty_level)}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">来源:</span>
                    <span className="ml-2">{selectedExercise.source_name}</span>
                  </div>
                </div>
                {renderTags(selectedExercise.tags)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ExercisePage
