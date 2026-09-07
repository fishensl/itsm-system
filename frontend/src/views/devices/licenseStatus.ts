export function licenseStatus(days: unknown) {
  if (typeof days !== 'number' || !Number.isFinite(days)) return null
  if (days < 0) return { text: `已过期 ${-days} 天`, color: 'var(--el-color-danger)' }
  if (days === 0) return { text: '今日到期', color: 'var(--el-color-warning)' }
  return { text: `剩 ${days} 天`, color: days <= 30 ? 'var(--el-color-warning)' : 'var(--itsm-text-muted)' }
}
