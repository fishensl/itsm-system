import { describe, it, expect, beforeEach } from 'vitest'
import {
  SIDEBAR_OPEN_KEY, loadOpenGroups, saveOpenGroups, clearOpenGroups,
} from '@/utils/sidebarState'

describe('sidebarState', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('未存储/脏数据时返回空数组', () => {
    expect(loadOpenGroups()).toEqual([])
    sessionStorage.setItem(SIDEBAR_OPEN_KEY, 'not-json{{')
    expect(loadOpenGroups()).toEqual([])
  })

  it('save/load 往返一致', () => {
    saveOpenGroups(['ops', 'dev'])
    expect(sessionStorage.getItem(SIDEBAR_OPEN_KEY)).toBe('["ops","dev"]')
    expect(loadOpenGroups()).toEqual(['ops', 'dev'])
  })

  it('clear 清空记录', () => {
    saveOpenGroups(['ops'])
    clearOpenGroups()
    expect(loadOpenGroups()).toEqual([])
  })
})
