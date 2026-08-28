export function downloadImportTemplate(module: string) {
  const link = document.createElement('a')
  link.href = `/exports/download-template/${encodeURIComponent(module)}`
  link.target = '_blank'
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}
