/**
 * 导出工具：base64 下载与导出结果处理（消除 6 处页面重复实现）
 */
export function saveBase64Blob(b64: string, filename: string) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * 通用导出提交处理：成功后下载 + toast + 关闭弹窗。
 * @param res 导出接口返回（base64 内容 + 文件名）
 * @param opts close 关闭弹窗回调；onSuccess 额外回调
 */
export function handleExportResult(
  res: { content?: string; filename?: string; download_url?: string },
  opts: { close?: () => void; onSuccess?: () => void } = {},
) {
  if (res.download_url) {
    // 一次性链接下载（bundle zip）
    window.open(res.download_url, '_blank')
  } else if (res.content && res.filename) {
    saveBase64Blob(res.content, res.filename)
  }
  opts.close?.()
  opts.onSuccess?.()
}
