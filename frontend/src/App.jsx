import { Routes, Route, Link, useLocation } from 'react-router-dom'
import AnalyzerPage from './pages/AnalyzerPage'
import AdminPage from './pages/AdminPage'
import CorrectionPage from './pages/CorrectionPage'
import TextbookPage from './pages/TextbookPage'
import ExercisePage from './pages/ExercisePage'
import QuizGeneratorPage from './pages/QuizGeneratorPage'
import HistoryDataPage from './pages/HistoryDataPage'
import ErrorBoundary from './components/ErrorBoundary'

function App() {
  const location = useLocation()

  const navLinks = [
    { path: '/', label: '试卷分析', icon: '📊' },
    { path: '/quiz', label: '测验生成', icon: '📝' },
    { path: '/history', label: '历史数据', icon: '📈' },
    { path: '/exercises', label: '题库', icon: '📚' },
    { path: '/textbook', label: '教材资料', icon: '📖' },
    { path: '/admin', label: '管理后台', icon: '⚙️' },
  ]

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
            <div className="w-9 h-9 rounded-[10px] flex items-center justify-center text-white text-lg"
              style={{ background: 'var(--color-primary)' }}>
              🧬
            </div>
            <span className="text-lg font-bold hidden sm:inline"
              style={{ color: 'var(--color-primary)' }}>
              生物审题
            </span>
          </Link>

          {/* 导航链接 */}
          <div className="flex items-center gap-5">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className="no-underline text-[15px] font-medium py-1"
                style={{
                  color: location.pathname === link.path
                    ? 'var(--color-primary)'
                    : 'var(--color-secondary)',
                  fontWeight: location.pathname === link.path ? 600 : 500,
                  borderBottom: location.pathname === link.path
                    ? '2px solid var(--color-primary)'
                    : '2px solid transparent',
                  transition: 'var(--transition)',
                }}
              >
                <span className="hidden md:inline">{link.label}</span>
                <span className="md:hidden">{link.icon}</span>
              </Link>
            ))}
            {/* 返回 momowan 链接 */}
            <a href="https://momowan.xyz"
              className="no-underline text-[15px] font-medium ml-2 px-4 py-1.5 rounded-[50px]"
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
            <Route path="/quiz" element={<QuizGeneratorPage />} />
            <Route path="/history" element={<HistoryDataPage />} />
            <Route path="/exercises" element={<ExercisePage />} />
            <Route path="/textbook" element={<TextbookPage />} />
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

      {/* 页脚 */}
      <footer className="py-8 mt-auto" style={{ borderTop: '1px solid var(--color-border-light)' }}>
        <div className="max-w-[1200px] mx-auto px-6 text-center text-sm"
          style={{ color: 'var(--color-muted)' }}>
          <p>第三届湖南省基础教育教学改革研究项目</p>
          <p className="mt-1">基于DeepSeek 指向素养培育的高中生物试题审题模型的构建（25JGYB0860）</p>
        </div>
      </footer>
    </div>
  )
}

export default App
