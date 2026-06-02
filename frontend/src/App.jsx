import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import { ScanSearch } from 'lucide-react'
import AnalyzerPage from './pages/AnalyzerPage'
import AdminPage from './pages/AdminPage'
import CorrectionPage from './pages/CorrectionPage'
import ErrorBoundary from './components/ErrorBoundary'

const ExercisePage = React.lazy(() => import('./pages/ExercisePage'))
const TextbookPage = React.lazy(() => import('./pages/TextbookPage'))
const QuizGeneratorPage = React.lazy(() => import('./pages/QuizGeneratorPage'))
const HistoryDataPage = React.lazy(() => import('./pages/HistoryDataPage'))
const TokenStatsPage = React.lazy(() => import('./pages/admin/TokenStatsPage'))
const CalibrationPage = React.lazy(() => import('./pages/admin/CalibrationPage'))

function SuspenseFallback() {
  return (
    <div className="route-loading" role="status">
      加载中...
    </div>
  )
}

function LazyRoute({ Component }) {
  return (
    <React.Suspense fallback={<SuspenseFallback />}>
      <Component />
    </React.Suspense>
  )
}

function NotFoundPage() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="text-center">
        <div className="text-6xl mb-4">404</div>
        <h1 className="text-xl font-bold mb-2" style={{ color: 'var(--color-primary)' }}>
          页面不存在
        </h1>
        <Link to="/" style={{ color: 'var(--color-primary-light)' }} className="hover:underline">
          返回首页
        </Link>
      </div>
    </div>
  )
}

function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main-content" className="skip-link">
        跳到主要内容
      </a>

      <nav className="app-nav fixed top-0 left-0 right-0 z-[1000] border-b" aria-label="主导航">
        <div className="max-w-[1200px] mx-auto px-6 h-full flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 no-underline" aria-label="智能审题 首页">
            <div className="w-9 h-9 rounded-[10px] flex items-center justify-center text-white nav-brand-mark">
              <ScanSearch size={20} aria-hidden="true" />
            </div>
            <span className="text-lg font-bold hidden sm:inline" style={{ color: 'var(--color-primary)' }}>
              智能审题
            </span>
          </Link>

          <div className="flex items-center gap-4">
            <span className="text-[14px] hidden md:inline" style={{ color: 'var(--color-muted)' }}>
              AI 试卷分析系统
            </span>
            <a
              href="https://momowan.xyz"
              className="nav-external-link no-underline text-[15px] font-medium px-4 py-1.5"
              target="_blank"
              rel="noopener noreferrer"
              aria-label="打开 momowan.xyz"
            >
              momowan.xyz
            </a>
          </div>
        </div>
      </nav>

      <div className="app-nav-spacer" aria-hidden="true" />

      <main id="main-content" className="flex-1 animate-fade-in">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<AnalyzerPage />} />
            <Route path="/correction" element={<CorrectionPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/exercises" element={<LazyRoute Component={ExercisePage} />} />
            <Route path="/textbooks" element={<LazyRoute Component={TextbookPage} />} />
            <Route path="/quiz" element={<LazyRoute Component={QuizGeneratorPage} />} />
            <Route path="/history" element={<LazyRoute Component={HistoryDataPage} />} />
            <Route path="/admin/tokens" element={<LazyRoute Component={TokenStatsPage} />} />
            <Route path="/admin/calibration" element={<LazyRoute Component={CalibrationPage} />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </ErrorBoundary>
      </main>

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
