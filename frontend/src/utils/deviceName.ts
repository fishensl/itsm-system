/** 手动机柜条目没有设备启用状态，不将缺失状态误判为停用。 */
export function inactiveDeviceColor(isInUse: unknown) {
  return isInUse === false ? 'var(--el-text-color-placeholder)' : undefined
}
