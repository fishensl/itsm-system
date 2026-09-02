import type { AxiosProgressEvent } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/request', () => ({ default: vi.fn() }))

import request from '@/utils/request'
import { uploadTaskReport } from '@/api/inspections'


describe('inspection material upload', () => {
  beforeEach(() => {
    vi.mocked(request).mockReset()
    vi.mocked(request).mockResolvedValue({} as never)
  })

  it('uses a dedicated long timeout and reports upload progress', async () => {
    const progress = vi.fn()
    await uploadTaskReport(7, new FormData(), progress)

    const config = vi.mocked(request).mock.calls[0][0]
    expect(config.timeout).toBe(1_800_000)
    config.onUploadProgress?.({ loaded: 50, total: 100 } as AxiosProgressEvent)
    expect(progress).toHaveBeenCalledWith(50)
  })
})
