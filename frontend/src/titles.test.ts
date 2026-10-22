import { describe, expect, it } from 'vitest'
import { titleSimilarity, titlesUnrelated } from './titles'

describe('titlesUnrelated', () => {
  it('accepts the same title, with other case, accents, a version or a plural', () => {
    expect(titlesUnrelated('Doñana National Park Dataset', 'donana national park dataset')).toBe(false)
    expect(titlesUnrelated('Doñana National Park Images v2', 'Donana National Park Image')).toBe(false)
  })

  it('accepts a title that only adds or drops some words', () => {
    expect(titlesUnrelated('Doñana National Park camera trap images', 'Doñana National Park')).toBe(false)
  })

  it('flags titles that share nothing', () => {
    expect(titlesUnrelated('Iberian lynx census 2024', 'Doñana National Park Dataset')).toBe(true)
  })

  it('cannot judge when a title has no meaningful words', () => {
    expect(titlesUnrelated('', 'Doñana National Park')).toBe(false)
    expect(titlesUnrelated('Dataset', 'Doñana National Park')).toBe(false)
    expect(titleSimilarity(null, 'x')).toBeNull()
  })
})
