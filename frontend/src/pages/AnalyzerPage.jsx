import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { ScanSearch, FileText, ClipboardEdit, TrendingUp, Crosshair, Brain, LogOut } from 'lucide-react'
import ResultDisplay from '../components/ResultDisplay'

const AUTH_API = 'https://api.momowan.xyz/api/auth'

function AnalyzerPage() {
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [mode, setMode] = useState('deep')
  const [generateReport, setGenerateReport] = useState(false)
  const [reviewChannel, setReviewChannel] = useState('evidence')
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)
  const reviewChannelOptions = [
    {
      id: 'evidence',
      label: '证据增强审题',
      help: '检索相关证据，校验审题结论。',
    },
    {
      id: 'agent_search',
      label: '智能体证据链路',
      help: '检索证据后获取带引用的答案，注入逐题审题。',
    },
    {
      id: 'model',
      label: '普通模型审题',
      help: '只走模型生成，不要求 证据服务门禁。',
    },
  ]
  const activeReviewChannel = reviewChannelOptions.find(option => option.id === reviewChannel) || reviewChannelOptions[0]

  // 认证状态
  const [token, setToken] = useState(() => localStorage.getItem('bio_token') || '')
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bio_user') || 'null') } catch { return null }
  })
  const [balance, setBalance] = useState(null)
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState('')

  // 加载积分余额
  const loadBalance = async (t) => {
    try {
      const resp = await axios.get('/api/credits/balance', { headers: { Authorization: `Bearer ${t}` } })
      setBalance(resp.data.data.balance)
    } catch (err) {
      if (err.response?.status === 401) { handleLogout(); return }
    }
  }

  useEffect(() => { if (token) loadBalance(token) }, [token])

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoginLoading(true)
    setLoginError('')
    try {
      const resp = await axios.post(`${AUTH_API}/login`, { email: loginEmail, password: loginPassword })
      const { token: t, user: u } = resp.data.data
      localStorage.setItem('bio_token', t)
      localStorage.setItem('bio_user', JSON.stringify(u))
      setToken(t)
      setUser(u)
      setBalance(u.credits)
    } catch (err) {
      setLoginError(err.response?.data?.error || '登录失败')
    } finally {
      setLoginLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('bio_token')
    localStorage.removeItem('bio_user')
    setToken('')
    setUser(null)
    setBalance(null)
    setResult(null)
  }

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0]
    if (selectedFile) {
      setFile(selectedFile)
      setError(null)
      setResult(null)
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    setDragOver(false)
  }

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

  const handleUpload = async () => {
    if (!file) { setError('请先选择文件'); return }
    if (!token) { setError('请先登录'); return }

    setLoading(true)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('mode', mode)
      formData.append('generate_report', generateReport)
      formData.append('exam_review_channel', reviewChannel)

      const response = await axios.post('/api/analyze_auto', formData, {
        headers: { 'Content-Type': 'multipart/form-data', Authorization: `Bearer ${token}` }
      })
      setResult(response.data)
      loadBalance(token) // 刷新余额
    } catch (err) {
      const status = err.response?.status
      const detail = err.response?.data?.detail
      if (status === 401) { handleLogout(); setError('登录已过期，请重新登录') }
      else if (status === 402) { setError(detail || '积分不足，请充值后再试') }
      else { setError(detail || '分析失败，请检查文件格式或网络连接') }
      if (import.meta.env.DEV) console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-[1200px] mx-auto px-6">
      {/* Hero 区域 — 大留白 */}
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
          style={{
            fontSize: '1.125rem',
            lineHeight: 1.7,
            color: 'var(--color-secondary)',
          }}
        >
          上传试卷（支持 DOCX 和 PDF 格式），AI 自动拆分并深度分析每道题目
        </p>
      </div>

      {/* 未登录：登录框 */}
      {!token && (
        <div className="max-w-md mx-auto" style={{ paddingBottom: '80px' }}>
          <div className="bg-white" style={{ borderRadius: '24px', border: '1px solid var(--color-border-light)', boxShadow: 'var(--shadow-lg)', padding: '36px' }}>
            <h2 className="text-center font-bold" style={{ color: 'var(--color-primary)', fontSize: '1.25rem', marginBottom: '8px' }}>登录使用</h2>
            <p className="text-center text-sm" style={{ color: 'var(--color-muted)', marginBottom: '28px' }}>使用 momowan.xyz 账号登录，每次分析消耗 200 积分</p>
            <form onSubmit={handleLogin}>
              <input type="email" placeholder="邮箱" value={loginEmail} onChange={e => setLoginEmail(e.target.value)} required
                className="input-modern" style={{ marginBottom: '12px' }} />
              <input type="password" placeholder="密码" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} required
                className="input-modern" style={{ marginBottom: '20px' }} />
              {loginError && <p style={{ color: '#991b1b', fontSize: '0.85rem', marginBottom: '12px' }}>{loginError}</p>}
              <button type="submit" disabled={loginLoading} className="w-full btn-primary" style={{ padding: '14px 0', fontSize: '15px' }}>
                {loginLoading ? '登录中...' : '登录'}
              </button>
            </form>
            <p className="text-center text-sm" style={{ color: 'var(--color-muted)', marginTop: '16px' }}>
              没有账号？<a href="https://momowan.xyz/register" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-primary-light)', textDecoration: 'underline' }}>去注册</a>
            </p>
          </div>
        </div>
      )}

      {/* 已登录：用户信息 + 上传区域 */}
      {token && <>
      {/* 用户信息栏 */}
      <div className="max-w-2xl mx-auto" style={{ marginBottom: '16px' }}>
        <div className="flex items-center justify-between" style={{ padding: '12px 20px', borderRadius: '16px', background: 'var(--macaron-mint-light)' }}>
          <div className="flex items-center gap-3">
            <span style={{ fontSize: '0.85rem', color: 'var(--color-primary)' }}>
              {user?.email || '已登录'}
            </span>
            <span style={{ fontSize: '0.85rem', color: 'var(--color-secondary)' }}>
              积分: <strong style={{ color: 'var(--color-primary)' }}>{balance ?? '...'}</strong>
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--color-muted)' }}>
              （每次分析消耗 200 积分）
            </span>
          </div>
          <button onClick={handleLogout} className="flex items-center gap-1 text-sm" style={{ color: 'var(--color-muted)', background: 'none', border: 'none', cursor: 'pointer' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--color-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--color-muted)'}>
            <LogOut size={14} /> 退出
          </button>
        </div>
      </div>

      {/* 上传区域 */}
      <div className="max-w-2xl mx-auto" style={{ paddingBottom: '80px' }}>
        <div
          className="bg-white"
          style={{
            borderRadius: '24px',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-lg)',
            padding: '36px',
          }}
        >
          {/* 拖拽上传区域 */}
          <div
            className={`upload-zone ${dragOver ? 'drag-over' : ''}`}
            style={{ marginBottom: '28px', padding: '48px 32px' }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx,.pdf"
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="text-center">
              {/* 装饰性插图圆 */}
              <div
                className="inline-flex items-center justify-center"
                style={{
                  width: '80px',
                  height: '80px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--macaron-mint-light), var(--macaron-mint))',
                  marginBottom: '20px',
                  boxShadow: '0 8px 24px rgba(200, 240, 212, 0.5)',
                }}
              >
                <svg className="w-10 h-10 text-[#1a2e1f]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-lg font-semibold mb-2" style={{ color: 'var(--color-primary)' }}>
                拖拽文件到这里，或点击选择文件
              </p>
              <p className="text-sm" style={{ color: 'var(--color-muted)' }}>
                支持 DOCX、PDF 格式，最大 50MB
              </p>
            </div>
          </div>

          {/* 已选文件信息 */}
          {file && (
            <div
              className="animate-fade-in"
              style={{
                marginBottom: '28px',
                padding: '16px 20px',
                background: 'linear-gradient(135deg, var(--macaron-mint-light), #f0faf3)',
                border: '1px solid #b8d1bf',
                borderRadius: '16px',
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div
                    className="flex items-center justify-center"
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      background: 'var(--macaron-mint)',
                      marginRight: '14px',
                    }}
                  >
                    {file.name.endsWith('.pdf') ? <FileText size={22} className="text-[#1a2e1f]" /> : <ClipboardEdit size={22} className="text-[#1a2e1f]" />}
                  </div>
                  <div>
                    <p className="font-semibold" style={{ color: 'var(--color-primary)' }}>{file.name}</p>
                    <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '2px' }}>{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                  className="transition-colors"
                  style={{ color: 'var(--color-muted)', padding: '6px' }}
                  onMouseEnter={e => { e.currentTarget.style.color = '#dc3545' }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--color-muted)' }}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* PDF报告生成选项 */}
          <div style={{ marginBottom: '28px' }}>
            <div
              style={{
                padding: '18px 20px',
                border: '2px solid var(--color-border-light)',
                borderRadius: '16px',
                background: 'var(--color-bg)',
              }}
            >
              <div className="flex items-center justify-between gap-3" style={{ marginBottom: '12px' }}>
                <span className="font-semibold flex items-center" style={{ color: 'var(--color-primary)' }}>
                  <Brain size={16} className="inline mr-1.5" /> 审题渠道
                </span>
                <span className="text-xs" style={{ color: 'var(--color-muted)' }}>
                  当前: {activeReviewChannel.label}
                </span>
              </div>
              <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
                {reviewChannelOptions.map(option => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setReviewChannel(option.id)}
                    className="transition-all"
                    style={{
                      minHeight: '72px',
                      padding: '10px 12px',
                      borderRadius: '12px',
                      border: reviewChannel === option.id ? '2px solid var(--color-primary-light)' : '1px solid var(--color-border-light)',
                      background: reviewChannel === option.id ? 'var(--macaron-mint-light)' : '#fff',
                      color: 'var(--color-primary)',
                      fontWeight: reviewChannel === option.id ? 700 : 500,
                      textAlign: 'left',
                    }}
                  >
                    <span style={{ display: 'block', marginBottom: '4px' }}>{option.label}</span>
                    <span className="text-xs" style={{ display: 'block', color: 'var(--color-muted)', lineHeight: 1.35, fontWeight: 500 }}>
                      {option.help}
                    </span>
                  </button>
                ))}
              </div>
              <p className="text-xs" style={{ marginTop: '10px', color: 'var(--color-muted)', lineHeight: 1.6 }}>
                {activeReviewChannel.help} 缺少必需证据会直接报错，不生成伪正常报告。
              </p>
            </div>
          </div>

          <div style={{ marginBottom: '28px' }}>
            <label
              className="flex items-center cursor-pointer transition-all"
              style={{
                padding: '18px 20px',
                border: generateReport ? '2px solid var(--color-primary-light)' : '2px solid var(--color-border-light)',
                borderRadius: '16px',
                background: generateReport ? 'var(--macaron-mint-light)' : 'var(--color-bg)',
                transition: 'var(--transition)',
              }}
              onMouseEnter={e => { if (!generateReport) { e.currentTarget.style.borderColor = '#b8d1bf' } }}
              onMouseLeave={e => { if (!generateReport) { e.currentTarget.style.borderColor = 'var(--color-border-light)' } }}
            >
              <input
                type="checkbox"
                checked={generateReport}
                onChange={(e) => setGenerateReport(e.target.checked)}
                className="h-5 w-5 text-[#1a2e1f] focus:ring-[#c8f0d4] rounded"
              />
              <div className="ml-4">
                <span className="font-semibold flex items-center" style={{ color: 'var(--color-primary)' }}>
                  <FileText size={16} className="inline mr-1.5" /> 生成PDF质量评估报告
                </span>
                <p className="text-sm mt-1" style={{ color: 'var(--color-muted)' }}>
                  包含难度曲线、素养分布等6张可视化图表（+10秒）
                </p>
              </div>
            </label>
          </div>

          {/* 开始分析按钮 */}
          <button
            onClick={handleUpload}
            disabled={!file || loading}
            className="w-full btn-primary"
            style={{ padding: '18px 0', fontSize: '17px', letterSpacing: '0.5px' }}
          >
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

          {/* 加载状态 */}
          {loading && (
            <div className="animate-fade-in" style={{ marginTop: '40px', textAlign: 'center' }}>
              <div
                className="inline-flex items-center justify-center"
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  background: 'var(--macaron-mint-light)',
                  marginBottom: '20px',
                }}
              >
                <div className="flex items-center space-x-2">
                  <div className="w-2.5 h-2.5 bg-[#1a2e1f] rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-2.5 h-2.5 bg-[#2d5a3d] rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-2.5 h-2.5 bg-[#5a9a6d] rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
              <p className="font-semibold" style={{ color: 'var(--color-primary)', fontSize: '16px' }}>
                正在拆分并分析试卷...
              </p>
              <p className="text-sm" style={{ color: 'var(--color-muted)', marginTop: '8px' }}>
                {mode === 'deep' ? '深度模式预计需要 2-3 分钟' : '快速模式预计需要 1 分钟'}
              </p>
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div
              className="animate-fade-in"
              style={{
                marginTop: '28px',
                padding: '18px 20px',
                background: 'var(--macaron-coral-light)',
                border: '1px solid var(--macaron-coral)',
                borderRadius: '16px',
              }}
            >
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

        {/* 功能特点 — macaron 风格卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6" style={{ marginTop: '64px' }}>
          {[
            {
              icon: <Crosshair size={28} />,
              title: '智能拆分',
              desc: '自动识别题目边界，精准拆分选择题和非选择题',
              bg: 'var(--macaron-blue-light)',
              accent: 'var(--macaron-blue)',
              iconBg: '#e0f2fe',
            },
            {
              icon: <TrendingUp size={28} />,
              title: '难度评估',
              desc: '多维度分析题目难度，生成难度曲线图',
              bg: 'var(--macaron-mint-light)',
              accent: 'var(--macaron-mint)',
              iconBg: '#c8f0d4',
            },
            {
              icon: <Brain size={28} />,
              title: '素养分析',
              desc: '评估生命观念、科学思维等核心素养覆盖',
              bg: 'var(--macaron-purple-light)',
              accent: 'var(--macaron-purple)',
              iconBg: '#ede9fe',
            },
          ].map((feat) => (
            <div
              key={feat.title}
              className="text-center"
              style={{
                padding: '36px 28px',
                borderRadius: '24px',
                background: feat.bg,
                border: `1px solid ${feat.accent}`,
                boxShadow: 'var(--shadow-sm)',
                transition: 'var(--transition)',
                cursor: 'default',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.transform = 'translateY(-6px)'
                e.currentTarget.style.boxShadow = 'var(--shadow-lg)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.transform = 'translateY(0)'
                e.currentTarget.style.boxShadow = 'var(--shadow-sm)'
              }}
            >
              <div
                className="inline-flex items-center justify-center"
                style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '16px',
                  background: feat.iconBg,
                  color: 'var(--color-primary)',
                  marginBottom: '16px',
                }}
              >
                {feat.icon}
              </div>
              <h3
                className="font-bold"
                style={{ color: 'var(--color-primary)', fontSize: '1.05rem', marginBottom: '8px' }}
              >
                {feat.title}
              </h3>
              <p style={{ color: 'var(--color-secondary)', fontSize: '0.875rem', lineHeight: 1.6 }}>
                {feat.desc}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* 结果展示 — 带分隔 */}
      {result && (
        <div style={{ paddingTop: '16px', paddingBottom: '48px' }}>
          <div
            style={{
              width: '80px',
              height: '4px',
              borderRadius: '50px',
              background: 'var(--macaron-mint)',
              margin: '0 auto 48px',
            }}
          />
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
