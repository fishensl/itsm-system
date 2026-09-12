import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MobileFilterPanel from '../MobileFilterPanel.vue'

describe('手机筛选面板', () => {
  it('折叠再展开保留输入，并提供展开状态给辅助技术', async () => {
    const wrapper = mount(MobileFilterPanel, { slots: { default: '<input aria-label="客户搜索" />' } })
    const button = wrapper.get('button')
    expect(button.attributes('aria-expanded')).toBe('false')
    await button.trigger('click')
    await wrapper.get('input').setValue('景德镇')
    await button.trigger('click')
    await button.trigger('click')
    expect(button.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('input').element.value).toBe('景德镇')
  })
  it('折叠时仍提示生效条件，清空后同步消失', async () => {
    const wrapper = mount(MobileFilterPanel, { props: { filters: { search: '客户', status: '', mine: false, dates: [] } } })
    expect(wrapper.get('button').text()).toContain('已选 1 项')
    await wrapper.setProps({ filters: { search: '' } })
    expect(wrapper.get('button').text()).not.toContain('已选')
  })
})
