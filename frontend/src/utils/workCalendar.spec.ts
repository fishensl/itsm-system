import { describe, expect, it } from 'vitest'

import {
  EMPTY_WORK_CALENDAR,
  workCalendarCellClass,
  workCalendarDay,
  workCalendarRangeSummary,
  type WorkCalendarData,
} from './workCalendar'

const calendar: WorkCalendarData = {
  version: 'cn-gov-2026-v1',
  source: 'test',
  covered_years: [2026],
  holidays: [{ date: '2026-06-19', name: '端午节' }],
  makeup_workdays: [{ date: '2026-02-14', name: '春节调休上班' }],
}

describe('work calendar', () => {
  it('distinguishes workdays, weekends, holidays and makeup workdays', () => {
    expect(workCalendarDay(new Date(2026, 5, 18), calendar).kind).toBe('workday')
    expect(workCalendarDay(new Date(2026, 5, 20), calendar).kind).toBe('weekend')
    expect(workCalendarDay(new Date(2026, 5, 19), calendar)).toEqual({
      kind: 'holiday', name: '端午节',
    })
    expect(workCalendarDay(new Date(2026, 1, 14), calendar)).toEqual({
      kind: 'makeup-workday', name: '春节调休上班',
    })
    expect(workCalendarCellClass(new Date(2026, 5, 19), calendar)).toBe(
      'task-calendar-holiday',
    )
  })

  it('summarizes a task deadline using the same calendar', () => {
    expect(workCalendarRangeSummary('2026-06-18', '2026-06-21', calendar)).toBe(
      '1个工作日 · 2个周末 · 1个法定节假日',
    )
  })

  it('labels uncovered years instead of inventing holiday overrides', () => {
    expect(workCalendarRangeSummary('2027-01-04', '2027-01-05', EMPTY_WORK_CALENDAR)).toContain(
      '2027年尚无法定调休数据',
    )
  })
})
