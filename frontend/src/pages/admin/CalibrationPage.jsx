import { useState, useEffect } from "react"
import axios from "axios"

function CalibrationPage() {
  const [status, setStatus] = useState(null)
  const [running, setRunning] = useState(false)

  const loadStatus = () => {
    axios.get("/api/admin/calibration")
      .then(res => setStatus(res.data))
      .catch(err => console.error(err))
  }

  useEffect(() => { loadStatus() }, [])

  const runCalibration = () => {
    setRunning(true)
    axios.post("/api/admin/calibration/run")
      .then(res => { setStatus(res.data); alert("校准完成") })
      .catch(err => alert("校准失败: " + err.message))
      .finally(() => setRunning(false))
  }

  return (
    <div style={{padding: "20px", maxWidth: "800px", margin: "0 auto"}}>
      <h2 style={{color: "#1e40af", marginBottom: "20px"}}>难度校准</h2>
      {status && (
        <div style={{background: "#f0f9ff", padding: "16px", borderRadius: "8px", marginBottom: "20px"}}>
          <p><strong>状态：</strong>{status.status === "calibrated" ? "已校准" : status.status === "insufficient" ? "数据不足" : "未校准"}</p>
          <p><strong>样本量：</strong>{status.sample_count || 0} 条</p>
          {status.overall_rmse && <p><strong>RMSE：</strong>{status.overall_rmse}</p>}
        </div>
      )}
      <button
        onClick={runCalibration}
        disabled={running}
        style={{background: "#3b82f6", color: "white", padding: "10px 20px", border: "none", borderRadius: "6px", cursor: "pointer"}}
      >
        {running ? "校准中..." : "运行校准"}
      </button>
    </div>
  )
}

export default CalibrationPage
