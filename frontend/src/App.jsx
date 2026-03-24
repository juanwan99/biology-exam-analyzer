import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { ScanSearch } from 'lucide-react'
import AnalyzerPage from './pages/AnalyzerPage'
import AdminPage from './pages/AdminPage'
import CorrectionPage from './pages/CorrectionPage'
import ErrorBoundary from './components/ErrorBoundary'

function App() {
  const location = useLocation()

  return (
    <div className="min-h-screen flex flex-col">
      {/* momowan 风格导航栏 */}
      <nav className="fixed top-0 left-0 right-0 z-[1000] h-[68px] border-b"
        style={{
          background: 'rgba(255, 255, 255, 0.92)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)',
          borderColor: 'var(--color-border-light)',
        }}
      >
        <div className="max-w-[1200px] mx-auto px-6 h-full flex items-center justify-between">
          {/* 品牌 */}
          <Link to="/" className="flex items-center gap-2.5 no-underline">
            <div className="w-9 h-9 rounded-[10px] flex items-center justify-center text-white"
              style={{ background: 'var(--color-primary)' }}>
              <ScanSearch size={20} />
            </div>
            <span className="text-lg font-bold hidden sm:inline"
              style={{ color: 'var(--color-primary)' }}>
              智能审题
            </span>
          </Link>

          {/* 右侧 */}
          <div className="flex items-center gap-4">
            <span className="text-[14px] hidden md:inline"
              style={{ color: 'var(--color-muted)' }}>
              AI 试卷分析系统
            </span>
            <a href="https://momowan.xyz"
              className="no-underline text-[15px] font-medium px-4 py-1.5 rounded-[50px]"
              style={{
                color: 'var(--color-primary)',
                border: '1.5px solid var(--color-border)',
                transition: 'var(--transition)',
              }}
              onMouseEnter={e => { e.target.style.borderColor = 'var(--color-primary-light)'; e.target.style.background = 'var(--macaron-mint-light)'; }}
              onMouseLeave={e => { e.target.style.borderColor = 'var(--color-border)'; e.target.style.background = 'transparent'; }}
            >
              momowan.xyz
            </a>
          </div>
        </div>
      </nav>

      {/* 顶部占位（fixed nav 高度） */}
      <div className="h-[68px]" />

      {/* 路由 */}
      <main className="flex-1 animate-fade-in">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<AnalyzerPage />} />
            <Route path="/correction" element={<CorrectionPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="*" element={
              <div className="min-h-[60vh] flex items-center justify-center">
                <div className="text-center">
                  <div className="text-6xl mb-4">404</div>
                  <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--color-primary)' }}>
                    页面不存在
                  </h2>
                  <Link to="/" style={{ color: 'var(--color-primary-light)' }}
                    className="hover:underline">返回首页</Link>
                </div>
              </div>
            } />
          </Routes>
        </ErrorBoundary>
      </main>

      {/* 页脚 — 带渐变分隔 */}
      <footer className="mt-auto" style={{ paddingTop: '0' }}>
        <div
          style={{
            height: '1px',
            background: 'linear-gradient(90deg, transparent 0%, var(--color-border) 50%, transparent 100%)',
          }}
        />
        <div
          className="max-w-[1200px] mx-auto px-6 text-center text-sm"
          style={{ color: 'var(--color-muted)', padding: '48px 24px' }}
        >
          <p style={{ fontWeight: 500 }}>第三届湖南省基础教育教学改革研究项目</p>
          <p style={{ marginTop: '8px', lineHeight: 1.6 }}>
            基于DeepSeek 指向素养培育的高中生物试题审题模型的构建（25JGYB0860）
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App
