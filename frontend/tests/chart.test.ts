import { describe, it, expect } from 'vitest'
import { sparklinePath, barRects } from '../src/utils/chart'

describe('chart utilities', () => {
  it('sparklinePath generiert Move/Line-Befehle', () => {
    const path = sparklinePath([1, 2, 3, 4, 5], 100, 30)
    expect(path).toMatch(/^M/)
    expect(path).toContain('L')
  })

  it('sparklinePath mit leerem Array → leerer String', () => {
    expect(sparklinePath([], 100, 30)).toBe('')
  })

  it('barRects liefert pro Wert ein Rect', () => {
    const rects = barRects([1, 2, 3], 100, 30)
    expect(rects).toHaveLength(3)
    expect(rects[0]).toHaveProperty('width')
    expect(rects[0]).toHaveProperty('height')
  })

  it('barRects skaliert auf max', () => {
    const rects = barRects([10, 20, 40], 100, 100)
    // Höchster Wert = volle Höhe (minus padding)
    expect(rects[2].height).toBeGreaterThan(rects[0].height)
  })
})
