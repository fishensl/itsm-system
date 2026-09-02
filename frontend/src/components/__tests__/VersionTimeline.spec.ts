import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import VersionTimeline from '@/components/VersionTimeline.vue'
import type { SubmissionVersion } from '@/api/inspections'

const stubs = {
  'el-empty': { template: '<div><slot /></div>' },
  'el-timeline': { template: '<div><slot /></div>' },
  'el-timeline-item': { template: '<section><slot /></section>' },
  'el-tag': { template: '<span><slot /></span>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-link': { template: '<a><slot /></a>' },
  'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
  'el-button': { template: '<button><slot /></button>' },
}

describe('VersionTimeline review summary', () => {
  it('renders review checklist as a compact state grid and hides an empty reviewer', () => {
    const version: SubmissionVersion = {
      id: 1,
      version_no: 1,
      report_file: false,
      report_name: '',
      content: {},
      submitted_by_name: '工程师',
      submitted_at: '2026-09-02 08:00',
      review_status: '已通过',
      assigned_reviewer_id: null,
      assigned_reviewer_name: '',
      reviewed_by_name: '',
      reviewed_at: '2026-09-02 09:19',
      review_comment: '',
      revision_requirements: '',
      checklist: {
        会议测试: '合格',
        拓扑图: '需修改',
        机房环境: '不适用',
      },
      assets: [],
    }

    const wrapper = mount(VersionTimeline, {
      props: { versions: [version], entityType: 'inspection' },
      global: { stubs },
    })

    expect(wrapper.text()).not.toContain('审核人：-')
    expect(wrapper.text()).toContain('审核时间：2026-09-02 09:19')
    expect(wrapper.find('.vt-check-summary').text()).toBe('3 项 · 合格 1 · 需修改 1 · 不适用 1')
    expect(wrapper.findAll('.vt-check-row')).toHaveLength(3)
    expect(wrapper.find('.vt-check-row.is-qualified').text()).toContain('会议测试合格')
    expect(wrapper.find('.vt-check-row.needs-change').text()).toContain('拓扑图需修改')
    expect(wrapper.find('.vt-check-row.not-applicable').text()).toContain('机房环境不适用')
  })
})
