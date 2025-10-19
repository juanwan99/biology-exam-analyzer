import { useState, useEffect } from 'react'
import axios from 'axios'

function AdminPage() {
  const [password, setPassword] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [activeTab, setActiveTab] = useState('prompts') // prompts | logs

  const [prompts, setPrompts] = useState({ split: '', analysis: '' })
  const [editingPrompt, setEditingPrompt] = useState('split')
  const [promptContent, setPromptContent] = useState('')

  const [logs, setLogs] = useState([])
  const [selectedLog, setSelectedLog] = useState(null)
  const [logContent, setLogContent] = useState('')

  // 认证
  const handleLogin = async () => {
    try {
      const response = await axios.get('/api/admin/prompts', {
        headers: { 'X-Admin-Password': password }
      })
      setAuthenticated(true)
      setPrompts(response.data)
      setPromptContent(response.data.split)
      await fetchLogs()
    } catch (err) {
      alert('密码错误')
    }
  }

  // 加载日志列表
  const fetchLogs = async () => {
    try {
      const response = await axios.get('/api/admin/logs/list', {
        headers: { 'X-Admin-Password': password }
      })
      setLogs(response.data.logs)
    } catch (err) {
      console.error('获取日志列表失败', err)
    }
  }

  // 查看日志
  const viewLog = async (date) => {
    try {
      const response = await axios.get(`/api/admin/logs?date=${date}`, {
        headers: { 'X-Admin-Password': password }
      })
      setSelectedLog(date)
      setLogContent(response.data.content)
    } catch (err) {
      alert('日志加载失败')
    }
  }

  // 下载日志
  const downloadLog = (date) => {
    window.open(`/api/admin/logs/download/${date}?password=${password}`, '_blank')
  }

  // 保存Prompt
  const savePrompt = async () => {
    try {
      await axios.put(
        '/api/admin/prompts',
        { type: editingPrompt, content: promptContent },
        { headers: { 'X-Admin-Password': password } }
      )
      alert('保存成功！')
      setPrompts({ ...prompts, [editingPrompt]: promptContent })
    } catch (err) {
      alert('保存失败')
    }
  }

  // 切换编辑的Prompt
  const switchPrompt = (type) => {
    setEditingPrompt(type)
    setPromptContent(prompts[type])
  }

  if (!authenticated) {
    return (
      <div className="max-w-md mx-auto mt-20">
        <div className="bg-white shadow rounded-lg p-8">
          <h2 className="text-2xl font-bold mb-6 text-center">管理员登录</h2>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入管理员密码"
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
    <div className="max-w-7xl mx-auto py-12 px-4 sm:px-6 lg:px-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">管理后台</h1>

      {/* 标签页 */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('prompts')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'prompts'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Prompt管理
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'logs'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            日志查看
          </button>
        </nav>
      </div>

      {/* Prompt管理 */}
      {activeTab === 'prompts' && (
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex gap-4 mb-6">
            <button
              onClick={() => switchPrompt('split')}
              className={`px-4 py-2 rounded ${
                editingPrompt === 'split'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700'
              }`}
            >
              拆分Prompt
            </button>
            <button
              onClick={() => switchPrompt('analysis')}
              className={`px-4 py-2 rounded ${
                editingPrompt === 'analysis'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700'
              }`}
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
            <span className="text-sm text-gray-600">
              字符数: {promptContent.length}
            </span>
            <button
              onClick={savePrompt}
              className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700"
            >
              保存并生效
            </button>
          </div>
        </div>
      )}

      {/* 日志查看 */}
      {activeTab === 'logs' && (
        <div className="grid grid-cols-3 gap-6">
          {/* 日志列表 */}
          <div className="bg-white shadow rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">日志文件列表</h3>
            <div className="space-y-2">
              {logs.map((log) => (
                <div
                  key={log.date}
                  className="p-3 border border-gray-200 rounded hover:bg-gray-50 cursor-pointer"
                  onClick={() => viewLog(log.date)}
                >
                  <div className="font-medium">{log.date}.log</div>
                  <div className="text-xs text-gray-500">
                    {(log.size / 1024).toFixed(2)} KB
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      downloadLog(log.date)
                    }}
                    className="text-xs text-blue-600 hover:underline mt-1"
                  >
                    下载
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* 日志内容 */}
          <div className="col-span-2 bg-white shadow rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4">
              {selectedLog ? `${selectedLog}.log` : '请选择日志文件'}
            </h3>
            <div className="bg-gray-900 text-green-400 p-4 rounded font-mono text-xs overflow-auto max-h-[600px]">
              {logContent || '暂无内容'}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminPage
