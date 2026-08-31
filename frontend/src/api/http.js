import axios from 'axios'
import { ElMessage } from 'element-plus'

// 统一后端访问实例（Base = /api，经 vite 代理到 127.0.0.1:8000）
const http = axios.create({
  baseURL: '/api',
  timeout: 300000
})

// 统一错误提示：后端 FastAPI 错误 detail 可能是字符串或 {message}
http.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    const resp = err.response
    const status = resp?.status
    const detail = resp?.data?.detail
    let msg = '请求失败'
    if (typeof detail === 'string' && detail) msg = detail
    else if (detail && typeof detail.message === 'string') msg = detail.message
    else if (status) msg = `请求失败 (HTTP ${status})`
    else if (err.code === 'ECONNABORTED') msg = '请求超时，请稍后重试'
    else msg = err.message || '网络错误'
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export default http
