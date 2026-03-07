import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { message } from 'ant-design-vue'

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('token')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
request.interceptors.response.use(
  (response: AxiosResponse) => {
    return response.data
  },
  (error) => {
    if (error.response) {
      const { status, data } = error.response
      const requestUrl = error.config?.url || ''
      const detail = typeof data?.detail === 'string' ? data.detail : (Array.isArray(data?.detail) ? data.detail.map((d: any) => d.msg || d).join('; ') : '')
      switch (status) {
        case 401:
          if (requestUrl.includes('/auth/login')) {
            message.error(detail || '用户名或密码错误')
          } else if (window.location.pathname !== '/login') {
            message.error('登录已过期，请重新登录')
            localStorage.removeItem('token')
            window.location.href = '/login'
          }
          break
        case 403:
          if (detail && detail.includes('待审批')) {
            message.warning(detail)
          } else {
            message.error(detail || '没有权限访问')
          }
          break
        case 404:
          message.error(detail || '请求的资源不存在')
          break
        case 422:
          message.error(detail || '请求参数错误')
          break
        case 500:
          message.error(detail || '服务器错误')
          break
        default:
          message.error(detail || '请求失败')
      }
    } else {
      message.error('网络连接失败')
    }
    return Promise.reject(error)
  }
)

export default request
