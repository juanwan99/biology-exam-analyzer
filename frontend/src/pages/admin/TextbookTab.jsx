import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

function TextbookTab({ token, getHeaders }) {
  // 教材管理状态
  const [chapters, setChapters] = useState([])
  const [knowledgePoints, setKnowledgePoints] = useState([])
  const [editingChapter, setEditingChapter] = useState(null)
  const [editingKP, setEditingKP] = useState(null)
  const [textbookLoading, setTextbookLoading] = useState(false)
  const [editingChunk, setEditingChunk] = useState(null)
  // 教材切片列表状态
  const [textbookChunks, setTextbookChunks] = useState([])
  const [chunkPage, setChunkPage] = useState(1)
  const [chunkTotal, setChunkTotal] = useState(0)
  const [chunkTotalPages, setChunkTotalPages] = useState(1)
  const [chunkFilters, setChunkFilters] = useState({ book_id: '', keyword: '' })
  const [books, setBooks] = useState([])

  const loadChapters = async () => {
    setTextbookLoading(true)
    try {
      const res = await axios.get('/api/textbook/chapters')
      setChapters(res.data.data || [])
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载章节失败:', err)
    } finally {
      setTextbookLoading(false)
    }
  }

  const loadKnowledgePoints = async () => {
    try {
      const res = await axios.get('/api/textbook/knowledge-points', { params: { limit: 100 } })
      setKnowledgePoints(res.data.data || [])
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载知识点失败:', err)
    }
  }

  const loadBooks = async () => {
    try {
      const res = await axios.get('/api/textbook/books')
      setBooks(res.data.data || [])
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载教材列表失败:', err)
    }
  }

  const loadTextbookChunks = useCallback(async (page = 1) => {
    setTextbookLoading(true)
    try {
      const params = {
        page,
        page_size: 30,
        ...Object.fromEntries(
          Object.entries(chunkFilters).filter(([_, v]) => v !== '')
        )
      }
      const res = await axios.get('/api/textbook/contents/list', { params })
      setTextbookChunks(res.data.items || [])
      setChunkPage(res.data.page)
      setChunkTotal(res.data.total)
      setChunkTotalPages(res.data.total_pages)
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载教材切片失败:', err)
    } finally {
      setTextbookLoading(false)
    }
  }, [chunkFilters])

  const saveChunk = async () => {
    if (!editingChunk) return
    try {
      await axios.put(`/api/textbook/chunks/${editingChunk.id}`, { content: editingChunk.content }, { headers: getHeaders() })
      setEditingChunk(null)
      loadTextbookChunks(chunkPage)
    } catch (err) {
      alert('保存失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const deleteChunk = async (id) => {
    if (!confirm('确定要删除这条切片吗？')) return
    try {
      await axios.delete(`/api/textbook/chunks/${id}`, { headers: getHeaders() })
      loadTextbookChunks(chunkPage)
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const deleteChapter = async (id) => {
    if (!confirm('确定要删除这个章节吗？（关联的内容也会被删除）')) return
    try {
      await axios.delete(`/api/textbook/chapters/${id}`, { headers: getHeaders() })
      loadChapters()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const saveChapter = async () => {
    if (!editingChapter) return
    try {
      if (editingChapter.id) {
        await axios.put(`/api/textbook/chapters/${editingChapter.id}`, editingChapter, { headers: getHeaders() })
      } else {
        await axios.post('/api/textbook/chapters', editingChapter, { headers: getHeaders() })
      }
      setEditingChapter(null)
      loadChapters()
    } catch (err) {
      alert('保存失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const deleteKnowledgePoint = async (id) => {
    if (!confirm('确定要删除这个知识点吗？')) return
    try {
      await axios.delete(`/api/textbook/knowledge-points/${id}`, { headers: getHeaders() })
      loadKnowledgePoints()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const saveKnowledgePoint = async () => {
    if (!editingKP) return
    try {
      if (editingKP.id) {
        await axios.put(`/api/textbook/knowledge-points/${editingKP.id}`, editingKP, { headers: getHeaders() })
      } else {
        await axios.post('/api/textbook/knowledge-points', editingKP, { headers: getHeaders() })
      }
      setEditingKP(null)
      loadKnowledgePoints()
    } catch (err) {
      alert('保存失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  // 初始加载
  useEffect(() => {
    loadTextbookChunks(1)
    loadBooks()
  }, [])

  // 弹窗打开时禁止背景滚动
  useEffect(() => {
    const hasModal = editingChapter || editingKP || editingChunk
    if (hasModal) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }
    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [editingChapter, editingKP, editingChunk])

  return (
    <>
      <div className="space-y-4">
        {/* 教材选择卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {books.map((book) => {
            // 根据book_id确定颜色
            const colorMap = {
              'bx1': { bg: 'bg-green-50', border: 'border-green-400', text: 'text-green-700', selected: 'ring-green-500' },
              'bx2': { bg: 'bg-[#e8f8ee]', border: 'border-[#5a9a6d]', text: 'text-[#0f1c13]', selected: 'ring-[#c8f0d4]' },
              'xxbx1': { bg: 'bg-[#e8f8ee]', border: 'border-[#2d5a3d]', text: 'text-[#0f1c13]', selected: 'ring-[#c8f0d4]' },
              'xxbx2': { bg: 'bg-orange-50', border: 'border-orange-400', text: 'text-orange-700', selected: 'ring-orange-500' },
              'xxbx3': { bg: 'bg-pink-50', border: 'border-pink-400', text: 'text-pink-700', selected: 'ring-pink-500' },
            }
            const colors = colorMap[book.book_id] || { bg: 'bg-gray-50', border: 'border-gray-400', text: 'text-gray-700', selected: 'ring-gray-500' }
            const isSelected = chunkFilters.book_id === book.book_id

            return (
              <button
                key={book.book_id}
                onClick={() => {
                  setChunkFilters(f => ({ ...f, book_id: book.book_id }))
                  loadTextbookChunks(1)
                }}
                className={`p-4 rounded-lg border-2 transition-all ${colors.bg} ${colors.border} ${
                  isSelected ? `ring-2 ${colors.selected} shadow-lg scale-105` : 'hover:shadow-md'
                }`}
              >
                <div className={`text-lg font-bold ${colors.text} mb-1`}>{book.short_name || book.book_name}</div>
                <div className="text-xs text-gray-500">{book.chunk_count} 条切片</div>
              </button>
            )
          })}
        </div>

        {/* 提示信息：未选择教材时 */}
        {!chunkFilters.book_id && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 text-center">
            <div className="text-yellow-700 text-lg mb-2">请先选择一本教材</div>
            <div className="text-yellow-600 text-sm">点击上方的教材卡片，查看和编辑该教材的切片内容</div>
          </div>
        )}

        {/* 已选择教材：显示筛选栏和切片列表 */}
        {chunkFilters.book_id && (
          <>
            {/* 筛选栏 */}
            <div className="bg-white shadow rounded-lg p-4">
              <div className="flex gap-4 items-center flex-wrap">
                <div className="text-sm text-gray-600">
                  当前教材: <span className="font-medium text-[#1a2e1f]">{books.find(b => b.book_id === chunkFilters.book_id)?.book_name}</span>
                </div>
                <input
                  type="text"
                  placeholder="关键词搜索..."
                  className="border rounded px-3 py-2 flex-1 min-w-[200px]"
                  value={chunkFilters.keyword}
                  onChange={e => setChunkFilters(f => ({ ...f, keyword: e.target.value }))}
                  onKeyPress={e => e.key === 'Enter' && loadTextbookChunks(1)}
                />
                <button
                  onClick={() => loadTextbookChunks(1)}
                  className="bg-[#2d5a3d] text-white px-4 py-2 rounded hover:bg-[#1a2e1f]"
                >
                  搜索
                </button>
                <button
                  onClick={() => {
                    setChunkFilters({ book_id: '', keyword: '' })
                    setTextbookChunks([])
                    setChunkTotal(0)
                  }}
                  className="text-gray-500 px-4 py-2 rounded hover:bg-gray-100"
                >
                  返回选择
                </button>
              </div>
            </div>

            {/* 切片列表 */}
            <div className="bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 380px)'}}>
              <div className="p-4 border-b flex justify-between items-center flex-shrink-0">
                <h3 className="font-medium">教材切片 (共 {chunkTotal} 条)</h3>
              </div>
              {textbookLoading ? (
                <div className="p-8 text-center text-gray-500">加载中...</div>
              ) : textbookChunks.length === 0 ? (
                <div className="p-8 text-center text-gray-400">暂无教材切片</div>
              ) : (
                <div className="divide-y overflow-y-auto flex-1">
                  {textbookChunks.map((chunk) => (
                    <div key={chunk.id} className="p-3 hover:bg-gray-50">
                      <div className="flex justify-between items-start gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="text-gray-400 text-xs">#{chunk.id}</span>
                            <span className="text-gray-400 text-xs">P{chunk.page_num}</span>
                            {chunk.chapter_info?.chapter && (
                              <span className="text-green-600 text-xs">{chunk.chapter_info.chapter}</span>
                            )}
                          </div>
                          <div className="text-sm text-gray-700 line-clamp-3 whitespace-pre-wrap">{chunk.content}</div>
                        </div>
                        <div className="flex gap-1 flex-shrink-0">
                          <button
                            onClick={() => setEditingChunk(chunk)}
                            className="text-[#1a2e1f] text-xs px-2 py-1 hover:bg-[#c8f0d4] rounded"
                          >
                            编辑
                          </button>
                          <button
                            onClick={() => deleteChunk(chunk.id)}
                            className="text-red-600 text-xs px-2 py-1 hover:bg-red-100 rounded"
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {/* 分页 */}
              {chunkTotalPages > 1 && (
                <div className="p-3 border-t flex justify-center gap-2 flex-shrink-0">
                  <button
                    className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                    disabled={chunkPage <= 1}
                    onClick={() => loadTextbookChunks(chunkPage - 1)}
                  >
                    上一页
                  </button>
                  <span className="px-3 py-1 text-sm">{chunkPage} / {chunkTotalPages}</span>
                  <button
                    className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                    disabled={chunkPage >= chunkTotalPages}
                    onClick={() => loadTextbookChunks(chunkPage + 1)}
                  >
                    下一页
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* 章节编辑弹窗 */}
      {editingChapter && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={() => setEditingChapter(null)}>
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full" onClick={e => e.stopPropagation()}>
            <div className="border-b p-4 flex justify-between items-center">
              <h3 className="font-medium">{editingChapter.id ? '编辑章节' : '新建章节'}</h3>
              <button onClick={() => setEditingChapter(null)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">模块名称</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  placeholder="如：必修1：分子与细胞"
                  value={editingChapter.module_name || ''}
                  onChange={e => setEditingChapter({...editingChapter, module_name: e.target.value})}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">章节号</label>
                  <input
                    type="number"
                    className="w-full border rounded px-3 py-2"
                    value={editingChapter.chapter_num || ''}
                    onChange={e => setEditingChapter({...editingChapter, chapter_num: parseInt(e.target.value) || null})}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">年级</label>
                  <input
                    type="text"
                    className="w-full border rounded px-3 py-2"
                    value={editingChapter.grade || '高中'}
                    onChange={e => setEditingChapter({...editingChapter, grade: e.target.value})}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">章节名称</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  value={editingChapter.chapter_name || ''}
                  onChange={e => setEditingChapter({...editingChapter, chapter_name: e.target.value})}
                />
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <button onClick={() => setEditingChapter(null)} className="px-4 py-2 border rounded hover:bg-gray-100">取消</button>
                <button onClick={saveChapter} className="px-4 py-2 bg-[#2d5a3d] text-white rounded hover:bg-[#1a2e1f]">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 知识点编辑弹窗 */}
      {editingKP && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={() => setEditingKP(null)}>
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full" onClick={e => e.stopPropagation()}>
            <div className="border-b p-4 flex justify-between items-center">
              <h3 className="font-medium">{editingKP.id ? '编辑知识点' : '新建知识点'}</h3>
              <button onClick={() => setEditingKP(null)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">知识点名称</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  value={editingKP.name || ''}
                  onChange={e => setEditingKP({...editingKP, name: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">描述</label>
                <textarea
                  className="w-full border rounded px-3 py-2"
                  rows={4}
                  value={editingKP.description || ''}
                  onChange={e => setEditingKP({...editingKP, description: e.target.value})}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">难度等级 (1-5)</label>
                  <input
                    type="number"
                    min="1"
                    max="5"
                    className="w-full border rounded px-3 py-2"
                    value={editingKP.difficulty_level || 3}
                    onChange={e => setEditingKP({...editingKP, difficulty_level: parseInt(e.target.value) || 3})}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">重要程度 (1-5)</label>
                  <input
                    type="number"
                    min="1"
                    max="5"
                    className="w-full border rounded px-3 py-2"
                    value={editingKP.importance_level || 3}
                    onChange={e => setEditingKP({...editingKP, importance_level: parseInt(e.target.value) || 3})}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <button onClick={() => setEditingKP(null)} className="px-4 py-2 border rounded hover:bg-gray-100">取消</button>
                <button onClick={saveKnowledgePoint} className="px-4 py-2 bg-[#2d5a3d] text-white rounded hover:bg-[#1a2e1f]">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 切片编辑弹窗 */}
      {editingChunk && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto" onClick={() => setEditingChunk(null)}>
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full my-8" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b p-4 flex justify-between items-center rounded-t-lg">
              <h3 className="font-medium">编辑切片</h3>
              <button onClick={() => setEditingChunk(null)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
              {/* 切片信息 */}
              <div className="text-sm bg-gray-50 px-3 py-2 rounded space-y-1">
                <div>教材: <span className="text-[#1a2e1f]">{editingChunk.book_name}</span></div>
                <div>页码: <span className="text-gray-600">P{editingChunk.page_num}</span></div>
                {editingChunk.chapter_info?.chapter && (
                  <div>章节: <span className="text-green-600">{editingChunk.chapter_info.chapter}</span></div>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">切片内容</label>
                <textarea
                  className="w-full border rounded px-3 py-2 font-mono text-sm resize-none overflow-hidden"
                  style={{ minHeight: '150px' }}
                  value={editingChunk.content || ''}
                  onChange={e => {
                    e.target.style.height = 'auto'
                    e.target.style.height = e.target.scrollHeight + 'px'
                    setEditingChunk({...editingChunk, content: e.target.value})
                  }}
                  ref={el => { if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' } }}
                />
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <button onClick={() => setEditingChunk(null)} className="px-4 py-2 border rounded hover:bg-gray-100">取消</button>
                <button onClick={saveChunk} className="px-4 py-2 bg-[#2d5a3d] text-white rounded hover:bg-[#1a2e1f]">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default TextbookTab
