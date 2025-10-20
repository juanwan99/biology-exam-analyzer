import { Routes, Route, Link } from 'react-router-dom'
import AnalyzerPage from './pages/AnalyzerPage'
import AdminPage from './pages/AdminPage'
import CorrectionPage from './pages/CorrectionPage'

function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* 导航栏 */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex space-x-8">
              <Link
                to="/"
                className="inline-flex items-center px-1 pt-1 text-gray-900 font-medium border-b-2 border-transparent hover:border-blue-500"
              >
                试卷分析
              </Link>
              <Link
                to="/admin"
                className="inline-flex items-center px-1 pt-1 text-gray-900 font-medium border-b-2 border-transparent hover:border-blue-500"
              >
                管理后台
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* 路由 */}
      <Routes>
        <Route path="/" element={<AnalyzerPage />} />
        <Route path="/correction" element={<CorrectionPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </div>
  )
}

export default App
