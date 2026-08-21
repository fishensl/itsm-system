import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import DataTable from '@/components/DataTable.vue'

describe('DataTable responsive cell slots', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  })

  it('renders the same editable cell slots in mobile cards', async () => {
    const wrapper = mount(DataTable, {
      props: {
        columns: [
          { key: 'name', label: '名称', asTitle: true },
          { key: 'enabled', label: '启用' },
          { key: 'actions', label: '操作', type: 'action', actions: [
            { label: '锁定', disabled: () => true, onClick: vi.fn() },
          ] },
        ],
        fetchData: async () => ({
          items: [{ id: 1, name: '检查配置', enabled: true }],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      },
      slots: {
        'cell-name': ({ row }: { row: Record<string, unknown> }) =>
          h('input', { 'data-testid': 'name-editor', value: row.name }),
        'cell-enabled': ({ row }: { row: Record<string, unknown> }) =>
          h('button', { 'data-testid': 'enabled-editor' }, String(row.enabled)),
      },
      global: {
        stubs: {
          'el-table-column': { template: '<div />' },
          'el-tag': { template: '<span><slot /></span>' },
          'router-link': { template: '<a><slot /></a>' },
          'el-icon': { template: '<i><slot /></i>' },
          'el-button': { template: '<button><slot /></button>' },
          'el-empty': { template: '<div />' },
          'el-table': { template: '<div><slot /></div>' },
          'el-pagination': { template: '<div />' },
          'el-checkbox': { template: '<label><slot /></label>' },
          'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
        },
        directives: {
          loading: () => undefined,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('[data-testid="name-editor"]').attributes('value')).toBe('检查配置')
    expect(wrapper.find('[data-testid="enabled-editor"]').text()).toBe('true')
    expect(wrapper.find('.card-actions button').text()).toBe('锁定')
    expect(wrapper.find('.card-actions button').attributes('disabled')).toBeDefined()
  })

  it('applies a quick column preset in preset order and persists it', async () => {
    const wrapper = mount(DataTable, {
      props: {
        columns: [
          { key: 'name', label: '名称' },
          { key: 'rack_location', label: '机房位置' },
          { key: 'power_supply', label: '电源配置' },
          { key: 'actions', label: '操作', type: 'action', actions: [] },
        ],
        fetchData: async () => ({ items: [], total: 0, page: 1, page_size: 20 }),
        immediate: false,
        columnSettings: {
          storageKey: 'device-table-columns-test',
          presets: [{
            key: 'asset', label: '设备资产表',
            columns: ['rack_location', 'power_supply', 'name', 'missing-sensitive-field'],
          }],
        },
      },
      global: {
        stubs: {
          'el-table-column': { template: '<div />' },
          'el-tag': { template: '<span><slot /></span>' },
          'router-link': { template: '<a><slot /></a>' },
          'el-icon': { template: '<i><slot /></i>' },
          'el-button': { template: '<button><slot /></button>' },
          'el-empty': { template: '<div />' },
          'el-table': { template: '<div><slot /></div>' },
          'el-pagination': { template: '<div />' },
          'el-checkbox': { template: '<label><slot /></label>' },
          'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
        },
        directives: { loading: () => undefined },
      },
    })

    await wrapper.find('.column-preset-row button').trigger('click')
    expect(JSON.parse(localStorage.getItem('device-table-columns-test') || '{}')).toMatchObject({
      v: 2,
      visible: ['rack_location', 'power_supply', 'name'],
      all: ['name', 'rack_location', 'power_supply'],
    })
  })
})
