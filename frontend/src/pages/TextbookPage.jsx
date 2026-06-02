import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import ReactMarkdown from 'react-markdown'

function TextbookPage() {
  // 状态管理
  const [stats, setStats] = useState(null)
  const [books, setBooks] = useState([])
  const [selectedBook, setSelectedBook] = useState(null)
  const [pages, setPages] = useState([])
  const [selectedPage, setSelectedPage] = useState(null)
  const [pageContent, setPageContent] = useState(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [activeTab, setActiveTab] = useState('browse') // browse, search

  // 搜索相关
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searchMode, setSearchMode] = useState('semantic') // semantic 或 keyword
  const [searchBookFilter, setSearchBookFilter] = useState('')

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const pageLimit = 20

  // 加载统计信息
  const loadStats = useCallback(async () => {
    try {
      const res = await axios.get('/api/knowledge/stats')
      if (res.data.success) {
        setStats(res.data.data)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载统计失败:', err)
    }
  }, [])

  // 加载教材列表
  const loadBooks = useCallback(async () => {
    try {
      const res = await axios.get('/api/knowledge/books')
      if (res.data.success) {
        setBooks(res.data.data)
        // 默认选中第一本
        if (res.data.data.length > 0 && !selectedBook) {
          setSelectedBook(res.data.data[0])
        }
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载教材列表失败:', err)
    }
  }, [selectedBook])

  // 加载教材页面列表
  const loadPages = useCallback(async (bookId, page = 1) => {
    if (!bookId) return
    try {
      setLoading(true)
      const res = await axios.get(`/api/knowledge/books/${bookId}/pages`, {
        params: { page, limit: pageLimit }
      })
      if (res.data.success) {
        setPages(res.data.data.pages)
        setTotalPages(res.data.data.total_pages)
        setCurrentPage(page)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载页面列表失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  // 加载单个页面内容
  const loadPageContent = useCallback(async (pageId) => {
    try {
      setLoading(true)
      const res = await axios.get(`/api/knowledge/pages/${pageId}`)
      if (res.data.success) {
        setPageContent(res.data.data)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载页面内容失败:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  // 初始化加载
  useEffect(() => {
    loadStats()
    loadBooks()
  }, [loadStats, loadBooks])

  // 切换教材时加载页面列表
  useEffect(() => {
    if (selectedBook) {
      loadPages(selectedBook.book_id, 1)
      setSelectedPage(null)
      setPageContent(null)
    }
  }, [selectedBook, loadPages])

  // 选择页面
  const handleSelectPage = (page) => {
    setSelectedPage(page)
    loadPageContent(page.id)
  }

  // 翻页
  const handlePageChange = (newPage) => {
    if (selectedBook && newPage >= 1 && newPage <= totalPages) {
      loadPages(selectedBook.book_id, newPage)
    }
  }

  // 语义搜索
  const handleSemanticSearch = async () => {
    if (!searchQuery.trim()) return

    try {
      setLoading(true)
      const res = await axios.post('/api/knowledge/search', {
        query: searchQuery,
        top_k: 20,
        book_id: searchBookFilter || null
      })
      if (res.data.success) {
        setSearchResults(res.data.data.results)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('搜索失败:', err)
      setMessage({ type: 'error', text: '搜索失败: ' + (err.response?.data?.detail || err.message) })
    } finally {
      setLoading(false)
    }
  }

  // 关键词搜索
  const handleKeywordSearch = async () => {
    if (!searchQuery.trim()) return

    try {
      setLoading(true)
      const res = await axios.get('/api/knowledge/search/simple', {
        params: {
          q: searchQuery,
          limit: 20,
          book_id: searchBookFilter || undefined
        }
      })
      if (res.data.success) {
        setSearchResults(res.data.data.results)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('搜索失败:', err)
    } finally {
      setLoading(false)
    }
  }

  // 统一搜索处理
  const handleSearch = () => {
    if (searchMode === 'semantic') {
      handleSemanticSearch()
    } else {
      handleKeywordSearch()
    }
  }

  return (
    <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
      {/* 页面标题 */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">知识库管理</h1>
        <p className="mt-2 text-gray-600">浏览和搜索教材知识库内容</p>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-2xl font-bold text-[#1a2e1f]">{stats.total_books}</div>
            <div className="text-sm text-gray-500">教材数量</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-2xl font-bold text-green-600">{stats.total_pages}</div>
            <div className="text-sm text-gray-500">总页数</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-2xl font-bold text-[#1a2e1f]">{stats.total_chunks}</div>
            <div className="text-sm text-gray-500">文本切片</div>
          </div>
          <div className="bg-white rounded-lg shadow p-4">
            <div className="text-2xl font-bold text-teal-600">{stats.total_embeddings}</div>
            <div className="text-sm text-gray-500">已向量化</div>
          </div>
        </div>
      )}

      {/* 各教材统计 */}
      {stats?.books?.length > 0 && (
        <div className="bg-white rounded-lg shadow p-4 mb-8">
          <h3 className="font-medium text-gray-700 mb-3">教材处理状态</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {stats.books.map((book) => (
              <div key={book.book_id} className="border rounded-lg p-3">
                <div className="font-medium text-sm text-gray-800 mb-1">{book.short_name}</div>
                <div className="text-xs text-gray-500 space-y-0.5">
                  <div>页数: {book.page_count}</div>
                  <div>切片: {book.chunk_count}</div>
                  <div className="flex items-center gap-1">
                    向量: {book.embedding_count}
                    {book.embedding_count === book.chunk_count ? (
                      <span className="text-green-500">✓</span>
                    ) : (
                      <span className="text-orange-500">
                        ({Math.round(book.embedding_count / book.chunk_count * 100)}%)
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 标签页 */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {[
            { id: 'browse', name: '浏览内容' },
            { id: 'search', name: '搜索知识' }
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab.id
                  ? 'border-[#2d5a3d] text-[#1a2e1f]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* 浏览内容 */}
      {activeTab === 'browse' && (
        <div className="space-y-6">
          {/* 教材卡片选择 */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {books.map((book) => {
              // 根据book_id确定颜色
              const colorMap = {
                'bx1': { bg: 'bg-green-50', border: 'border-green-400', text: 'text-green-700', selected: 'ring-green-500' },
                'bx2': { bg: 'bg-[#e8f8ee]', border: 'border-[#2d5a3d]', text: 'text-[#0f1c13]', selected: 'ring-[#c8f0d4]' },
                'xxbx1': { bg: 'bg-[#e8f8ee]', border: 'border-[#2d5a3d]', text: 'text-[#0f1c13]', selected: 'ring-[#c8f0d4]' },
                'xxbx2': { bg: 'bg-orange-50', border: 'border-orange-400', text: 'text-orange-700', selected: 'ring-orange-500' },
                'xxbx3': { bg: 'bg-pink-50', border: 'border-pink-400', text: 'text-pink-700', selected: 'ring-pink-500' },
              }
              const colors = colorMap[book.book_id] || { bg: 'bg-gray-50', border: 'border-gray-400', text: 'text-gray-700', selected: 'ring-gray-500' }
              const isSelected = selectedBook?.book_id === book.book_id

              return (
                <button
                  key={book.book_id}
                  onClick={() => setSelectedBook(book)}
                  className={`p-4 rounded-lg border-2 transition-all ${colors.bg} ${colors.border} ${
                    isSelected ? `ring-2 ${colors.selected} shadow-lg scale-105` : 'hover:shadow-md hover:scale-102'
                  }`}
                >
                  <div className={`text-lg font-bold ${colors.text} mb-1`}>{book.short_name}</div>
                  <div className="text-xs text-gray-500">{book.page_count} 页</div>
                </button>
              )
            })}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左侧：页面列表 */}
          <div className="bg-white rounded-lg shadow p-4">
            {/* 当前选中的教材 */}
            {selectedBook && (
              <div className="mb-4 pb-3 border-b">
                <div className="font-medium text-gray-900">{selectedBook.short_name}</div>
                <div className="text-sm text-gray-500">{selectedBook.book_name}</div>
              </div>
            )}

            {/* 页面列表 */}
            <h3 className="font-medium text-gray-900 mb-3">页面列表</h3>

            {loading && !pages.length ? (
              <div className="text-center py-4 text-gray-500">加载中...</div>
            ) : pages.length > 0 ? (
              <>
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {pages.map((page) => (
                    <button
                      key={page.id}
                      onClick={() => handleSelectPage(page)}
                      className={`w-full text-left p-3 rounded-lg border transition ${
                        selectedPage?.id === page.id
                          ? 'bg-[#e8f8ee] border-[#b8d1bf]'
                          : 'hover:bg-gray-50 border-gray-200'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-gray-800">第 {page.page_num} 页</span>
                        <span className="text-xs text-gray-400">
                          {Math.round(page.content_length / 100) * 100}+ 字
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 line-clamp-2">
                        {page.preview?.replace(/[#*`]/g, '').slice(0, 80)}...
                      </p>
                    </button>
                  ))}
                </div>

                {/* 分页控件 */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-2 mt-4 pt-3 border-t">
                    <button
                      onClick={() => handlePageChange(currentPage - 1)}
                      disabled={currentPage === 1}
                      className="px-3 py-1 text-sm border rounded disabled:opacity-50"
                    >
                      上一页
                    </button>
                    <span className="text-sm text-gray-600">
                      {currentPage} / {totalPages}
                    </span>
                    <button
                      onClick={() => handlePageChange(currentPage + 1)}
                      disabled={currentPage === totalPages}
                      className="px-3 py-1 text-sm border rounded disabled:opacity-50"
                    >
                      下一页
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-8 text-gray-500">
                该教材暂无内容
              </div>
            )}
          </div>

          {/* 右侧：页面内容 */}
          <div className="lg:col-span-2 bg-white rounded-lg shadow p-4">
            {pageContent ? (
              <>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium text-gray-900">
                    {pageContent.book_name} - 第 {pageContent.page_num} 页
                  </h3>
                </div>

                {/* Markdown 内容 */}
                <div className="prose prose-sm max-w-none mb-6 p-4 bg-gray-50 rounded-lg max-h-[400px] overflow-y-auto">
                  <ReactMarkdown>{pageContent.markdown_content}</ReactMarkdown>
                </div>

                {/* 切片列表 */}
                {pageContent.chunks?.length > 0 && (
                  <div>
                    <h4 className="font-medium text-gray-700 mb-3">
                      文本切片 ({pageContent.chunks.length}个)
                    </h4>
                    <div className="space-y-2 max-h-[300px] overflow-y-auto">
                      {pageContent.chunks.map((chunk) => (
                        <div key={chunk.id} className="border rounded-lg p-3">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                              #{chunk.chunk_index + 1}
                            </span>
                            {chunk.has_embedding ? (
                              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">
                                已向量化
                              </span>
                            ) : (
                              <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded">
                                未向量化
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-gray-600">
                            {chunk.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-16 text-gray-500">
                请从左侧选择一个页面查看内容
              </div>
            )}
          </div>
        </div>
        </div>
      )}

      {/* 搜索知识 */}
      {activeTab === 'search' && (
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">搜索教材知识</h3>

            {message && (
              <div className={`mb-4 p-3 rounded ${
                message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
              }`}>
                {message.text}
              </div>
            )}

            {/* 搜索模式选择 */}
            <div className="flex gap-4 mb-4">
              <label className="flex items-center">
                <input
                  type="radio"
                  name="searchMode"
                  value="semantic"
                  checked={searchMode === 'semantic'}
                  onChange={() => setSearchMode('semantic')}
                  className="mr-2"
                />
                <span className="text-sm">
                  <span className="font-medium text-[#0f1c13]">语义搜索</span>
                  <span className="text-gray-500">（理解语义，更智能）</span>
                </span>
              </label>
              <label className="flex items-center">
                <input
                  type="radio"
                  name="searchMode"
                  value="keyword"
                  checked={searchMode === 'keyword'}
                  onChange={() => setSearchMode('keyword')}
                  className="mr-2"
                />
                <span className="text-sm">
                  <span className="font-medium">关键词搜索</span>
                  <span className="text-gray-500">（精确匹配）</span>
                </span>
              </label>
            </div>

            {/* 教材筛选 */}
            <div className="mb-4">
              <label className="block text-sm text-gray-600 mb-1">筛选教材（可选）</label>
              <select
                value={searchBookFilter}
                onChange={(e) => setSearchBookFilter(e.target.value)}
                className="w-full border rounded-lg p-2"
              >
                <option value="">全部教材</option>
                {books.map((book) => (
                  <option key={book.book_id} value={book.book_id}>
                    {book.short_name}
                  </option>
                ))}
              </select>
            </div>

            {/* 搜索框 */}
            <div className="flex gap-2 mb-6">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={searchMode === 'semantic'
                  ? '输入问题或描述，如：细胞如何产生能量？'
                  : '输入关键词，如：光合作用、细胞分裂...'}
                className="flex-1 border rounded-lg p-3"
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              />
              <button
                onClick={handleSearch}
                disabled={loading || !searchQuery.trim()}
                className={`px-6 rounded-lg disabled:bg-gray-300 ${
                  searchMode === 'semantic'
                    ? 'bg-[#1a2e1f] text-white hover:bg-[#0f1c13]'
                    : 'bg-[#1a2e1f] text-white hover:bg-[#0f1c13]'
                }`}
              >
                {loading ? '搜索中...' : '搜索'}
              </button>
            </div>

            {/* 搜索结果 */}
            {searchResults.length > 0 && (
              <div className="space-y-4">
                <div className="text-sm text-gray-500">
                  找到 {searchResults.length} 条相关内容
                </div>
                {searchResults.map((result, index) => (
                  <div key={result.chunk_id || index} className="border rounded-lg p-4">
                    {/* 章节定位路径 */}
                    {result.location && (
                      <div className="text-xs text-[#1a2e1f] mb-2 font-medium">
                        {result.location}
                      </div>
                    )}
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <span className="text-xs bg-[#c8f0d4] text-[#0f1c13] px-2 py-0.5 rounded">
                        {result.short_name || result.book_name}
                      </span>
                      {result.chapter && (
                        <span className="text-xs bg-[#e8f8ee] text-[#1a2e1f] px-2 py-0.5 rounded">
                          {result.chapter}
                        </span>
                      )}
                      {result.section && (
                        <span className="text-xs bg-[#e8f8ee] text-[#1a2e1f] px-2 py-0.5 rounded">
                          {result.section}
                        </span>
                      )}
                      <span className="text-xs text-gray-500">
                        P{result.page_num}
                      </span>
                      {result.similarity !== undefined && (
                        <span className={`text-xs px-2 py-0.5 rounded ${
                          result.similarity > 0.7
                            ? 'bg-green-100 text-green-700'
                            : result.similarity > 0.5
                              ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-gray-100 text-gray-600'
                        }`}>
                          {(result.similarity * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">
                      {result.content}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {searchResults.length === 0 && searchQuery && !loading && (
              <div className="text-center py-8 text-gray-500">
                未找到相关内容，请尝试其他关键词
              </div>
            )}

            {/* 使用提示 */}
            {!searchQuery && (
              <div className="mt-6 p-4 bg-gray-50 rounded-lg">
                <h4 className="font-medium text-gray-700 mb-2">搜索提示</h4>
                <ul className="text-sm text-gray-600 space-y-1">
                  <li>• <strong>语义搜索</strong>：理解您的问题含义，找到相关的知识内容</li>
                  <li>• <strong>关键词搜索</strong>：精确匹配您输入的文字</li>
                  <li>• 可以通过筛选教材来缩小搜索范围</li>
                  <li>• 语义搜索示例：&quot;细胞如何获取能量？&quot;、&quot;DNA复制的过程&quot;</li>
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default TextbookPage
