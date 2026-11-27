import { useState, useEffect } from 'react'
import axios from 'axios'
import ListTable from '../../components/ListTable'

const columns = [
  { key: 'id', header: 'ID', type: 'number', accessor: user => user.id },
  { key: 'username', header: '用户名', type: 'text', accessor: user => user.username },
  { key: 'display_name', header: '显示名', type: 'text', accessor: user => user.display_name },
  { key: 'role', header: '角色', type: 'enum', accessor: user => user.role === 'admin' ? 'admin' : 'editor',
    options: [{ value: 'admin', label: '管理员' }, { value: 'editor', label: '编辑' }] },
  { key: 'is_active', header: '状态', type: 'enum', accessor: user => user.is_active ? '1' : '0',
    options: [{ value: '1', label: '启用' }, { value: '0', label: '禁用' }] },
  { key: 'last_login', header: '最后登录', type: 'date', accessor: user => user.last_login },
  { key: 'actions', header: '操作', sortable: false, filterable: false },
]

function UsersTab({ token, getHeaders, user }) {
  const [users, setUsers] = useState([])

  const loadUsers = async () => {
    try {
      const res = await axios.get('/api/auth/users', { headers: getHeaders() })
      setUsers(res.data.users || [])
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载用户列表失败:', err)
    }
  }

  const resetUserPassword = async (userId) => {
    if (!confirm('确定要重置该用户密码吗？将生成一个随机密码。')) return
    try {
      const res = await axios.post(`/api/auth/users/${userId}/reset-password`, {}, { headers: getHeaders() })
      alert(res.data.message)
    } catch (err) {
      alert('重置失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const toggleUserStatus = async (userId, isActive) => {
    try {
      await axios.put(`/api/auth/users/${userId}`, { is_active: isActive ? 0 : 1 }, { headers: getHeaders() })
      loadUsers()
    } catch (err) {
      alert('操作失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  // 初始加载
  useEffect(() => {
    if (user?.role === 'admin') {
      loadUsers()
    }
  }, [])

  if (user?.role !== 'admin') return null

  return (
    <div className="bg-white shadow rounded-lg flex flex-col" style={{maxHeight: 'calc(100vh - 200px)'}}>
      <div className="p-4 border-b flex-shrink-0">
        <h3 className="font-medium">用户管理</h3>
      </div>
      <ListTable columns={columns} rows={users} rowKey="id" emptyText="暂无用户"
        renderRow={u => (
          <tr className="hover:bg-gray-50">
            <td className="px-3 py-2 text-right text-xs text-gray-500">{u.id}</td>
            <td className="px-3 py-2 text-xs font-medium text-gray-900">{u.username}</td>
            <td className="px-3 py-2 text-xs text-gray-500">{u.display_name}</td>
            <td className="px-3 py-2 text-xs"><span className={`px-1.5 py-0.5 rounded ${
              u.role === 'admin' ? 'bg-[#ede9fe] text-[#0f1c13]' : 'bg-gray-100 text-gray-800'
            }`}>{u.role === 'admin' ? '管理员' : '编辑'}</span></td>
            <td className="px-3 py-2 text-xs"><span className={`px-1.5 py-0.5 rounded ${
              u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
            }`}>{u.is_active ? '启用' : '禁用'}</span></td>
            <td className="px-3 py-2 text-xs text-gray-500 whitespace-nowrap">{u.last_login?.replace('T', ' ').slice(0, 19) || '-'}</td>
            <td className="px-3 py-2 text-xs space-x-1">
              <button onClick={() => resetUserPassword(u.id)} className="text-[#1a2e1f] hover:underline">重置密码</button>
              <button onClick={() => toggleUserStatus(u.id, u.is_active)}
                className={u.is_active ? 'text-red-600 hover:underline' : 'text-green-600 hover:underline'}
              >{u.is_active ? '禁用' : '启用'}</button>
            </td>
          </tr>
        )} />
    </div>
  )
}

export default UsersTab
