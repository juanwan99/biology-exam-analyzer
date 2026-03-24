import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import ExercisesTab from './admin/ExercisesTab'
import TextbookTab from './admin/TextbookTab'
import PromptsTab from './admin/PromptsTab'
import LogsTab from './admin/LogsTab'
import UsersTab from './admin/UsersTab'

function AdminPage() {
  // 认证状态
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [user, setUser] = useState(null)
  const [authenticated, setAuthenticated] = useState(false)
  const [loginError, setLoginError] = useState('')

  const [activeTab, setActiveTab] = useState('exercises') // exercises | textbook | prompts | logs | users

  // API Headers - 使用Bearer Token
  const getHeaders = useCallback(() => ({ 'Authorization': `Bearer ${token}` }), [token])

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
      if (import.meta.env.DEV) console.error('登出失败:', err)
    }
    setAuthenticated(false)
    setToken('')
    setUser(null)
    localStorage.removeItem('authToken')
    localStorage.removeItem('authUser')
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
            className="w-full bg-[#1a2e1f] text-white py-2 px-4 rounded-lg hover:bg-[#0f1c13]"
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
            {user?.role === 'admin' && <span className="ml-1 text-[#1a2e1f]">(管理员)</span>}
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
                  ? 'border-[#2d5a3d] text-[#1a2e1f]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === 'exercises' && <ExercisesTab token={token} getHeaders={getHeaders} />}
      {activeTab === 'textbook' && <TextbookTab token={token} getHeaders={getHeaders} />}
      {activeTab === 'prompts' && <PromptsTab token={token} getHeaders={getHeaders} />}
      {activeTab === 'logs' && <LogsTab token={token} getHeaders={getHeaders} />}
      {activeTab === 'users' && <UsersTab token={token} getHeaders={getHeaders} user={user} />}
    </div>
  )
}

export default AdminPage
