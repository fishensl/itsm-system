import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import GroupTree from '../GroupTree.vue'


describe('GroupTree 客户层级折叠', () => {
  it('renderAllNodes 模式默认折叠下级，点击上级箭头后展开', async () => {
    const wrapper = mount(GroupTree, {
      props: {
        nodes: [{
          id: 1,
          name: '水科院',
          children: [{ id: 2, name: '水科院共青城', children: [] }],
        }],
        leafDepth: 1,
        renderAllNodes: true,
        defaultExpanded: 0,
      },
      slots: {
        leaf: ({ node, hasChildren, expanded, toggle }) => h(
          'button',
          {
            class: 'customer-node',
            'data-id': String(node.id),
            'data-has-children': String(Boolean(hasChildren)),
            'data-expanded': String(Boolean(expanded)),
            onClick: toggle,
          },
          node.name,
        ),
      },
      global: {
        stubs: { ElIcon: true, ElTag: true },
      },
    })

    const children = wrapper.find('.all-node-children')
    expect(children.attributes('style')).toContain('display: none')
    expect(wrapper.find('[data-id="1"]').attributes('data-expanded')).toBe('false')

    await wrapper.find('[data-id="1"]').trigger('click')

    expect(children.attributes('style') || '').not.toContain('display: none')
    expect(wrapper.find('[data-id="1"]').attributes('data-expanded')).toBe('true')
  })
})
