import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

function AdminPage() {
  // 认证状态
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [user, setUser] = useState(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [loginError, setLoginError] = useState('')

  const [activeTab, setActiveTab] = useState('exercises') // exercises | textbook | prompts | logs | users

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

  // Prompt和日志状态
  const [prompts, setPrompts] = useState({ split: '', analysis: '' })
  const [editingPrompt, setEditingPrompt] = useState('split')
  const [promptContent, setPromptContent] = useState('')

  // 操作日志状态
  const [operationLogs, setOperationLogs] = useState([])
  const [logsPage, setLogsPage] = useState(1)
  const [logsTotal, setLogsTotal] = useState(0)
  const [logsTotalPages, setLogsTotalPages] = useState(1)
  const [logsLoading, setLogsLoading] = useState(false)

  // 用户管理状态（仅管理员）
  const [users, setUsers] = useState([])
  const [editingUser, setEditingUser] = useState(null)

  // API Headers - 使用Bearer Token
  const getHeaders = () => ({ 'Authorization': `Bearer ${token}` })

  // 登录
  const handleLogin = async () => {
    setLoginError('')
    try {
      const response = await axios.post('/api/auth/login', {
        username,
        password
      })
      if (response.data.success) {
        const { token: newToken, user: userData } = response.data
        setToken(newToken)
        setUser(userData)
        setAuthenticated(true)
        localStorage.setItem('authToken', newToken)
        localStorage.setItem('authUser', JSON.stringify(userData))
      } else {
        setLoginError(response.data.message || '登录失败')
      }
    } catch (err) {
      setLoginError(err.response?.data?.message || '登录失败')
    }
  }

  // 检查本地存储的Token
  useEffect(() => {
    const savedToken = localStorage.getItem('authToken')
    const savedUser = localStorage.getItem('authUser')
    if (savedToken && savedUser) {
      // 验证token是否有效
      axios.get('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${savedToken}` }
      }).then(res => {
        if (res.data.success) {
          setToken(savedToken)
          setUser(JSON.parse(savedUser))
          setAuthenticated(true)
        } else {
          localStorage.removeItem('authToken')
          localStorage.removeItem('authUser')
        }
      }).catch(() => {
        localStorage.removeItem('authToken')
        localStorage.removeItem('authUser')
      })
    }
  }, [])

  // 登出
  const handleLogout = async () => {
    try {
      await axios.post('/api/auth/logout', {}, { headers: getHeaders() })
    } catch (err) {
      console.error('登出失败:', err)
    }
    setAuthenticated(false)
    setToken('')
    setUser(null)
    localStorage.removeItem('authToken')
    localStorage.removeItem('authUser')
  }

  // ========== 题库管理 ==========
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
      console.error('加载题目失败:', err)
    } finally {
      setExerciseLoading(false)
    }
  }, [exerciseFilters])

  const loadSources = async () => {
    try {
      const res = await axios.get('/api/exercises/sources')
      setSources(res.data.items || [])
    } catch (err) {
      console.error('加载来源失败:', err)
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

  // ========== 教材管理 ==========
  const loadChapters = async () => {
    setTextbookLoading(true)
    try {
      const res = await axios.get('/api/textbook/chapters')
      setChapters(res.data.data || [])
    } catch (err) {
      console.error('加载章节失败:', err)
    } finally {
      setTextbookLoading(false)
    }
  }

  const loadKnowledgePoints = async () => {
    try {
      const res = await axios.get('/api/textbook/knowledge-points', { params: { limit: 100 } })
      setKnowledgePoints(res.data.data || [])
    } catch (err) {
      console.error('加载知识点失败:', err)
    }
  }

  const loadBooks = async () => {
    try {
      const res = await axios.get('/api/textbook/books')
      setBooks(res.data.data || [])
    } catch (err) {
      console.error('加载教材列表失败:', err)
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
      console.error('加载教材切片失败:', err)
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

  // ========== 操作日志 ==========
  const loadOperationLogs = async (page = 1) => {
    setLogsLoading(true)
    try {
      const res = await axios.get('/api/auth/logs', {
        params: { page, page_size: 50 },
        headers: getHeaders()
      })
      setOperationLogs(res.data.logs || [])
      setLogsPage(res.data.page)
      setLogsTotal(res.data.total)
      setLogsTotalPages(res.data.total_pages)
    } catch (err) {
      console.error('加载操作日志失败:', err)
    } finally {
      setLogsLoading(false)
    }
  }

  // ========== 用户管理（仅管理员）==========
  const loadUsers = async () => {
    try {
      const res = await axios.get('/api/auth/users', { headers: getHeaders() })
      setUsers(res.data.users || [])
    } catch (err) {
      console.error('加载用户列表失败:', err)
    }
  }

  const resetUserPassword = async (userId) => {
    if (!confirm('确定要重置该用户密码吗？将生成一个随机密码。')) return
    try {
      const res = await axios.post(`/api/auth/users/${userId}/reset-password`, {}, { headers: getHeaders() })
      alert(res.data.message)
    } catch (err) {
      alert('重置失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const toggleUserStatus = async (userId, isActive) => {
    try {
      await axios.put(`/api/auth/users/${userId}`, { is_active: isActive ? 0 : 1 }, { headers: getHeaders() })
      loadUsers()
    } catch (err) {
      alert('操作失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  // ========== Prompt管理 ==========
  const loadPrompts = async () => {
    try {
      const response = await axios.get('/api/admin/prompts', { headers: getHeaders() })
      setPrompts(response.data)
      setPromptContent(response.data.split)
    } catch (err) {
      console.error('加载Prompt失败:', err)
    }
  }

  const savePrompt = async () => {
    try {
      await axios.put(
        '/api/admin/prompts',
        { type: editingPrompt, content: promptContent },
        { headers: getHeaders() }
      )
      alert('保存成功！')
      setPrompts({ ...prompts, [editingPrompt]: promptContent })
    } catch (err) {
      alert('保存失败')
    }
  }

  const switchPrompt = (type) => {
    setEditingPrompt(type)
    setPromptContent(prompts[type])
  }

  // 切换标签页时加载数据
  useEffect(() => {
    if (!authenticated) return
    if (activeTab === 'exercises') {
      loadExercises(1)
      loadSources()
    } else if (activeTab === 'textbook') {
      loadTextbookChunks(1)
      loadBooks()
    } else if (activeTab === 'logs') {
      loadOperationLogs(1)
    } else if (activeTab === 'users' && user?.role === 'admin') {
      loadUsers()
    } else if (activeTab === 'prompts') {
      loadPrompts()
    }
  }, [activeTab, authenticated])

  // 弹窗打开时禁止背景滚动
  useEffect(() => {
    const hasModal = editingExercise || editingSource || editingChapter || editingKP || editingChunk
    if (hasModal) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = 'unset'
    }
    return () => {
      document.body.style.overflow = 'unset'
    }
  }, [editingExercise, editingSource, editingChapter, editingKP, editingChunk])

  // 格式化操作类型
  const formatOperation = (op) => {
    const opMap = {
      'login': '登录',
      'logout': '登出',
      'create': '创建',
      'update': '更新',
      'delete': '删除',
      'batch_delete': '批量删除',
      'change_password': '修改密码',
      'reset_password': '重置密码'
    }
    return opMap[op] || op
  }

  // 格式化目标类型
  const formatTargetType = (type) => {
    const typeMap = {
      'exercise': '题目',
      'source': '来源',
      'chapter': '章节',
      'content': '内容',
      'knowledge_point': '知识点',
      'version': '版本',
      'user': '用户'
    }
    return typeMap[type] || type
  }

  if (!authenticated) {
    return (
      <div className="max-w-md mx-auto mt-20">
        <div className="bg-white shadow rounded-lg p-8">
          <h2 className="text-2xl font-bold mb-6 text-center">管理员登录</h2>
          {loginError && (
            <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">{loginError}</div>
          )}
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="请输入用户名"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg mb-4"
            onKeyPress={(e) => e.key === 'Enter' && handleLogin()}
          />
          <button
            onClick={handleLogin}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700"
          >
            登录
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-900">管理后台</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600">
            {user?.display_name || user?.username}
            {user?.role === 'admin' && <span className="ml-1 text-blue-600">(管理员)</span>}
          </span>
          <button
            onClick={handleLogout}
            className="px-4 py-2 text-sm text-red-600 hover:text-red-800"
          >
            退出登录
          </button>
        </div>
      </div>

      {/* 标签页 */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          {[
            { key: 'exercises', label: '题库管理' },
            { key: 'textbook', label: '教材管理' },
            { key: 'prompts', label: 'Prompt管理' },
            { key: 'logs', label: '操作日志' },
            ...(user?.role === 'admin' ? [{ key: 'users', label: '用户管理' }] : [])
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-4 px-1 border-b-2 font-medium text-sm ${
                activeTab === tab.key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* 题库管理 */}
      {activeTab === 'exercises' && (
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
                className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
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
                            <span className="px-2 py-0.5 bg-blue-500 text-white text-xs rounded flex-shrink-0">{ex.question_type}</span>
                            {ex.year && <span className="text-gray-500 text-xs">{ex.year}年</span>}
                            <span className="text-gray-400 text-xs">ID: {ex.id}</span>
                          </div>
                          <div className="text-gray-800 text-sm line-clamp-2">{ex.content?.substring(0, 120)}...</div>
                        </div>
                        <div className="flex gap-1 ml-2 flex-shrink-0">
                          <button
                            onClick={() => setEditingExercise(ex)}
                            className="px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded"
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
                      <button onClick={() => setEditingSource(src)} className="text-blue-600 text-xs px-1">编辑</button>
                      <button onClick={() => deleteSource(src.id)} className="text-red-600 text-xs px-1">删除</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 教材管理 - 已上传切片的审核和编辑 */}
      {activeTab === 'textbook' && (
        <div className="space-y-4">
          {/* 教材选择卡片 */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {books.map((book) => {
              // 根据book_id确定颜色
              const colorMap = {
                'bx1': { bg: 'bg-green-50', border: 'border-green-400', text: 'text-green-700', selected: 'ring-green-500' },
                'bx2': { bg: 'bg-blue-50', border: 'border-blue-400', text: 'text-blue-700', selected: 'ring-blue-500' },
                'xxbx1': { bg: 'bg-purple-50', border: 'border-purple-400', text: 'text-purple-700', selected: 'ring-purple-500' },
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
                    当前教材: <span className="font-medium text-blue-600">{books.find(b => b.book_id === chunkFilters.book_id)?.book_name}</span>
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
                    className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600"
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
                              className="text-blue-600 text-xs px-2 py-1 hover:bg-blue-100 rounded"
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
      )}

      {/* Prompt管理 */}
      {activeTab === 'prompts' && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex gap-4 mb-6">
            <button
              onClick={() => switchPrompt('split')}
              className={`px-4 py-2 rounded ${editingPrompt === 'split' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'}`}
            >
              拆分Prompt
            </button>
            <button
              onClick={() => switchPrompt('analysis')}
              className={`px-4 py-2 rounded ${editingPrompt === 'analysis' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'}`}
            >
              分析Prompt
            </button>
          </div>
          <textarea
            value={promptContent}
            onChange={(e) => setPromptContent(e.target.value)}
            rows={20}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg font-mono text-sm"
          />
          <div className="mt-4 flex justify-between items-center">
            <span className="text-sm text-gray-600">字符数: {promptContent.length}</span>
            <button onClick={savePrompt} className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700">
              保存并生效
            </button>
          </div>
        </div>
      )}

      {/* 操作日志 */}
      {activeTab === 'logs' && (
        <div className="bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 200px)'}}>
          <div className="p-4 border-b flex-shrink-0">
            <h3 className="font-medium">操作日志 (共 {logsTotal} 条)</h3>
          </div>
          {logsLoading ? (
            <div className="p-8 text-center text-gray-500">加载中...</div>
          ) : (
            <div className="overflow-auto flex-1">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">时间</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">用户</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">对象类型</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">对象</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">IP</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {operationLogs.map(log => (
                    <tr key={log.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">{log.created_at?.replace('T', ' ').slice(0, 19)}</td>
                      <td className="px-3 py-2 text-xs font-medium text-gray-900">{log.username}</td>
                      <td className="px-3 py-2 text-xs">
                        <span className={`px-1.5 py-0.5 rounded text-xs ${
                          log.operation === 'delete' || log.operation === 'batch_delete' ? 'bg-red-100 text-red-800' :
                          log.operation === 'create' ? 'bg-green-100 text-green-800' :
                          log.operation === 'update' ? 'bg-blue-100 text-blue-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {formatOperation(log.operation)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-500">{formatTargetType(log.target_type)}</td>
                      <td className="px-3 py-2 text-xs text-gray-500 max-w-[200px] truncate" title={log.target_name}>
                        {log.target_name || '-'}
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">{log.ip_address || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {/* 分页 */}
          {logsTotalPages > 1 && (
            <div className="p-3 border-t flex justify-center gap-2 flex-shrink-0">
              <button
                className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                disabled={logsPage <= 1}
                onClick={() => loadOperationLogs(logsPage - 1)}
              >
                上一页
              </button>
              <span className="px-3 py-1 text-sm">{logsPage} / {logsTotalPages}</span>
              <button
                className="px-3 py-1 border rounded text-sm disabled:opacity-50"
                disabled={logsPage >= logsTotalPages}
                onClick={() => loadOperationLogs(logsPage + 1)}
              >
                下一页
              </button>
            </div>
          )}
        </div>
      )}

      {/* 用户管理（仅管理员） */}
      {activeTab === 'users' && user?.role === 'admin' && (
        <div className="bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 200px)'}}>
          <div className="p-4 border-b flex-shrink-0">
            <h3 className="font-medium">用户管理</h3>
          </div>
          <div className="overflow-auto flex-1">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">用户名</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">显示名</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">角色</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">状态</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">最后登录</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {users.map(u => (
                  <tr key={u.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-xs text-gray-500">{u.id}</td>
                    <td className="px-3 py-2 text-xs font-medium text-gray-900">{u.username}</td>
                    <td className="px-3 py-2 text-xs text-gray-500">{u.display_name}</td>
                    <td className="px-3 py-2 text-xs">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        u.role === 'admin' ? 'bg-purple-100 text-purple-800' : 'bg-gray-100 text-gray-800'
                      }`}>
                        {u.role === 'admin' ? '管理员' : '编辑'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${
                        u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                      }`}>
                        {u.is_active ? '启用' : '禁用'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">{u.last_login?.replace('T', ' ').slice(0, 19) || '-'}</td>
                    <td className="px-3 py-2 text-xs space-x-1">
                      <button
                        onClick={() => resetUserPassword(u.id)}
                        className="text-blue-600 hover:underline"
                      >
                        重置密码
                      </button>
                      <button
                        onClick={() => toggleUserStatus(u.id, u.is_active)}
                        className={u.is_active ? 'text-red-600 hover:underline' : 'text-green-600 hover:underline'}
                      >
                        {u.is_active ? '禁用' : '启用'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
                <button onClick={saveExercise} className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">保存</button>
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
                <button onClick={saveSource} className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}

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
                <button onClick={saveChapter} className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">保存</button>
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
                <button onClick={saveKnowledgePoint} className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">保存</button>
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
                <div>教材: <span className="text-blue-600">{editingChunk.book_name}</span></div>
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
                <button onClick={saveChunk} className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">保存</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminPage
