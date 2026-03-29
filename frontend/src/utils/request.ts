import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'
import { message } from 'ant-design-vue'

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

interface AuthResponse {
  access_token: string
  user: {
    id: string
    username: string
    email: string
    full_name: string | null
    role: string
    is_active: boolean
  }
}

const request: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

let refreshPromise: Promise<AuthResponse> | null = null
let loginRedirectPending = false

function persistAuth(data: AuthResponse) {
  localStorage.setItem('token', data.access_token)
  localStorage.setItem('userInfo', JSON.stringify({
    id: data.user.id,
    username: data.user.username,
    email: data.user.email,
    full_name: data.user.full_name,
    role: data.user.role,
    is_active: data.user.is_active,
  }))
}

function clearAuth() {
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
}

function redirectToLogin() {
  if (window.location.pathname === '/login' || loginRedirectPending) return
  loginRedirectPending = true
  message.error('登录已过期，请重新登录')
  clearAuth()
  window.location.href = '/login'
}

async function refreshAccessToken(): Promise<AuthResponse> {
  if (!refreshPromise) {
    refreshPromise = axios.post<AuthResponse>(
      `${request.defaults.baseURL}/auth/refresh`,
      {},
      {
        withCredentials: true,
        headers: {
          'Content-Type': 'application/json',
        },
      }
    ).then((response) => {
      persistAuth(response.data)
      return response.data
    }).finally(() => {
      refreshPromise = null
    })
  }

  return refreshPromise
}

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
  async (error) => {
    if (error.response) {
      const { status, data } = error.response
      const requestUrl = error.config?.url || ''
      const originalRequest = error.config as RetriableRequestConfig | undefined
      const detail = typeof data?.detail === 'string' ? data.detail : (Array.isArray(data?.detail) ? data.detail.map((d: any) => d.msg || d).join('; ') : '')
      switch (status) {
        case 401:
          if (requestUrl.includes('/auth/login')) {
            message.error(detail || '用户名或密码错误')
            break
          }

          if (requestUrl.includes('/auth/refresh')) {
            redirectToLogin()
            break
          }

          if (originalRequest && !originalRequest._retry) {
            originalRequest._retry = true
            try {
              const refreshed = await refreshAccessToken()
              if (originalRequest.headers) {
                originalRequest.headers.Authorization = `Bearer ${refreshed.access_token}`
              }
              return request(originalRequest)
            } catch (_refreshError) {
              redirectToLogin()
            }
          } else {
            redirectToLogin()
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
