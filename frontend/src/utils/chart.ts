/**
 * Minimale Chart-Helfer (kein chart.js — wir bauen direkt SVG).
 */

export interface SparklinePoint {
  x: number
  y: number
}

/**
 * Erzeugt einen SVG-Path-String für eine Sparkline.
 * Skaliert auf die Box (width × height), Padding 2px.
 */
export function sparklinePath(values: number[], width = 100, height = 24, pad = 2): string {
  if (!values.length) return ''
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const innerW = width - 2 * pad
  const innerH = height - 2 * pad
  const step = values.length > 1 ? innerW / (values.length - 1) : 0
  return values
    .map((v, i) => {
      const x = pad + i * step
      const y = pad + innerH - ((v - min) / range) * innerH
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')
}

/**
 * Bars für Bar-Chart, gibt Array von Rect-Specs zurück.
 */
export interface BarRect {
  x: number; y: number; width: number; height: number; value: number
}

export function barRects(values: number[], width: number, height: number, pad = 2, gap = 2): BarRect[] {
  if (!values.length) return []
  const max = Math.max(...values, 1)
  const innerW = width - 2 * pad
  const innerH = height - 2 * pad
  const barW = (innerW - gap * (values.length - 1)) / values.length
  return values.map((v, i) => {
    const h = (v / max) * innerH
    return {
      x: pad + i * (barW + gap),
      y: pad + innerH - h,
      width: barW,
      height: h,
      value: v,
    }
  })
}
