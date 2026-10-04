import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

describe('api.checkHealth', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns true when the backend responds ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
    await expect(api.checkHealth()).resolves.toBe(true)
  })

  it('returns false when the backend responds with an error status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }))
    await expect(api.checkHealth()).resolves.toBe(false)
  })

  it('returns false when the request throws (backend unreachable)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))
    await expect(api.checkHealth()).resolves.toBe(false)
  })
})
