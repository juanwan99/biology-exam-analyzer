import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { Lock, User, LogOut, BookOpen, FileText, Terminal, ScrollText, Users } from 'lucide-react'
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
      <div className="min-h-[70vh] flex items-center justify-center px-4">
        <div className="w-full max-w-[400px] animate-fade-in">
          <div className="text-center mb-8">
            <div className="w-14 h-14 rounded-2xl mx-auto mb-4 flex items-center justify-center text-white"
              style={{ background: 'var(--color-primary)', boxShadow: 'var(--shadow-md)' }}>
              <Lock size={24} />
            </div>
            <h2 className="text-2xl font-bold" style={{ color: 'var(--color-primary)' }}>管理后台</h2>
            <p className="mt-2 text-sm" style={{ color: 'var(--color-muted)' }}>请输入管理员凭证</p>
          </div>

          <div style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-lg)',
            background: 'rgba(255, 255, 255, 0.92)',
            backdropFilter: 'blur(12px)',
            padding: '32px',
          }}>
            {loginError && (
              <div className="alert alert-error mb-5 text-sm">{loginError}</div>
            )}
            <div className="mb-4">
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2"
                style={{ color: 'var(--color-secondary)' }}>用户名</label>
              <div className="relative">
                <User size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-muted)' }} />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="请输入用户名"
                  className="input-modern"
                  style={{ paddingLeft: '40px' }}
                />
              </div>
            </div>
            <div className="mb-6">
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2"
                style={{ color: 'var(--color-secondary)' }}>密码</label>
              <div className="relative">
                <Lock size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2"
                  style={{ color: 'var(--color-muted)' }} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="请输入密码"
                  className="input-modern"
                  style={{ paddingLeft: '40px' }}
                  onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                />
              </div>
            </div>
            <button onClick={handleLogin} className="btn-primary w-full">
              登录
            </button>
          </div>
        </div>
      </div>
    )
  }

  const tabs = [
    { key: 'exercises', label: '题库管理', icon: BookOpen },
    { key: 'textbook', label: '教材管理', icon: FileText },
    { key: 'prompts', label: 'Prompt管理', icon: Terminal },
    { key: 'logs', label: '操作日志', icon: ScrollText },
    ...(user?.role === 'admin' ? [{ key: 'users', label: '用户管理', icon: Users }] : [])
  ]

  return (
    <div className="max-w-[1200px] mx-auto py-8 px-6">
      <div className="flex justify-between items-center mb-8">
        <h1 className="page-title">管理后台</h1>
        <div className="flex items-center gap-4">
          <span className="badge badge-primary">
            {user?.display_name || user?.username}
            {user?.role === 'admin' && ' (管理员)'}
          </span>
          <button onClick={handleLogout}
            className="inline-flex items-center gap-1.5 text-sm font-medium px-4 py-2 rounded-full"
            style={{ color: 'var(--danger)', transition: 'var(--transition)' }}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--macaron-coral-light)'}
            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
          >
            <LogOut size={14} /> 退出
          </button>
        </div>
      </div>

      {/* 标签页 */}
      <div className="mb-8" style={{ borderBottom: '1px solid var(--color-border-light)' }}>
        <nav className="-mb-px flex gap-1">
          {tabs.map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.key
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className="inline-flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors"
                style={{
                  borderColor: isActive ? 'var(--color-primary-light)' : 'transparent',
                  color: isActive ? 'var(--color-primary)' : 'var(--color-muted)',
                }}
              >
                <Icon size={15} /> {tab.label}
              </button>
            )
          })}
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
