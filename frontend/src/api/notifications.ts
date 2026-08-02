import request from '@/utils/request'

export interface NotificationItem {
  id: number
  category: string
  title: string
  content: string
  link: string
  is_read: boolean
  created_at: string
}

export function fetchNotifications() {
  return request<{ items: NotificationItem[] }>({ url: '/api/notifications', method: 'GET' })
}

export function fetchUnreadCount() {
  return request<{ unread: number }>({ url: '/api/notifications/unread-count', method: 'GET' })
}

export function markRead(ids?: number[]) {
  return request<null>({
    url: '/api/notifications/read',
    method: 'POST',
    data: ids ? { ids } : {},
  })
}
