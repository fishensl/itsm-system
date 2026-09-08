/** 下载失败留在当前页面，避免受限下载跳到登录页。 */
export async function downloadImportTemplate(module: string) {
  try {
    const response = await fetch(`/exports/download-template/${encodeURIComponent(module)}`, {
      credentials: 'same-origin',
    })
    if (response.redirected || response.status === 401) {
      throw new Error('登录状态已失效，请刷新页面后重新登录')
    }
    const contentType = response.headers.get('content-type') || ''
    if (!response.ok) {
      const body = contentType.includes('application/json') ? await response.json() : null
      throw new Error(body?.message || (response.status === 403 ? '无权下载该模板' : '模板下载失败，请稍后重试'))
    }
    if (!contentType.includes('spreadsheetml')) {
      throw new Error('模板下载失败：服务器未返回 Excel 文件')
    }
    const disposition = response.headers.get('content-disposition') || ''
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const filename = encoded ? decodeURIComponent(encoded) :
      disposition.match(/filename="([^"]+)"/i)?.[1] || `${module}_template.xlsx`
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (error) {
    window.dispatchEvent(new CustomEvent('itsm:toast', {
      detail: { message: error instanceof Error ? error.message : '模板下载失败', type: 'error' },
    }))
  }
}
