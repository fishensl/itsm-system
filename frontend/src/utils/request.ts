import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import type { ApiResponse } from '@/types'
import { currentOperationToken, requestOperationToken } from '@/utils/operationToken'
import { loginRedirectTarget } from '@/utils/appRoute'

export interface ItsmRequestConfig extends AxiosRequestConfig {
  /** 登录/MFA 等认证流程自行展示 401，避免拦截器抢先整页跳转。 */
  skipAuthRedirect?: boolean
}

/** 读取 CSRF token：优先 cookie；保留 meta 回退以兼容旧部署缓存。 */
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

/** 提取后端统一契约中的业务错误，避免 4xx 只显示 Axios 状态码。 */
export function apiErrorMessage(error: unknown): string {
  const data = (error as AxiosError<ApiResponse>)?.response?.data
  return typeof data?.message === 'string' ? data.message.trim() : ''
}

// 请求拦截：非 GET 自动附加 Flask-WTF 所需的 X-CSRFToken
instance.interceptors.request.use((config) => {
  const method = (config.method || 'get').toUpperCase()
  if (method !== 'GET') {
    config.headers.set('X-CSRFToken', getCsrfToken())
  }
  const operationToken = currentOperationToken()
  if (operationToken) config.headers.set('X-Operation-Token', operationToken)
  return config
})

// 响应拦截：契约解包 + 401/403 统一处理
instance.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<ApiResponse>) => {
    if (error.response) {
      const { status, data } = error.response
      const requestConfig = error.config as ItsmRequestConfig | undefined
      if (status === 401 && !requestConfig?.skipAuthRedirect) {
        // 未登录：跳登录页（保留回跳地址）
        if (window.location.pathname !== '/app/login') {
          const redirect = encodeURIComponent(loginRedirectTarget(
            window.location.pathname + window.location.search,
          ))
          window.location.href = `/app/login?redirect=${redirect}`
        }
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
export async function request<T>(config: ItsmRequestConfig): Promise<T> {
  let resp
  try {
    resp = await instance.request<ApiResponse<T>>(config)
  } catch (error) {
    const axiosError = error as AxiosError<ApiResponse<T>>
    const retryConfig = config as ItsmRequestConfig & { _operationRetried?: boolean }
    if (axiosError.response?.status === 403 &&
        axiosError.response.data?.message === '需要操作动态码验证' &&
        !retryConfig._operationRetried) {
      await requestOperationToken()
      retryConfig._operationRetried = true
      resp = await instance.request<ApiResponse<T>>(retryConfig)
    } else {
      const message = apiErrorMessage(error)
      if (message) throw new Error(message)
      throw error
    }
  }
  const body = resp.data
  if (body.code !== 0) {
    throw new Error(body.message || '请求失败')
  }
  return body.data
}

export const http = instance

/** 使用操作令牌下载附件，令牌不写入地址栏。 */
export async function downloadProtectedFile(url: string, filename = ''): Promise<void> {
  try {
    const blob = await requestProtectedBlob(url)
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename || decodeURIComponent(url.split('/').pop()?.split('?')[0] || '附件')
    link.click()
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  } catch { /* request handles MFA prompts and errors */ }
}
/** 受保护附件走同源请求携带操作令牌，不把令牌写入 URL。 */
export async function requestProtectedBlob(url: string): Promise<Blob> {
  const load = () => instance.get<Blob>(url, { responseType: 'blob' })
  try {
    return (await load()).data
  } catch (error) {
    const response = (error as AxiosError<Blob>).response
    if (response?.data instanceof Blob) {
      const body = JSON.parse(await response.data.text()) as { message?: string }
      if (response.status === 403 && body.message === '需要操作动态码验证') {
        await requestOperationToken()
        return (await load()).data
      }
      window.dispatchEvent(new CustomEvent('itsm:toast', {
        detail: { message: body.message || '附件下载失败', type: 'error' },
      }))
      throw new Error(body.message || '附件下载失败')
    }
    throw error
  }
}
export default request
