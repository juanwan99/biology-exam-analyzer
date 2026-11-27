import { useState, useEffect } from "react"
import axios from "axios"
import ListTable from "../../components/ListTable"

const columns = [
  { key: "name", header: "Provider", type: "text", accessor: row => row.name },
  ...[
    ["call_count", "调用次数"], ["input_tokens", "输入 Token"],
    ["output_tokens", "输出 Token"], ["unknown_count", "未知"],
  ].map(([key, header]) => ({ key, header, type: "number", accessor: row => row[key] || 0, firstDir: "desc" })),
]

function TokenStatsPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    axios.get("/api/admin/token-stats")
      .then(res => setStats(res.data))
      .catch(err => console.error("Failed to load token stats:", err))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{padding: "20px"}}>加载中...</div>
  if (!stats) return <div style={{padding: "20px"}}>无法加载统计数据</div>

  const providers = stats.providers || []

  return (
    <div style={{padding: "20px", maxWidth: "800px", margin: "0 auto"}}>
      <h2 style={{color: "#1e40af", marginBottom: "20px"}}>Token 用量统计</h2>
      <ListTable columns={columns} rows={providers} rowKey="name" emptyText="暂无 Token 用量" />
      <p style={{color: "#64748b", fontSize: "12px", marginTop: "10px"}}>
        统计自本次服务启动，重启后清零
      </p>
    </div>
  )
}

export default TokenStatsPage
