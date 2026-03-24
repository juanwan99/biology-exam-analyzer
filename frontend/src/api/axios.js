/**
 * Axios 配置
 * 支持开发和生产环境的API地址配置
 */
import axios from 'axios'

// 获取API基础地址
// 生产环境使用完整URL，开发环境使用相对路径（通过Vite代理）
const getBaseURL = () => {
  const apiBase = import.meta.env.VITE_API_BASE_URL

  // 如果配置了完整的API地址（包含http），则使用它
  if (apiBase && apiBase.startsWith('http')) {
    return apiBase
  }

  // 否则使用相对路径（开发环境通过Vite代理）
  return ''
}

// 创建axios实例
const apiClient = axios.create({
  baseURL: getBaseURL(),
  timeout: 60000, // 60秒超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  config => {
    // 可以在这里添加token等认证信息
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  response => {
    return response
  },
  error => {
    // 统一错误处理
    if (import.meta.env.DEV) {
      if (error.response) {
        // 服务器返回错误状态码
        console.error('API错误:', error.response.status, error.response.data)
      } else if (error.request) {
        // 请求发送了但没有收到响应
        console.error('网络错误: 无法连接到服务器')
      } else {
        // 其他错误
        console.error('请求错误:', error.message)
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
