import { useState, useEffect } from "react"
import axios from "axios"

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
      <table style={{width: "100%", borderCollapse: "collapse"}}>
        <thead>
          <tr style={{background: "#f1f5f9"}}>
            <th style={{padding: "10px", textAlign: "left", border: "1px solid #e2e8f0"}}>Provider</th>
            <th style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>调用次数</th>
            <th style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>输入 Token</th>
            <th style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>输出 Token</th>
            <th style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>未知</th>
          </tr>
        </thead>
        <tbody>
          {providers.map(p => (
            <tr key={p.name}>
              <td style={{padding: "10px", border: "1px solid #e2e8f0", fontWeight: "bold"}}>{p.name}</td>
              <td style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>{p.call_count}</td>
              <td style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>{(p.input_tokens || 0).toLocaleString()}</td>
              <td style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>{(p.output_tokens || 0).toLocaleString()}</td>
              <td style={{padding: "10px", textAlign: "right", border: "1px solid #e2e8f0"}}>{p.unknown_count || 0}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{color: "#64748b", fontSize: "12px", marginTop: "10px"}}>
        统计自本次服务启动，重启后清零
      </p>
    </div>
  )
}

export default TokenStatsPage
