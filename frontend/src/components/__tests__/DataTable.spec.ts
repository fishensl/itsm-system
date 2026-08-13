import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import DataTable from '@/components/DataTable.vue'

describe('DataTable responsive cell slots', () => {
  beforeEach(() => {
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
})
