import { describe, expect, it } from 'vitest'
import {
  PROVIDER_PRESETS,
  applyAuthPrefix,
  getProviderPreset,
  stripAuthPrefix,
} from '../src/data/providers'

describe('Provider-Presets', () => {
  it('enthaelt Custom als erste Option', () => {
    expect(PROVIDER_PRESETS[0].id).toBe('custom')
  })

  it('enthaelt alle Pflicht-Provider', () => {
    const ids = PROVIDER_PRESETS.map(p => p.id)
    for (const id of ['openai', 'anthropic', 'google-gemini', 'mistral', 'cohere', 'together', 'groq', 'ollama-local']) {
      expect(ids).toContain(id)
    }
  })

  it('hat valide Felder fuer jeden Preset', () => {
    for (const p of PROVIDER_PRESETS) {
      expect(p.id).toBeTruthy()
      expect(p.label).toBeTruthy()
      expect(['openai', 'ollama', 'custom', 'gpu-llm-manager', 'paddle-ocr']).toContain(p.type)
      expect(Array.isArray(p.capabilities)).toBe(true)
      if (p.id !== 'custom') {
        expect(p.base_url).toMatch(/^https?:\/\//)
      }
    }
  })

  it('markiert nicht-OpenAI-kompatible Provider als custom mit notice', () => {
    const anthropic = PROVIDER_PRESETS.find(p => p.id === 'anthropic')!
    expect(anthropic.type).toBe('custom')
    expect(anthropic.notice).toMatch(/Adapter/i)
    expect(anthropic.auth_header).toBe('x-api-key')
    // Kein Bearer-Praefix bei Anthropic
    expect(anthropic.auth_value_prefix ?? '').toBe('')

    const gemini = PROVIDER_PRESETS.find(p => p.id === 'google-gemini')!
    expect(gemini.type).toBe('custom')
    expect(gemini.notice).toMatch(/Adapter/i)
  })

  it('hat Bearer-Praefix fuer OpenAI/Mistral/Cohere/Together/Groq', () => {
    for (const id of ['openai', 'mistral', 'cohere', 'together', 'groq']) {
      const p = PROVIDER_PRESETS.find(x => x.id === id)!
      expect(p.auth_header).toBe('Authorization')
      expect(p.auth_value_prefix).toBe('Bearer ')
    }
  })

  it('Cohere hat rerank capability', () => {
    const cohere = PROVIDER_PRESETS.find(p => p.id === 'cohere')!
    expect(cohere.capabilities).toContain('rerank')
  })

  it('Ollama-lokal hat type=ollama und kein Praefix', () => {
    const ol = PROVIDER_PRESETS.find(p => p.id === 'ollama-local')!
    expect(ol.type).toBe('ollama')
    expect(ol.auth_value_prefix ?? '').toBe('')
    expect(ol.base_url).toBe('http://localhost:11434')
  })

  it('getProviderPreset liefert Custom fuer unbekannte IDs', () => {
    expect(getProviderPreset('nonexistent').id).toBe('custom')
  })
})

describe('applyAuthPrefix', () => {
  it('fuegt Praefix hinzu wenn nicht vorhanden', () => {
    expect(applyAuthPrefix('sk-abc', 'Bearer ')).toBe('Bearer sk-abc')
  })

  it('verdoppelt Praefix nicht (idempotent)', () => {
    expect(applyAuthPrefix('Bearer sk-abc', 'Bearer ')).toBe('Bearer sk-abc')
  })

  it('case-insensitiv beim Praefix-Check', () => {
    expect(applyAuthPrefix('bearer sk-abc', 'Bearer ')).toBe('bearer sk-abc')
  })

  it('liefert nur Wert wenn kein Praefix gesetzt', () => {
    expect(applyAuthPrefix('sk-abc', undefined)).toBe('sk-abc')
    expect(applyAuthPrefix('sk-abc', '')).toBe('sk-abc')
  })

  it('liefert leeren String fuer leeren Input', () => {
    expect(applyAuthPrefix('', 'Bearer ')).toBe('')
    expect(applyAuthPrefix('   ', 'Bearer ')).toBe('')
  })
})

describe('stripAuthPrefix', () => {
  it('entfernt Praefix wenn vorhanden', () => {
    expect(stripAuthPrefix('Bearer sk-abc', 'Bearer ')).toBe('sk-abc')
  })

  it('laesst Wert unveraendert wenn Praefix fehlt', () => {
    expect(stripAuthPrefix('sk-abc', 'Bearer ')).toBe('sk-abc')
  })

  it('liefert leeren String fuer undefined', () => {
    expect(stripAuthPrefix(undefined, 'Bearer ')).toBe('')
  })

  it('liefert Wert 1:1 wenn kein Praefix definiert', () => {
    expect(stripAuthPrefix('any', undefined)).toBe('any')
  })
})
