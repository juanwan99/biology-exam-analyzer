import { useState, useEffect } from 'react'
import axios from 'axios'
import ListTable from '../../components/ListTable'
import { encodeListQuery } from '../../lib/listQuery'

const operations = {
  login: '登录', logout: '登出', create: '创建', update: '更新', delete: '删除',
  batch_delete: '批量删除', change_password: '修改密码', reset_password: '重置密码', update_api_keys: '更新 API Key',
}
const targets = {
  exercise: '题目', source: '来源', chapter: '章节', content: '内容',
  knowledge_point: '知识点', version: '版本', user: '用户',
}
const options = labels => Object.entries(labels).map(([value, label]) => ({ value, label }))
const columns = [
  { key: 'created_at', header: '时间', type: 'date', accessor: row => row.created_at, firstDir: 'desc' },
  { key: 'username', header: '用户', type: 'text', accessor: row => row.username },
  { key: 'operation', header: '操作', type: 'enum', accessor: row => row.operation, options: options(operations) },
  { key: 'target_type', header: '对象类型', type: 'enum', accessor: row => row.target_type, options: options(targets) },
  { key: 'target_name', header: '对象', type: 'text', accessor: row => row.target_name },
  { key: 'ip_address', header: 'IP', type: 'text', accessor: row => row.ip_address },
]

function LogsTab({ getHeaders }) {
  const [request, setRequest] = useState({ query: { sort: null, filters: {} }, page: 1 })
  const [result, setResult] = useState(null)
  const { query, page: logsPage } = request
  const { logs = [], total: logsTotal = 0, total_pages: logsTotalPages = 0, has_data: hasData } = result?.data ?? {}
  const logsLoading = result?.request !== request
  const loadError = !logsLoading && result.error

  useEffect(() => {
    const controller = new AbortController()
    const params = encodeListQuery(request.query)
    params.set('page', request.page)
    axios.get('/api/auth/logs', { params, headers: getHeaders(), signal: controller.signal })
      .then(({ data }) => setResult({ request, data }))
      .catch(err => {
        if (axios.isCancel(err)) return
        if (import.meta.env.DEV) console.error('加载操作日志失败:', err)
        setResult({ request, error: true })
      })
    return () => controller.abort()
  }, [request, getHeaders])

  return (
    <div className={`bg-white shadow rounded-lg flex flex-col ${logsLoading || loadError ? '[&_tbody]:hidden' : ''}`}
      style={{ maxHeight: 'calc(100vh - 200px)' }} aria-busy={logsLoading}>
      <div className="p-4 border-b flex-shrink-0">
        <h3 className="font-medium">操作日志 (共 {logsTotal} 条)</h3>
      </div>
      <ListTable columns={columns} rows={logs} rowKey="id" mode="server" query={query} hasData={hasData}
        onQueryChange={next => setRequest({ query: next, page: 1 })} emptyText="暂无操作日志"
        renderRow={log => (
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">{log.created_at?.replace('T', ' ').slice(0, 19)}</td>
            <td className="px-3 py-2 text-xs font-medium text-gray-900">{log.username}</td>
            <td className="px-3 py-2 text-xs">
              <span className={`px-1.5 py-0.5 rounded text-xs ${
                log.operation === 'delete' || log.operation === 'batch_delete' ? 'bg-red-100 text-red-800' :
                log.operation === 'create' ? 'bg-green-100 text-green-800' :
                log.operation === 'update' ? 'bg-[#c8f0d4] text-[#0a120c]' :
                'bg-gray-100 text-gray-800'
              }`}>
                {operations[log.operation] ?? log.operation}
              </span>
            </td>
            <td className="px-3 py-2 text-xs text-gray-500">{targets[log.target_type] ?? log.target_type}</td>
            <td className="px-3 py-2 text-xs text-gray-500 max-w-[200px] truncate" title={log.target_name}>
              {log.target_name || '-'}
            </td>
            <td className="px-3 py-2 text-xs text-gray-400">{log.ip_address || '-'}</td>
          </tr>
        )} />
      {(logsLoading || loadError) && <p role={loadError ? 'alert' : 'status'} className="p-8 text-center text-gray-500">
        {loadError ? '加载操作日志失败' : '加载中...'}
      </p>}
      {!logsLoading && !loadError && logsTotalPages > 1 && (
        <div className="p-3 border-t flex justify-center gap-2 flex-shrink-0">
          <button className="px-3 py-1 border rounded text-sm disabled:opacity-50" disabled={logsPage <= 1}
            onClick={() => setRequest({ query, page: logsPage - 1 })}>上一页</button>
          <span className="px-3 py-1 text-sm">{logsPage} / {logsTotalPages}</span>
          <button className="px-3 py-1 border rounded text-sm disabled:opacity-50" disabled={logsPage >= logsTotalPages}
            onClick={() => setRequest({ query, page: logsPage + 1 })}>下一页</button>
        </div>
      )}
    </div>
  )
}

export default LogsTab
