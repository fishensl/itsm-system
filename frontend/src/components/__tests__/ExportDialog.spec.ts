import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ExportDialog from '../ExportDialog.vue'

function mountDialog() {
  return mount(ExportDialog, {
    props: { modelValue: true, module: 'device', title: '导出设备' },
    global: {
      plugins: [ElementPlus],
      stubs: {
        teleport: true,
        ElSelect: true, ElOption: true, ElDatePicker: true, ElAlert: true, ElInput: true,
      },
    },
  })
}

function checkedLabels(w: ReturnType<typeof mountDialog>) {
  return w.findAll('label.el-checkbox.is-checked').map((c) => c.text().trim())
}

async function clickPreset(w: ReturnType<typeof mountDialog>, idx: number) {
  const radios = w.findAll('.el-radio-button')
  await radios[idx].find('input').setValue(true)
  await w.vm.$nextTick()
}

describe('ExportDialog 设备预设自动勾选', () => {
  beforeEach(() => localStorage.clear())

  it('首次打开默认勾选资产表 14 列（无密码列）', async () => {
    const w = mountDialog()
    await w.vm.$nextTick()
    const labels = checkedLabels(w)
    expect(labels).toHaveLength(14)
    expect(labels).toContain('客户')
    expect(labels).toContain('机柜号')
    expect(labels).not.toContain('登录密码')
  })

  it('点击「设备密码表」自动勾选 18 列且含登录密码', async () => {
    const w = mountDialog()
    await w.vm.$nextTick()
    await clickPreset(w, 1)
    const labels = checkedLabels(w)
    expect(labels).toHaveLength(18)
    expect(labels).toContain('登录密码')
    expect(labels).toContain('上次修改密码账号')
  })

  it('点击「安全版本控制表」自动勾选 17 列', async () => {
    const w = mountDialog()
    await w.vm.$nextTick()
    await clickPreset(w, 2)
    const labels = checkedLabels(w)
    expect(labels).toHaveLength(17)
    expect(labels).toContain('系统版本')
    expect(labels).toContain('授权截止')
    expect(labels).not.toContain('登录密码')
  })

  it('再次打开恢复上次选择的预设与列', async () => {
    const w = mountDialog()
    await w.vm.$nextTick()
    await clickPreset(w, 1)
    await w.setProps({ modelValue: false })
    await w.setProps({ modelValue: true })
    await w.vm.$nextTick()
    const labels = checkedLabels(w)
    expect(labels).toHaveLength(18)
    expect(labels).toContain('登录密码')
  })
})
