export interface WorkCalendarDay {
  date: string
  name: string
}

export interface WorkCalendarData {
  version: string
  source: string
  covered_years: number[]
  holidays: WorkCalendarDay[]
  makeup_workdays: WorkCalendarDay[]
}

export type WorkCalendarDayKind = 'workday' | 'weekend' | 'holiday' | 'makeup-workday'

export const EMPTY_WORK_CALENDAR: WorkCalendarData = {
  version: '',
  source: '',
  covered_years: [],
  holidays: [],
  makeup_workdays: [],
}

export function localDateText(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function dayMaps(calendar: WorkCalendarData) {
  return {
    holidays: new Map(calendar.holidays.map((item) => [item.date, item.name])),
    makeupWorkdays: new Map(calendar.makeup_workdays.map((item) => [item.date, item.name])),
  }
}

export function workCalendarDay(
  value: Date,
  calendar: WorkCalendarData,
): { kind: WorkCalendarDayKind; name: string } {
  const key = localDateText(value)
  const maps = dayMaps(calendar)
  const makeupName = maps.makeupWorkdays.get(key)
  if (makeupName) return { kind: 'makeup-workday', name: makeupName }
  const holidayName = maps.holidays.get(key)
  if (holidayName) return { kind: 'holiday', name: holidayName }
  if (value.getDay() === 0 || value.getDay() === 6) {
    return { kind: 'weekend', name: '周末' }
  }
  return { kind: 'workday', name: '工作日' }
}

export function workCalendarCellClass(value: Date, calendar: WorkCalendarData) {
  return `task-calendar-${workCalendarDay(value, calendar).kind}`
}

function parseLocalDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const parsed = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  return localDateText(parsed) === value ? parsed : null
}

export function workCalendarRangeSummary(
  startText: string,
  endText: string,
  calendar: WorkCalendarData,
) {
  const start = parseLocalDate(startText)
  const end = parseLocalDate(endText)
  if (!start || !end || end < start) return ''

  const counts: Record<WorkCalendarDayKind, number> = {
    workday: 0,
    weekend: 0,
    holiday: 0,
    'makeup-workday': 0,
  }
  const uncoveredYears = new Set<number>()
  const coveredYears = new Set(calendar.covered_years)
  const current = new Date(start)
  while (current <= end) {
    counts[workCalendarDay(current, calendar).kind] += 1
    if (!coveredYears.has(current.getFullYear())) uncoveredYears.add(current.getFullYear())
    current.setDate(current.getDate() + 1)
  }

  const totalWorkdays = counts.workday + counts['makeup-workday']
  const parts = [`${totalWorkdays}个工作日`]
  if (counts['makeup-workday']) parts.push(`含${counts['makeup-workday']}个调休上班日`)
  if (counts.weekend) parts.push(`${counts.weekend}个周末`)
  if (counts.holiday) parts.push(`${counts.holiday}个法定节假日`)
  if (uncoveredYears.size) {
    parts.push(`${[...uncoveredYears].sort().join('、')}年尚无法定调休数据`)
  }
  return parts.join(' · ')
}
