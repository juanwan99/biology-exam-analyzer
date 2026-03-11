import { Routes, Route, Link, useLocation } from 'react-router-dom'
import AnalyzerPage from './pages/AnalyzerPage'
import AdminPage from './pages/AdminPage'
import CorrectionPage from './pages/CorrectionPage'
import TextbookPage from './pages/TextbookPage'
import ExercisePage from './pages/ExercisePage'
import QuizGeneratorPage from './pages/QuizGeneratorPage'
import HistoryDataPage from './pages/HistoryDataPage'

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
    <div className="min-h-screen">
      {/* 导航栏 */}
      <nav className="bg-white/80 backdrop-blur-md shadow-sm border-b border-gray-200/50 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            {/* 品牌标识 */}
            <div className="flex items-center">
              <Link to="/" className="flex items-center space-x-3 group">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg group-hover:shadow-xl transition-all">
                  <span className="text-white text-xl">🧬</span>
                </div>
                <div className="hidden sm:block">
                  <h1 className="text-lg font-bold text-gray-900">生物试卷分析</h1>
                  <p className="text-xs text-gray-500">AI智能审题系统</p>
                </div>
              </Link>
            </div>

            {/* 导航链接 */}
            <div className="flex items-center space-x-1">
              {navLinks.map((link) => (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`
                    flex items-center px-4 py-2 rounded-lg font-medium text-sm
                    transition-all duration-200 ease-in-out
                    ${location.pathname === link.path
                      ? 'bg-blue-50 text-blue-600 shadow-sm'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }
                  `}
                >
                  <span className="mr-2">{link.icon}</span>
                  <span className="hidden md:inline">{link.label}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </nav>

      {/* 路由 */}
      <main className="animate-fade-in">
        <Routes>
          <Route path="/" element={<AnalyzerPage />} />
          <Route path="/correction" element={<CorrectionPage />} />
          <Route path="/quiz" element={<QuizGeneratorPage />} />
          <Route path="/history" element={<HistoryDataPage />} />
          <Route path="/exercises" element={<ExercisePage />} />
          <Route path="/textbook" element={<TextbookPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>

      {/* 页脚 */}
      <footer className="bg-white/50 border-t border-gray-200/50 mt-auto py-6">
        <div className="max-w-7xl mx-auto px-4 text-center text-sm text-gray-500">
          <p>第三届湖南省基础教育教学改革研究项目</p>
          <p className="mt-1">基于DeepSeek 指向素养培育的高中生物试题审题模型的构建（25JGYB0860）</p>
        </div>
      </footer>
    </div>
  )
}

export default App
