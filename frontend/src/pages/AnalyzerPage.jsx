import { useState, useRef, useEffect, useCallback } from 'react'
import axios from 'axios'
import { ScanSearch, FileText, ClipboardEdit, TrendingUp, Crosshair, Brain, LogOut } from 'lucide-react'
import ResultDisplay from '../components/ResultDisplay'

const isReviewMode = /^\d+\.\d+\.\d+\.\d+$/.test(window.location.hostname)
const AUTH_API = isReviewMode ? '/api/auth' : 'https://api.momowan.xyz/api/auth'

function AnalyzerPage() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('deep')
  const [generateReport, setGenerateReport] = useState(false)
  const [subject, setSubject] = useState('biology')
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState(null)
  const fileInputRef = useRef(null)
  const pollingRef = useRef(false)
  const SUBJECTS = [
    { key: 'chinese', name: '语文' }, { key: 'math', name: '数学' }, { key: 'english', name: '英语' },
    { key: 'physics', name: '物理' }, { key: 'chemistry', name: '化学' }, { key: 'biology', name: '生物' },
    { key: 'politics', name: '思想政治' }, { key: 'history', name: '历史' }, { key: 'geography', name: '地理' },
  ]

  const [token, setToken] = useState(() => localStorage.getItem('bio_token') || '')
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bio_user') || 'null') } catch { return null }
  })
  const [balance, setBalance] = useState(null)
  const [apiKeys, setApiKeys] = useState({ has_deepseek: false, has_qwen: false, deepseek_key_preview: null, qwen_key_preview: null, uses_system_keys: false })
  const [apiKeyForm, setApiKeyForm] = useState({ deepseek: '', qwen: '' })
  const [apiKeySaving, setApiKeySaving] = useState(false)
  const [apiKeyMsg, setApiKeyMsg] = useState('')
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState('')

  const loadBalance = async (t) => {
    if (isReviewMode) return
    try {
      const resp = await axios.get('/api/credits/balance', { headers: { Authorization: `Bearer ${t}` } })
      setBalance(resp.data.data.balance)
    } catch (err) {
      if (err.response?.status === 401) { handleLogout(); return }
    }
  }

  const loadApiKeys = async (t) => {
    if (!isReviewMode) return
    try {
      const resp = await axios.get('/api/auth/me/api-keys', { headers: { Authorization: `Bearer ${t}` } })
      setApiKeys(resp.data)
    } catch (err) {
      if (err.response?.status === 401) handleLogout()
    }
  }

  useEffect(() => { if (token && !isReviewMode) loadBalance(token) }, [token])
  useEffect(() => { if (token && isReviewMode) loadApiKeys(token) }, [token])

  useEffect(() => {
    return () => { pollingRef.current = false }
  }, [])

  // 页面加载时恢复未完成的分析任务（浏览器关闭重开后仍可跟踪后台任务）
  useEffect(() => {
    const pendingTaskId = localStorage.getItem('bio_task_id')
    if (pendingTaskId && token) {
      setLoading(true)
      setProgress({ progress: 0, total: 0, message: '恢复任务进度...' })
      pollTaskStatus(pendingTaskId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoginLoading(true)
    setLoginError('')
    try {
      if (isReviewMode) {
        const resp = await axios.post(`${AUTH_API}/login`, { username: loginEmail, password: loginPassword })
        if (!resp.data.success) { setLoginError(resp.data.message || '??????'); return }
        const { token: t, user: u } = resp.data
        localStorage.setItem('bio_token', t)
        localStorage.setItem('bio_user', JSON.stringify(u))
        setToken(t)
        setUser(u)
        if (u.uses_system_keys === false) loadApiKeys(t)
      } else {
        const resp = await axios.post(`${AUTH_API}/login`, { email: loginEmail, password: loginPassword })
        const { token: t, user: u } = resp.data.data
        localStorage.setItem('bio_token', t)
        localStorage.setItem('bio_user', JSON.stringify(u))
        setToken(t)
        setUser(u)
        setBalance(u.credits)
      }
    } catch (err) {
      setLoginError(err.response?.data?.error || '登录失败')
    } finally {
      setLoginLoading(false)
    }
  }

  const saveApiKeys = async () => {
    setApiKeySaving(true)
    setApiKeyMsg('')
    try {
      const body = {}
      if (apiKeyForm.deepseek) body.deepseek_api_key = apiKeyForm.deepseek
      if (apiKeyForm.qwen) body.qwen_api_key = apiKeyForm.qwen
      const resp = await axios.put('/api/auth/me/api-keys', body, { headers: { Authorization: `Bearer ${token}` } })
      setApiKeyMsg(resp.data.message)
      setApiKeyForm({ deepseek: '', qwen: '' })
      loadApiKeys(token)
    } catch (err) {
      setApiKeyMsg(err.response?.data?.detail || '保存失败')
    } finally {
      setApiKeySaving(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('bio_token')
    localStorage.removeItem('bio_user')
    setToken('')
    setUser(null)
    setBalance(null)
    setResult(null)
    pollingRef.current = false
  }

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    if (selectedFile) {
      setFile(selectedFile)
      setError(null)
      setResult(null)
    }
  }

  const handleDragOver = (e) => { e.preventDefault(); setDragOver(true) }
  const handleDragLeave = (e) => { e.preventDefault(); setDragOver(false) }
  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && (droppedFile.name.endsWith('.docx') || droppedFile.name.endsWith('.pdf'))) {
      setFile(droppedFile)
      setError(null)
      setResult(null)
    } else {
      setError('请上传 DOCX 或 PDF 格式的文件')
    }
  }

  const pollTaskStatus = useCallback((taskId) => {
    pollingRef.current = true
    const poll = async () => {
      if (!pollingRef.current) return
      try {
        const resp = await axios.get(`/api/analysis/status/${taskId}`)
        const data = resp.data
        setProgress({ progress: data.progress, total: data.total, message: data.message })

        if (data.status === 'completed') {
          pollingRef.current = false
          localStorage.removeItem('bio_task_id')
          setResult(data.result)
          setLoading(false)
          setProgress(null)
          if (!isReviewMode) loadBalance(token)
          return
        }
        if (data.status === 'failed') {
          pollingRef.current = false
          localStorage.removeItem('bio_task_id')
          setError(data.error || '分析失败')
          setLoading(false)
          setProgress(null)
          return
        }
        setTimeout(poll, 3000)
      } catch (err) {
        if (!pollingRef.current) return
        if (err.response?.status === 404) {
          pollingRef.current = false
          localStorage.removeItem('bio_task_id')
          setLoading(false)
          setProgress(null)
          return
        }
        setTimeout(poll, 5000)
      }
    }
    poll()
  }, [token])

  const handleUpload = async () => {
    if (!file) { setError('请先选择文件'); return }
    if (!token) { setError('请先登录'); return }

    setLoading(true)
    setError(null)
    setProgress(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('mode', mode)
      formData.append('generate_report', generateReport)
      formData.append('subject', subject)

      const response = await axios.post('/api/analyze_auto', formData, {
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${token}` }
      })

      const { task_id, total } = response.data
      localStorage.setItem('bio_task_id', task_id)
      setProgress({ progress: 0, total: total || 0, message: '任务已提交，开始分析...' })
      pollTaskStatus(task_id)
    } catch (err) {
      const status = err.response?.status
      const detail = err.response?.data?.detail
      if (status === 401) { handleLogout(); setError('登录已过期，请重新登录') }
      else if (status === 402) { setError(isReviewMode ? '服务暂时不可用' : (detail || '积分不足，请充值后再试')) }
      else { setError(detail || '提交失败，请检查文件格式或网络连接') }
      setLoading(false)
    }
  }

  const progressPercent = progress && progress.total > 0
    ? Math.round((progress.progress / progress.total) * 100)
    : 0

  return (
    <div className="max-w-[1200px] mx-auto px-6">
      {/* Hero 区域 */}
      <div className="text-center" style={{ paddingTop: '80px', paddingBottom: '64px' }}>
        <div
          className="inline-flex items-center justify-center w-24 h-24 text-white animate-float"
          style={{
            borderRadius: '28px',
            background: 'linear-gradient(135deg, #2d5a3d, #1a2e1f)',
            boxShadow: '0 16px 40px rgba(26, 46, 31, 0.2)',
            marginBottom: '32px',
          }}
        >
          <ScanSearch size={52} />
        </div>
        <h1
          className="font-extrabold tracking-tight"
          style={{
            fontSize: 'clamp(2.25rem, 5vw, 3.25rem)',
            color: 'var(--color-primary)',
            marginBottom: '16px',
            lineHeight: 1.15,
          }}
        >
          智能试卷分析系统
        </h1>
        <p
          className="max-w-xl mx-auto"
          style={{ fontSize: '1.125rem', lineHeight: 1.7, color: 'var(--color-secondary)' }}
        >
          上传试卷（支持 DOCX 和 PDF 格式），AI 自动拆分并深度分析每道题目
        </p>
      </div>

      {/* 未登录：登录框 */}
      {!token && (
        <div className="max-w-md mx-auto" style={{ paddingBottom: '80px' }}>
          <div className="bg-white" style={{ borderRadius: '24px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-lg)', padding: '36px' }}>
            <h2 className="text-center font-bold" style={{ color: 'var(--color-primary)', fontSize: '1.25rem', marginBottom: '8px' }}>登录使用</h2>
            <p className="text-center text-sm" style={{ color: 'var(--color-muted)', marginBottom: '28px' }}>{isReviewMode ? '使用评审账号登录体验系统' : '使用 momowan.xyz 账号登录，每次分析消耗 200 积分'}</p>
            <form onSubmit={handleLogin}>
              <input type={isReviewMode ? "text" : "email"} placeholder={isReviewMode ? "用户名" : "邮箱"} value={loginEmail} onChange={e => setLoginEmail(e.target.value)} required
                className="input-modern" style={{ marginBottom: '12px' }} />
              <input type="password" placeholder="密码" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} required
                className="input-modern" style={{ marginBottom: '20px' }} />
              {loginError && <p style={{ color: '#991b1b', fontSize: '0.85rem', marginBottom: '12px' }}>{loginError}</p>}
              <button type="submit" disabled={loginLoading} className="w-full btn-primary" style={{ padding: '14px 0', fontSize: '15px' }}>
                {loginLoading ? '登录中...' : '登录'}
              </button>
            </form>
            {!isReviewMode && (
              <p className="text-center text-sm" style={{ color: 'var(--color-muted)', marginTop: '16px' }}>
                没有账号？<a href="https://momowan.xyz/register" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-primary-light)', textDecoration: 'underline' }}>去注册</a>
              </p>
            )}
          </div>
        </div>
      )}

      {/* 已登录 */}
      {token && <>
      {/* 用户信息栏 */}
      <div className="max-w-2xl mx-auto" style={{ marginBottom: '16px' }}>
        <div className="flex items-center justify-between" style={{ padding: '12px 20px', borderRadius: '16px', background: 'var(--macaron-mint-light)' }}>
          <div className="flex items-center gap-3">
            <span style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>
              {isReviewMode ? (user?.display_name || user?.username || '评审员') : (user?.email || '已登录')}
            </span>
            {!isReviewMode && (<>
              <span style={{ fontSize: '0.85rem', color: 'var(--color-secondary)' }}>
                积分: <strong style={{ color: 'var(--color-primary)' }}>{balance ?? '...'}</strong>
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-muted)' }}>（每次分析消耗 200 积分）</span>
            </>)}
            {isReviewMode && (
              <span style={{ fontSize: '0.75rem', color: 'var(--color-muted)' }}>课题评审体验模式</span>
            )}
          </div>
          <button onClick={handleLogout} className="flex items-center gap-1 text-sm" style={{ color: 'var(--color-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--color-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--color-muted)'}>
            <LogOut size={14} /> 退出
          </button>
        </div>
      </div>

      {/* API Key 配置 */}
      {isReviewMode && !apiKeys.uses_system_keys && (
        <div className="max-w-2xl mx-auto" style={{ marginBottom: '16px' }}>
          <div style={{ padding: '24px', borderRadius: '20px', border: (apiKeys.has_deepseek && apiKeys.has_qwen) ? '1px solid #b8d1bf' : '2px solid #fde68a', background: (apiKeys.has_deepseek && apiKeys.has_qwen) ? '#f0faf3' : '#fffbeb' }}>
            <h3 className="font-bold" style={{ color: 'var(--color-primary)', fontSize: '1rem', marginBottom: '12px' }}>
              {(apiKeys.has_deepseek && apiKeys.has_qwen) ? '✓ API Key 已配置' : '请配置 API Key'}
            </h3>
            {(apiKeys.has_deepseek && apiKeys.has_qwen) ? (
              <div style={{ fontSize: '0.85rem', color: 'var(--color-secondary)' }}>
                <p>DeepSeek: {apiKeys.deepseek_key_preview}</p>
                <p style={{ marginTop: '4px' }}>Qwen: {apiKeys.qwen_key_preview}</p>
                <button onClick={() => setApiKeys(prev => ({ ...prev, has_deepseek: false }))} className="text-sm mt-2" style={{ color: 'var(--color-primary-light)', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer' }}>重新配置</button>
              </div>
            ) : (
              <>
                <p style={{ fontSize: '0.85rem', color: 'var(--color-muted)', marginBottom: '16px' }}>使用前需要填入您自己的 API Key，分析产生的费用由您的账户承担。</p>
                <div style={{ marginBottom: '10px' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-secondary)', marginBottom: '4px' }}>DeepSeek API Key</label>
                  <input type="password" placeholder="sk-..." value={apiKeyForm.deepseek} onChange={e => setApiKeyForm(p => ({ ...p, deepseek: e.target.value }))} className="input-modern" style={{ fontSize: '0.85rem' }} />
                </div>
                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-secondary)', marginBottom: '4px' }}>Qwen API Key (通义千问 / DashScope)</label>
                  <input type="password" placeholder="sk-..." value={apiKeyForm.qwen} onChange={e => setApiKeyForm(p => ({ ...p, qwen: e.target.value }))} className="input-modern" style={{ fontSize: '0.85rem' }} />
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={saveApiKeys} disabled={apiKeySaving || (!apiKeyForm.deepseek && !apiKeyForm.qwen)} className="btn-primary" style={{ padding: '10px 24px', fontSize: '14px' }}>
                    {apiKeySaving ? '保存中...' : '保存 Key'}
                  </button>
                  <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.8rem', color: 'var(--color-muted)' }}>获取 DeepSeek Key</a>
                  <a href="https://dashscope.console.aliyun.com/apiKey" target="_blank" rel="noopener noreferrer" style={{ fontSize: '0.8rem', color: 'var(--color-muted)' }}>获取 Qwen Key</a>
                </div>
                {apiKeyMsg && <p style={{ marginTop: '10px', fontSize: '0.85rem', color: apiKeyMsg.includes('失败') ? '#991b1b' : '#166534' }}>{apiKeyMsg}</p>}
              </>
            )}
          </div>
        </div>
      )}

      {/* 上传区域 */}
      <div className="max-w-2xl mx-auto" style={{ paddingBottom: '80px' }}>
        <div className="bg-white" style={{ borderRadius: '24px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-lg)', padding: '36px' }}>
          {/* 分值提示 */}
          <div
            style={{
              marginBottom: '20px',
              padding: '14px 18px',
              background: '#fffbeb',
              border: '1px solid #fde68a',
              borderRadius: '12px',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#b45309" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: '1px' }}>
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <p style={{ color: '#92400e', fontSize: '0.875rem', lineHeight: 1.6, margin: 0 }}>
              试题卷需要标注每一道大题的分值，否则分值预测将不准确。
            </p>
          </div>

          {/* 拖拽上传 */}
          <div
            className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
            style={{ marginBottom: '28px', padding: '48px 32px' }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input ref={fileInputRef} type="file" accept=".docx,.pdf" onChange={handleFileChange} className="hidden" />
            <div className="text-center">
              <div className="inline-flex items-center justify-center"
                style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'linear-gradient(135deg, var(--macaron-mint-light), var(--macaron-mint))', marginBottom: '20px', boxShadow: '0 8px 24px rgba(200, 240, 212, 0.5)' }}>
                <svg className="w-10 h-10 text-[#1a2e1f]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-lg font-semibold mb-2" style={{ color: 'var(--color-primary)' }}>拖拽文件到这里，或点击选择文件</p>
              <p className="text-sm" style={{ color: 'var(--color-muted)' }}>支持 DOCX、PDF 格式，最大 50MB</p>
            </div>
          </div>

          {/* 已选文件 */}
          {file && (
            <div className="animate-fade-in" style={{ marginBottom: '28px', padding: '16px 20px', background: 'linear-gradient(135deg, var(--macaron-mint-light), #f0faf3)', border: '1px solid #b8d1bf', borderRadius: '16px' }}>
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="flex items-center justify-center" style={{ width: '44px', height: '44px', borderRadius: '12px', background: 'var(--macaron-mint)', marginRight: '14px' }}>
                    {file.name.endsWith('.pdf') ? <FileText size={22} className="text-[#1a2e1f]" /> : <ClipboardEdit size={22} className="text-[#1a2e1f]" />}
                  </div>
                  <div>
                    <p className="font-semibold" style={{ color: 'var(--color-primary)' }}>{file.name}</p>
                    <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '2px' }}>{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                  </div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); setFile(null) }}
                  className="transition-colors" style={{ color: 'var(--color-muted)', padding: '6px' }}
                  onMouseEnter={e => { e.currentTarget.style.color = '#dc3545' }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--color-muted)' }}>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* 学科选择 */}
          <div style={{ marginBottom: '28px' }}>
            <div style={{ padding: '18px 20px', border: '2px solid var(--color-border-light)', borderRadius: '16px', background: 'var(--color-bg)' }}>
              <div className="flex items-center justify-between gap-3" style={{ marginBottom: '12px' }}>
                <span className="font-semibold" style={{ color: 'var(--color-primary)' }}>学科</span>
                <span className="text-xs" style={{ color: 'var(--color-muted)' }}>当前：{SUBJECTS.find(s => s.key === subject)?.name}</span>
              </div>
              <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(76px, 1fr))' }}>
                {SUBJECTS.map(s => (
                  <button key={s.key} type="button" onClick={() => setSubject(s.key)}
                    className="transition-all"
                    style={{
                      minHeight: '44px', padding: '8px 6px', borderRadius: '10px',
                      border: subject === s.key ? '2px solid var(--color-primary-light)' : '1px solid var(--color-border-light)',
                      background: subject === s.key ? 'var(--macaron-mint-light)' : '#fff',
                      color: 'var(--color-primary)',
                      fontWeight: subject === s.key ? 700 : 500,
                    }}>
                    {s.name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 报告选项 */}
          <div style={{ marginBottom: '28px' }}>
            <label className="flex items-center cursor-pointer transition-all"
              style={{
                padding: '18px 20px',
                border: generateReport ? '2px solid var(--color-primary-light)' : '2px solid var(--color-border-light)',
                borderRadius: '16px',
                background: generateReport ? 'var(--macaron-mint-light)' : 'var(--color-bg)',
                transition: 'var(--transition)',
              }}
              onMouseEnter={e => { if (!generateReport) e.currentTarget.style.borderColor = '#b8d1bf' }}
              onMouseLeave={e => { if (!generateReport) e.currentTarget.style.borderColor = 'var(--color-border-light)' }}>
              <input type="checkbox" checked={generateReport} onChange={(e) => setGenerateReport(e.target.checked)}
                className="h-5 w-5 text-[#1a2e1f] focus:ring-[#c8f0d4] rounded" />
              <div className="ml-4">
                <span className="font-semibold flex items-center" style={{ color: 'var(--color-primary)' }}>
                  <FileText size={16} className="inline mr-1.5" /> 生成质量评估报告
                </span>
                <p className="text-sm mt-1" style={{ color: 'var(--color-muted)' }}>包含难度曲线、素养分布等可视化图表（HTML 在线报告）</p>
              </div>
            </label>
          </div>

          {/* 开始分析按钮 */}
          <button onClick={handleUpload} disabled={!file || loading}
            className="w-full btn-primary" style={{ padding: '18px 0', fontSize: '17px', letterSpacing: '0.5px' }}>
            {loading ? (
              <span className="flex items-center justify-center">
                <div className="loader mr-3" style={{ width: '24px', height: '24px', borderWidth: '3px' }}></div>
                分析中...
              </span>
            ) : (
              <span className="flex items-center justify-center">
                <svg className="w-6 h-6 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                开始分析
              </span>
            )}
          </button>

          {/* 分析进度 */}
          {loading && (
            <div className="animate-fade-in" style={{ marginTop: '40px', textAlign: 'center' }}>
              <div className="inline-flex items-center justify-center"
                style={{ width: '64px', height: '64px', borderRadius: '50%', background: 'var(--macaron-mint-light)', marginBottom: '20px' }}>
                <div className="flex items-center space-x-2">
                  <div className="w-2.5 h-2.5 bg-[#1a2e1f] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2.5 h-2.5 bg-[#2d5a3d] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2.5 h-2.5 bg-[#5a9a6d] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>

              {progress ? (
                <>
                  <p className="font-semibold" style={{ color: 'var(--color-primary)', fontSize: '16px' }}>
                    {progress.message || `正在分析第 ${progress.progress}/${progress.total} 题...`}
                  </p>
                  {progress.total > 0 && (
                    <div style={{ maxWidth: '320px', margin: '16px auto 0' }}>
                      <div style={{
                        height: '8px', borderRadius: '4px',
                        background: 'var(--color-border-light)', overflow: 'hidden',
                      }}>
                        <div style={{
                          height: '100%', borderRadius: '4px',
                          background: 'linear-gradient(90deg, #2d5a3d, #5a9a6d)',
                          width: `${progressPercent}%`,
                          transition: 'width 0.5s ease',
                        }} />
                      </div>
                      <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '8px' }}>
                        {progress.progress}/{progress.total} 题 ({progressPercent}%)
                      </p>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <p className="font-semibold" style={{ color: 'var(--color-primary)', fontSize: '16px' }}>正在提交文件...</p>
                  <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '8px' }}>文件解析中，请稍候</p>
                </>
              )}
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="animate-fade-in" style={{ marginTop: '28px', padding: '18px 20px', background: 'var(--macaron-coral-light)', border: '1px solid var(--macaron-coral)', borderRadius: '16px' }}>
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <p className="ml-3 text-[#991b1b]">{error}</p>
              </div>
            </div>
          )}
        </div>

        {/* 功能特点卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6" style={{ marginTop: '64px' }}>
          {[
            { icon: <Crosshair size={28} />, title: '智能拆分', desc: '自动识别题目边界，精准拆分选择题和非选择题', bg: 'var(--macaron-blue-light)', accent: 'var(--macaron-blue)', iconBg: '#e0f2fe' },
            { icon: <TrendingUp size={28} />, title: '难度评估', desc: '多维度分析题目难度，生成难度曲线图', bg: 'var(--macaron-mint-light)', accent: 'var(--macaron-mint)', iconBg: '#c8f0d4' },
            { icon: <Brain size={28} />, title: '素养分析', desc: '评估生命观念、科学思维等核心素养覆盖', bg: 'var(--macaron-purple-light)', accent: 'var(--macaron-purple)', iconBg: '#ede9fe' },
          ].map((feat) => (
            <div key={feat.title} className="text-center"
              style={{ padding: '36px 28px', borderRadius: '24px', background: feat.bg, border: `1px solid ${feat.accent}`, boxShadow: 'var(--shadow-sm)', transition: 'var(--transition)', cursor: 'default' }}
              onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-6px)'; e.currentTarget.style.boxShadow = 'var(--shadow-lg)' }}
              onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = 'var(--shadow-sm)' }}>
              <div className="inline-flex items-center justify-center"
                style={{ width: '56px', height: '56px', borderRadius: '16px', background: feat.iconBg, color: 'var(--color-primary)', marginBottom: '16px' }}>
                {feat.icon}
              </div>
              <h3 className="font-bold" style={{ color: 'var(--color-primary)', fontSize: '1.05rem', marginBottom: '8px' }}>{feat.title}</h3>
              <p style={{ color: 'var(--color-secondary)', fontSize: '0.875rem', lineHeight: 1.6 }}>{feat.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* 结果展示 */}
      {result && (
        <div style={{ paddingTop: '16px', paddingBottom: '48px' }}>
          <div style={{ width: '80px', height: '4px', borderRadius: '50px', background: 'var(--macaron-mint)', margin: '0 auto 48px' }} />
          <div className="animate-fade-in">
            <ResultDisplay data={result} />
          </div>
        </div>
      )}
      </>}
    </div>
  )
}

export default AnalyzerPage
