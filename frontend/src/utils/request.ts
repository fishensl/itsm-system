import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import type { ApiResponse } from '@/types'

/** 读取 CSRF token：优先 meta 标签（与 SSR base.html 机制一致），回退 cookie */
function getCsrfToken(): string {
  const meta = document.querySelector('meta[name="csrf-token"]')
  if (meta && meta.getAttribute('content')) return meta.getAttribute('content')!
  const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/)
  return m ? decodeURIComponent(m[1]) : ''
}

const instance = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 请求拦截：非 GET 自动附加 X-CSRFToken（复用 Flask-WTF 现有机制）
instance.interceptors.request.use((config) => {
  const method = (config.method || 'get').toUpperCase()
  if (method !== 'GET') {
    config.headers.set('X-CSRFToken', getCsrfToken())
  }
  return config
})

// 响应拦截：契约解包 + 401/403 统一处理
instance.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<ApiResponse>) => {
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) {
        // 未登录：跳登录页（保留回跳地址）
        const redirect = encodeURIComponent(window.location.pathname + window.location.search)
        window.location.href = `/app/login?redirect=${redirect}`
      } else if (status === 403) {
        window.dispatchEvent(new CustomEvent('itsm:toast', {
          detail: { message: data?.message || '权限不足', type: 'error' },
        }))
      } else if (status >= 500) {
        window.dispatchEvent(new CustomEvent('itsm:toast', {
          detail: { message: data?.message || '服务器错误，请稍后重试', type: 'error' },
        }))
      }
    }
    return Promise.reject(error)
  },
)

/** 统一请求封装：返回解包后的 data；业务错误抛 Error(message) */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const resp = await instance.request<ApiResponse<T>>(config)
  const body = resp.data
  if (body.code !== 0) {
    throw new Error(body.message || '请求失败')
  }
  return body.data
}

export const http = instance
export default request
