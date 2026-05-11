import { describe, it, expect } from 'vitest'
import {
  formatNumber, formatTokens, formatBytes, formatDuration,
  formatPercent, formatUptime, pct,
} from '../src/utils/format'

describe('format utilities', () => {
  it('formatNumber mit Tausendertrenner', () => {
    expect(formatNumber(1234567)).toBe('1.234.567')
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(null)).toBe('—')
  })

  it('formatTokens mit Suffix', () => {
    expect(formatTokens(500)).toBe('500')
    expect(formatTokens(2500)).toBe('2,5 k')
    expect(formatTokens(1_500_000)).toBe('1,5 Mio')
  })

  it('formatBytes', () => {
    expect(formatBytes(512)).toBe('512 MB')
    expect(formatBytes(2048)).toBe('2,0 GB')
  })

  it('formatDuration', () => {
    expect(formatDuration(120)).toBe('120 ms')
    expect(formatDuration(2500)).toBe('2,50 s')
  })

  it('formatPercent', () => {
    expect(formatPercent(75)).toBe('75 %')
    expect(formatPercent(33.7, 1)).toBe('33,7 %')
  })

  it('formatUptime', () => {
    expect(formatUptime(60)).toBe('1m')
    expect(formatUptime(3600)).toBe('1h 0m')
    expect(formatUptime(90061)).toBe('1d 1h 1m')
  })

  it('pct cap auf 100', () => {
    expect(pct(50, 100)).toBe(50)
    expect(pct(150, 100)).toBe(100)
    expect(pct(0, 0)).toBe(0)
  })
})
