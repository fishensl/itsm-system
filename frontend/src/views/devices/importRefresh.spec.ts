import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { defineComponent, h, onMounted, ref } from 'vue'
import DevicePage from './index.vue'

const mocks = vi.hoisted(() => ({
  importDevices: vi.fn(), fetchDevices: vi.fn(), fetchTree: vi.fn(), toast: vi.fn(),
  fetchDeviceDicts: vi.fn(),
}))

vi.mock('vue-router', async (importOriginal) => ({
  ...await importOriginal<object>(), useRoute: () => ({ query: {} }),
}))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ hasPerm: () => true }) }))
vi.mock('@/stores/ui', () => ({ useUiStore: () => ({ toast: mocks.toast }) }))
vi.mock('@/api/devices', async (importOriginal) => ({
  ...await importOriginal<object>(),
  importDevicesEncrypted: mocks.importDevices,
  fetchDevices: mocks.fetchDevices,
  fetchDeviceTree: mocks.fetchTree,
}))
vi.mock('@/api/dicts', () => ({
  fetchDeviceDicts: mocks.fetchDeviceDicts,
}))
vi.mock('@/api/meta', async (importOriginal) => ({
  ...await importOriginal<object>(), fetchEntityMetas: async () => ({}),
}))

const dateFields = ['build_date', 'license_start', 'license_expiry', 'cert_expiry_date']
const importedDates = ['2021-01-01', '2025-03-27', '2026-03-26', '2026-03-26']

// 模拟 DataTable 的数据获取和公开 refresh 接口，实际执行页面的 doImport/reload。
const TableStub = defineComponent({
  props: ['fetchData', 'query'],
  setup(props, { expose }) {
    const items = ref<Record<string, string>[]>([])
    async function refresh() {
      items.value = (await props.fetchData(props.query)).items
    }
    onMounted(refresh)
    expose({ refresh })
    return () => h('div', { 'data-testid': 'device-table' },
      items.value.map((row) => h('div', dateFields.map((key) =>
        h('span', { 'data-field': key }, row[key] || '-')))))
  },
})

function mountPage() {
  const wrapper = shallowMount(DevicePage, {
    global: {
      stubs: { DataTable: TableStub, ElDialog: true, ElTable: true, ElTableColumn: true },
      directives: { loading: () => undefined },
      config: { warnHandler: () => undefined },
    },
  })
  // script setup 的状态用于模拟文件选择与模式；业务函数仍来自实际页面。
  const state = (wrapper.vm as unknown as {
    $: { setupState: {
      mode: string; activeDeviceView: string; importFile: File | null;
      importVisible: boolean; importPreview: unknown; importMode: string;
      doImport: () => Promise<void>;
    } };
  }).$.setupState
  return { wrapper, state }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.fetchDeviceDicts.mockResolvedValue({ brands: [], device_types: [], customers: [] })
  mocks.fetchTree.mockResolvedValue({ tree: [], total: 0 })
  mocks.fetchDevices.mockResolvedValue({ items: [{}], total: 1 })
  mocks.importDevices.mockImplementation(async (_file, fields) => {
    if (fields.dry_run === '0') {
      mocks.fetchDevices.mockResolvedValue({
        items: [Object.fromEntries(dateFields.map((key, i) => [key, importedDates[i]]))],
        total: 1,
      })
    }
    return {
      create: fields.mode === 'create' ? 1 : 0,
      update: fields.mode === 'create' ? 0 : 1, unchanged: 0, skipped: 0, failed: 0,
      errors: [], unknown_network_types: {}, batch_id: 'date-refresh-regression',
      dry_run: fields.dry_run === '1', committed: fields.dry_run === '0',
    }
  })
})

afterEach(() => vi.restoreAllMocks())

describe('设备导入后刷新当前视图', () => {
  it.each([
    { failed: 1, dry_run: false, committed: false, errors: ['第2行：U 位冲突'] },
    { failed: 0, dry_run: true, committed: false, errors: [] },
    { failed: 0, dry_run: false, committed: false, errors: [] },
    { failed: 0, dry_run: false, errors: [] },
  ])('确认执行但未获提交确认不能提示成功或关闭窗口：%j', async (response) => {
    const { wrapper, state } = mountPage()
    try {
      await flushPromises()
      state.importFile = new File(['fixture'], 'devices.xlsx')
      state.importVisible = true
      await state.doImport()
      mocks.toast.mockClear()
      mocks.fetchTree.mockClear()
      mocks.importDevices.mockResolvedValueOnce({
        create: 0, update: 1, unchanged: 0, skipped: 0,
        unknown_network_types: {}, batch_id: 'date-refresh-regression', ...response,
      })
      await state.doImport()
      await flushPromises()
      expect(mocks.toast.mock.calls.some((call) => call[1] === 'success')).toBe(false)
      expect(state.importVisible).toBe(true)
      expect(state.importPreview).not.toBeNull()
      expect(mocks.fetchTree).not.toHaveBeenCalled()
      expect(mocks.fetchDevices).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it.each(['asset', 'password', 'version'].flatMap((view) =>
    ['create', 'update'].map((mode) => [view, mode])))('%s 表格 %s 确认执行后读回日期，预检不刷新', async (view, mode) => {
    const { wrapper, state } = mountPage()
    try {
      await flushPromises()
      state.mode = 'table'
      state.activeDeviceView = view
      state.importMode = mode
      state.importFile = new File(['fixture'], 'devices.xlsx')
      state.importVisible = true
      await flushPromises()
      expect(wrapper.find('[data-field="build_date"]').text()).toBe('-')
      mocks.fetchDevices.mockClear()
      mocks.fetchTree.mockClear()
      mocks.fetchDeviceDicts.mockClear()

      await state.doImport() // 预检
      await flushPromises()
      expect(mocks.fetchDevices).not.toHaveBeenCalled()
      expect(state.importVisible).toBe(true)
      expect(mocks.fetchDeviceDicts).not.toHaveBeenCalled()

      await state.doImport() // 确认执行
      await flushPromises()
      expect(mocks.importDevices.mock.calls[1][1]).toMatchObject({
        dry_run: '0', batch_id: 'date-refresh-regression',
      })
      expect(mocks.fetchDevices).toHaveBeenCalledTimes(1)
      expect(mocks.fetchDeviceDicts).toHaveBeenCalledTimes(1)
      expect(mocks.fetchTree).not.toHaveBeenCalled()
      dateFields.forEach((key, i) => {
        expect(wrapper.find(`[data-field="${key}"]`).text()).toBe(importedDates[i])
      })
      expect(state.importVisible).toBe(false)
      expect(state.importPreview).toBeNull()
      expect(state.activeDeviceView).toBe(view)
    } finally {
      wrapper.unmount()
    }
  })

  it('确认时已全部无变化或跳过，不再用成功提示掩盖零写入', async () => {
    const { wrapper, state } = mountPage()
    try {
      await flushPromises()
      state.importFile = new File(['fixture'], 'devices.xlsx')
      state.importVisible = true
      await state.doImport()
      mocks.toast.mockClear()
      mocks.importDevices.mockResolvedValueOnce({
        create: 0, update: 0, unchanged: 1, skipped: 0, failed: 0,
        dry_run: false, committed: true, errors: [], unknown_network_types: {},
        batch_id: 'date-refresh-regression',
      })
      await state.doImport()
      expect(mocks.toast).toHaveBeenCalledWith(expect.stringContaining('没有需要执行的变更'), 'warning')
      expect(mocks.toast.mock.calls.some((call) => call[1] === 'success')).toBe(false)
      expect(state.importVisible).toBe(true)
    } finally {
      wrapper.unmount()
    }
  })

  it('客户树模式导入后仍刷新客户树', async () => {
    const { wrapper, state } = mountPage()
    try {
      await flushPromises()
      mocks.fetchTree.mockClear()
      state.importFile = new File(['fixture'], 'devices.xlsx')
      await state.doImport()
      await state.doImport()
      await flushPromises()
      expect(mocks.fetchTree).toHaveBeenCalledTimes(1)
      expect(mocks.fetchDevices).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })
})
