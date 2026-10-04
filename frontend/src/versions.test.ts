import { describe, expect, it } from 'vitest'
import { compareVersions, isNewerVersion, nextVersion } from './versions'

describe('versions', () => {
  it('orders numeric versions, treating missing parts as 0', () => {
    expect(compareVersions('3.0', '2.9')).toBeGreaterThan(0)
    expect(compareVersions('3', '3.0')).toBe(0)
    expect(compareVersions('v1.10', '1.9')).toBeGreaterThan(0)
    expect(compareVersions('1.0-beta', '1.0-rc')).toBeNull()
  })

  it('only accepts a strictly newer version', () => {
    expect(isNewerVersion('4.0', '3.0')).toBe(true)
    expect(isNewerVersion('3.0', '3.0')).toBe(false)
    expect(isNewerVersion('2.0', '3.0')).toBe(false)
    expect(isNewerVersion('', '3.0')).toBe(false)
    expect(isNewerVersion('anything', null)).toBe(true)
  })

  it('suggests the next major version', () => {
    expect(nextVersion('3.0')).toBe('4.0')
    expect(nextVersion('3')).toBe('4')
    expect(nextVersion('1.2.3')).toBe('2.0.0')
  })
})
