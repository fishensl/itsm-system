import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('adaptive preview presentation', () => {
  it('supports viewport sizing, manual resize and fullscreen', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/AdaptivePreviewDialog.vue'), 'utf8')

    expect(source).toContain('resize: both')
    expect(source).toContain('fullscreen = !fullscreen')
    expect(source).toContain('calc(100vw - 32px)')
    expect(source).toContain('calc(94vh - 24px)')
  })

  it('lets file contents fill the resized preview window', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/FilePreview.vue'), 'utf8')

    expect(source).toContain('height: 100%')
    expect(source).not.toContain('max-height: 62vh')
  })

  it('keeps local serial available in the device form fallback choices', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/devices/index.vue'), 'utf8')

    expect(source).toContain("['SSH', 'Telnet', 'Web', 'SNMP', '本地串口']")
  })
})
