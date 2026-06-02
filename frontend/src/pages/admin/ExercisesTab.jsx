import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

function ExercisesTab({ token, getHeaders }) {
  // 题库管理状态
  const [exercises, setExercises] = useState([])
  const [exercisePage, setExercisePage] = useState(1)
  const [exerciseTotal, setExerciseTotal] = useState(0)
  const [exerciseTotalPages, setExerciseTotalPages] = useState(1)
  const [exerciseFilters, setExerciseFilters] = useState({ question_type: '', keyword: '' })
  const [editingExercise, setEditingExercise] = useState(null)
  const [exerciseLoading, setExerciseLoading] = useState(false)

  // 来源管理状态
  const [sources, setSources] = useState([])
  const [editingSource, setEditingSource] = useState(null)

  const loadExercises = useCallback(async (page = 1) => {
    setExerciseLoading(true)
    try {
      const params = {
        page,
        page_size: 20,
        ...Object.fromEntries(
          Object.entries(exerciseFilters).filter(([_, v]) => v !== '')
        )
      }
      const res = await axios.get('/api/exercises/list', { params })
      setExercises(res.data.items || [])
      setExercisePage(res.data.page)
      setExerciseTotal(res.data.total)
      setExerciseTotalPages(res.data.total_pages)
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载题目失败:', err)
    } finally {
      setExerciseLoading(false)
    }
  }, [exerciseFilters])

  const loadSources = async () => {
    try {
      const res = await axios.get('/api/exercises/sources')
      setSources(res.data.items || [])
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载来源失败:', err)
    }
  }

  const deleteExercise = async (id) => {
    if (!confirm('确定要删除这道题目吗？')) return
    try {
      await axios.delete(`/api/exercises/delete/${id}`, { headers: getHeaders() })
      loadExercises(exercisePage)
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const saveExercise = async () => {
    if (!editingExercise) return
    try {
      if (editingExercise.id) {
        await axios.put(`/api/exercises/update/${editingExercise.id}`, editingExercise, { headers: getHeaders() })
      } else {
        await axios.post('/api/exercises/create', editingExercise, { headers: getHeaders() })
      }
      setEditingExercise(null)
      loadExercises(exercisePage)
    } catch (err) {
      alert('保存失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const deleteSource = async (id) => {
    if (!confirm('确定要删除这个来源吗？')) return
    try {
      await axios.delete(`/api/exercises/sources/delete/${id}`, { headers: getHeaders() })
      loadSources()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const saveSource = async () => {
    if (!editingSource) return
    try {
      if (editingSource.id) {
        await axios.put(`/api/exercises/sources/update/${editingSource.id}`, editingSource, { headers: getHeaders() })
      } else {
        await axios.post('/api/exercises/sources/create', editingSource, { headers: getHeaders() })
      }
      setEditingSource(null)
      loadSources()
    } catch (err) {
      alert('保存失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  // 初始加载
  useEffect(() => {
    loadExercises(1)
    loadSources()
  }, [])

  // 弹窗打开时禁止背景滚动
  useEffect(() => {
    const hasModal = editingExercise || editingSource
    if (hasModal) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }
    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [editingExercise, editingSource])

  return (
    <>
      <div className="space-y-4">
        {/* 筛选和新建 */}
        <div className="bg-white shadow rounded-lg p-4">
          <div className="flex gap-4 items-center flex-wrap">
            <select
              className="border rounded px-3 py-2"
              value={exerciseFilters.question_type}
              onChange={e => setExerciseFilters(f => ({ ...f, question_type: e.target.value }))}
            >
              <option value="">所有题型</option>
              <option value="单选题">单选题</option>
              <option value="多选题">多选题</option>
              <option value="填空题">填空题</option>
              <option value="简答题">简答题</option>
            </select>
            <input
              type="text"
              placeholder="关键词搜索..."
              className="border rounded px-3 py-2 flex-1 min-w-[200px]"
              value={exerciseFilters.keyword}
              onChange={e => setExerciseFilters(f => ({ ...f, keyword: e.target.value }))}
              onKeyPress={e => e.key === 'Enter' && loadExercises(1)}
            />
            <button
              onClick={() => loadExercises(1)}
              className="bg-[#2d5a3d] text-white px-4 py-2 rounded hover:bg-[#1a2e1f]"
            >
              搜索
            </button>
            <button
              onClick={() => setEditingExercise({ question_type: '单选题', content: '', answer: '', tags: [] })}
              className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600"
            >
              新建题目
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* 题目列表 - 占2列 */}
          <div className="lg:col-span-2 bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 280px)'}}>
            <div className="p-4 border-b flex-shrink-0">
              <h3 className="font-medium">题目列表 (共 {exerciseTotal} 道)</h3>
            </div>
            {exerciseLoading ? (
              <div className="p-8 text-center text-gray-500">加载中...</div>
            ) : (
              <div className="divide-y overflow-y-auto flex-1">
                {exercises.map(ex => (
                  <div key={ex.id} className="p-3 hover:bg-gray-50">
                    <div className="flex justify-between items-start">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="px-2 py-0.5 bg-[#2d5a3d] text-white text-xs rounded flex-shrink-0">{ex.question_type}</span>
                          {ex.year && <span className="text-gray-500 text-xs">{ex.year}年</span>}
                          <span className="text-gray-400 text-xs">ID: {ex.id}</span>
                        </div>
                        <div className="text-gray-800 text-sm line-clamp-2">{ex.content?.substring(0, 120)}...</div>
                      </div>
                      <div className="flex gap-1 ml-2 flex-shrink-0">
                        <button
                          onClick={() => setEditingExercise(ex)}
                          className="px-2 py-1 text-xs text-[#1a2e1f] hover:bg-[#e8f8ee] rounded"
                        >
                          编辑
                        </button>
                        <button
                          onClick={() => deleteExercise(ex.id)}
                          className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded"
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
            {exerciseTotalPages > 1 && (
              <div className="p-3 border-t flex justify-center gap-2 flex-shrink-0">
                <button
                  className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                  disabled={exercisePage <= 1}
                  onClick={() => loadExercises(exercisePage - 1)}
                >
                  上一页
                </button>
                <span className="px-3 py-1 text-sm">{exercisePage} / {exerciseTotalPages}</span>
                <button
                  className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                  disabled={exercisePage >= exerciseTotalPages}
                  onClick={() => loadExercises(exercisePage + 1)}
                >
                  下一页
                </button>
              </div>
            )}
          </div>

          {/* 来源管理 - 占1列 */}
          <div className="bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 280px)'}}>
            <div className="p-4 border-b flex justify-between items-center flex-shrink-0">
              <h3 className="font-medium">来源管理</h3>
              <button
                onClick={() => setEditingSource({ name: '', source_type: '高考' })}
                className="bg-green-500 text-white px-3 py-1 rounded text-sm hover:bg-green-600"
              >
                新建
              </button>
            </div>
            <div className="divide-y overflow-y-auto flex-1">
              {sources.map(src => (
                <div key={src.id} className="p-3 flex justify-between items-center hover:bg-gray-50">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-sm truncate">{src.name}</div>
                    <div className="text-gray-500 text-xs">{src.source_type} ({src.exercise_count}题)</div>
                  </div>
                  <div className="flex gap-1 ml-2 flex-shrink-0">
                    <button onClick={() => setEditingSource(src)} className="text-[#1a2e1f] text-xs px-1">编辑</button>
                    <button onClick={() => deleteSource(src.id)} className="text-red-600 text-xs px-1">删除</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 题目编辑弹窗 */}
      {editingExercise && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto" onClick={() => setEditingExercise(null)}>
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full my-8" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b p-4 flex justify-between items-center rounded-t-lg">
              <h3 className="font-medium">{editingExercise.id ? '编辑题目' : '新建题目'}</h3>
              <button onClick={() => setEditingExercise(null)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
              <div>
                <label className="block text-sm font-medium mb-1">题型</label>
                <select
                  className="w-full border rounded px-3 py-2"
                  value={editingExercise.question_type}
                  onChange={e => setEditingExercise({...editingExercise, question_type: e.target.value})}
                >
                  <option value="单选题">单选题</option>
                  <option value="多选题">多选题</option>
                  <option value="填空题">填空题</option>
                  <option value="简答题">简答题</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">题目内容</label>
                <textarea
                  className="w-full border rounded px-3 py-2 resize-none overflow-hidden"
                  style={{ minHeight: '60px' }}
                  value={editingExercise.content || ''}
                  onChange={e => {
                    e.target.style.height = 'auto'
                    e.target.style.height = e.target.scrollHeight + 'px'
                    setEditingExercise({...editingExercise, content: e.target.value})
                  }}
                  ref={el => { if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' } }}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">答案</label>
                <textarea
                  className="w-full border rounded px-3 py-2 resize-none overflow-hidden"
                  style={{ minHeight: '40px' }}
                  value={editingExercise.answer || ''}
                  onChange={e => {
                    e.target.style.height = 'auto'
                    e.target.style.height = e.target.scrollHeight + 'px'
                    setEditingExercise({...editingExercise, answer: e.target.value})
                  }}
                  ref={el => { if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' } }}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">解析</label>
                <textarea
                  className="w-full border rounded px-3 py-2 resize-none overflow-hidden"
                  style={{ minHeight: '40px' }}
                  value={editingExercise.explanation || ''}
                  onChange={e => {
                    e.target.style.height = 'auto'
                    e.target.style.height = e.target.scrollHeight + 'px'
                    setEditingExercise({...editingExercise, explanation: e.target.value})
                  }}
                  ref={el => { if (el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px' } }}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">难度 (0-1)</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="1"
                    className="w-full border rounded px-3 py-2"
                    value={editingExercise.difficulty_level || ''}
                    onChange={e => setEditingExercise({...editingExercise, difficulty_level: parseFloat(e.target.value) || null})}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">年份</label>
                  <input
                    type="number"
                    className="w-full border rounded px-3 py-2"
                    value={editingExercise.year || ''}
                    onChange={e => setEditingExercise({...editingExercise, year: parseInt(e.target.value) || null})}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">标签 (逗号分隔)</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  value={(editingExercise.tags || []).join(', ')}
                  onChange={e => setEditingExercise({...editingExercise, tags: e.target.value.split(',').map(t => t.trim()).filter(t => t)})}
                />
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <button onClick={() => setEditingExercise(null)} className="px-4 py-2 border rounded hover:bg-gray-100">取消</button>
                <button onClick={saveExercise} className="px-4 py-2 bg-[#2d5a3d] text-white rounded hover:bg-[#1a2e1f]">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 来源编辑弹窗 */}
      {editingSource && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={() => setEditingSource(null)}>
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full" onClick={e => e.stopPropagation()}>
            <div className="border-b p-4 flex justify-between items-center">
              <h3 className="font-medium">{editingSource.id ? '编辑来源' : '新建来源'}</h3>
              <button onClick={() => setEditingSource(null)} className="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">名称</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  value={editingSource.name || ''}
                  onChange={e => setEditingSource({...editingSource, name: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">类型</label>
                <select
                  className="w-full border rounded px-3 py-2"
                  value={editingSource.source_type || '高考'}
                  onChange={e => setEditingSource({...editingSource, source_type: e.target.value})}
                >
                  <option value="高考">高考</option>
                  <option value="模拟">模拟</option>
                  <option value="教辅">教辅</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-1">年份</label>
                  <input
                    type="number"
                    className="w-full border rounded px-3 py-2"
                    value={editingSource.year || ''}
                    onChange={e => setEditingSource({...editingSource, year: parseInt(e.target.value) || null})}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">地区</label>
                  <input
                    type="text"
                    className="w-full border rounded px-3 py-2"
                    value={editingSource.region || ''}
                    onChange={e => setEditingSource({...editingSource, region: e.target.value})}
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-4 border-t">
                <button onClick={() => setEditingSource(null)} className="px-4 py-2 border rounded hover:bg-gray-100">取消</button>
                <button onClick={saveSource} className="px-4 py-2 bg-[#2d5a3d] text-white rounded hover:bg-[#1a2e1f]">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default ExercisesTab
