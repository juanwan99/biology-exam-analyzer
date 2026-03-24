import { useState, useEffect } from 'react'
import axios from 'axios'

function LogsTab({ token, getHeaders }) {
  const [operationLogs, setOperationLogs] = useState([])
  const [logsPage, setLogsPage] = useState(1)
  const [logsTotal, setLogsTotal] = useState(0)
  const [logsTotalPages, setLogsTotalPages] = useState(1)
  const [logsLoading, setLogsLoading] = useState(false)

  const loadOperationLogs = async (page = 1) => {
    setLogsLoading(true)
    try {
      const res = await axios.get('/api/auth/logs', {
        params: { page, page_size: 50 },
        headers: getHeaders()
      })
      setOperationLogs(res.data.logs || [])
      setLogsPage(res.data.page)
      setLogsTotal(res.data.total)
      setLogsTotalPages(res.data.total_pages)
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载操作日志失败:', err)
    } finally {
      setLogsLoading(false)
    }
  }

  // 格式化操作类型
  const formatOperation = (op) => {
    const opMap = {
      'login': '登录',
      'logout': '登出',
      'create': '创建',
      'update': '更新',
      'delete': '删除',
      'batch_delete': '批量删除',
      'change_password': '修改密码',
      'reset_password': '重置密码'
    }
    return opMap[op] || op
  }

  // 格式化目标类型
  const formatTargetType = (type) => {
    const typeMap = {
      'exercise': '题目',
      'source': '来源',
      'chapter': '章节',
      'content': '内容',
      'knowledge_point': '知识点',
      'version': '版本',
      'user': '用户'
    }
    return typeMap[type] || type
  }

  // 初始加载
  useEffect(() => {
    loadOperationLogs(1)
  }, [])

  return (
    <div className="bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 200px)'}}>
      <div className="p-4 border-b flex-shrink-0">
        <h3 className="font-medium">操作日志 (共 {logsTotal} 条)</h3>
      </div>
      {logsLoading ? (
        <div className="p-8 text-center text-gray-500">加载中...</div>
      ) : (
        <div className="overflow-auto flex-1">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">时间</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">用户</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">对象类型</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">对象</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">IP</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {operationLogs.map(log => (
                <tr key={log.id} className="hover:bg-gray-50">
                  <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">{log.created_at?.replace('T', ' ').slice(0, 19)}</td>
                  <td className="px-3 py-2 text-xs font-medium text-gray-900">{log.username}</td>
                  <td className="px-3 py-2 text-xs">
                    <span className={`px-1.5 py-0.5 rounded text-xs ${
                      log.operation === 'delete' || log.operation === 'batch_delete' ? 'bg-red-100 text-red-800' :
                      log.operation === 'create' ? 'bg-green-100 text-green-800' :
                      log.operation === 'update' ? 'bg-[#c8f0d4] text-[#0a120c]' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {formatOperation(log.operation)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">{formatTargetType(log.target_type)}</td>
                  <td className="px-3 py-2 text-xs text-gray-500 max-w-[200px] truncate" title={log.target_name}>
                    {log.target_name || '-'}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-400">{log.ip_address || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* 分页 */}
      {logsTotalPages > 1 && (
        <div className="p-3 border-t flex justify-center gap-2 flex-shrink-0">
          <button
            className="px-3 py-1 border rounded text-sm disabled:opacity-50"
            disabled={logsPage <= 1}
            onClick={() => loadOperationLogs(logsPage - 1)}
          >
            上一页
          </button>
          <span className="px-3 py-1 text-sm">{logsPage} / {logsTotalPages}</span>
          <button
            className="px-3 py-1 border rounded text-sm disabled:opacity-50"
            disabled={logsPage >= logsTotalPages}
            onClick={() => loadOperationLogs(logsPage + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}

export default LogsTab
