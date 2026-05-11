/**
 * Kuratierte Liste bekannter LLM-Provider-Presets fuer das Spoke-Form.
 *
 * Der Admin waehlt im Provider-Picker eine Vorlage; alle relevanten Felder
 * (base_url, type, auth_header, capabilities, etc.) werden vorausgefuellt.
 * Das eigentliche API-Key-Feld bleibt leer und wird vom User eingetragen.
 *
 * type-Mapping:
 *   - "openai":  OpenAI-kompatibles Schema (/v1/chat/completions, /v1/models)
 *                — Spoke funktioniert direkt fuer Routing/Discovery.
 *   - "ollama":  Direkter Ollama-Endpoint.
 *   - "custom":  API ist nicht OpenAI-kompatibel (z.B. Anthropic
 *                /v1/messages, Gemini generateContent). Spoke kann angelegt
 *                werden, fuer Routing ist aber ein Adapter noetig (siehe
 *                docs/external-providers.md).
 *
 * auth_value_prefix wird beim Speichern automatisch dem User-Input vorangestellt
 * (z.B. "Bearer " + "sk-proj-..." → "Bearer sk-proj-..."). Wenn leer, wird
 * der Wert 1:1 als Header-Value gesetzt (z.B. Anthropic x-api-key).
 */
import type { SpokeCapability, SpokeType } from '../api/types'

export interface ProviderPreset {
  /** Stabile ID, z.B. 'openai', 'anthropic', 'custom'. */
  id: string
  /** Anzeige-Name im Dropdown. */
  label: string
  /** Basis-URL ohne trailing slash. */
  base_url: string
  /** Spoke-Typ — bestimmt Routing/Discovery-Pfad im Backend. */
  type: SpokeType
  /** Header-Name fuer Auth (z.B. 'Authorization', 'x-api-key'). */
  auth_header: string
  /** Praefix, der dem Token vorangestellt wird (z.B. 'Bearer '). */
  auth_value_prefix?: string
  /** Default-Capabilities — koennen vom User noch angepasst werden. */
  capabilities: SpokeCapability[]
  /** GET-Pfad fuer Connection-Test (z.B. '/v1/models'). Leer = kein Test. */
  test_endpoint: string
  /** Doku-Link fuer den User. */
  docs_url: string
  /** Beispiel-Token-Format fuer das Input-Placeholder. */
  placeholder_key?: string
  /**
   * Optionaler Hinweis-Banner. Wird angezeigt, wenn der Provider noch nicht
   * direkt routingfaehig ist (z.B. Anthropic, Gemini — custom statt openai).
   */
  notice?: string
}

/**
 * Custom / Self-hosted: leere Defaults, behaelt das bestehende Verhalten des
 * Forms bei (keine Auto-Fuellung). Steht bewusst als erste Option im Picker.
 */
const CUSTOM_PRESET: ProviderPreset = {
  id: 'custom',
  label: 'Custom / Self-hosted (keine Vorlage)',
  base_url: '',
  type: 'custom',
  auth_header: 'Authorization',
  capabilities: ['llm'],
  test_endpoint: '',
  docs_url: '',
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  CUSTOM_PRESET,
  {
    id: 'openai',
    label: 'OpenAI',
    base_url: 'https://api.openai.com',
    type: 'openai',
    auth_header: 'Authorization',
    auth_value_prefix: 'Bearer ',
    capabilities: ['llm', 'embedding', 'vision'],
    test_endpoint: '/v1/models',
    docs_url: 'https://platform.openai.com/docs/api-reference',
    placeholder_key: 'sk-proj-...',
  },
  {
    id: 'anthropic',
    label: 'Anthropic (Claude)',
    base_url: 'https://api.anthropic.com',
    // Anthropic-API ist nicht OpenAI-kompatibel — Adapter noch nicht
    // implementiert. Spoke wird als 'custom' angelegt; Routing kommt spaeter.
    type: 'custom',
    auth_header: 'x-api-key',
    auth_value_prefix: '',
    capabilities: ['llm'],
    test_endpoint: '/v1/models',
    docs_url: 'https://docs.anthropic.com/en/api/getting-started',
    placeholder_key: 'sk-ant-...',
    notice:
      'Anthropic-API ist nicht OpenAI-kompatibel. Spoke wird angelegt, '
      + 'fuer Routing braucht es einen spaeteren Adapter-Patch.',
  },
  {
    id: 'google-gemini',
    label: 'Google Gemini',
    base_url: 'https://generativelanguage.googleapis.com',
    type: 'custom',
    // Gemini benutzt API-Key per Query-Param ODER X-Goog-Api-Key Header.
    // Wir tragen X-Goog-Api-Key als Default ein; der Adapter muss spaeter
    // entscheiden ob er den Header oder den ?key=-Parameter nutzt.
    auth_header: 'X-Goog-Api-Key',
    auth_value_prefix: '',
    capabilities: ['llm', 'embedding', 'vision'],
    test_endpoint: '/v1beta/models',
    docs_url: 'https://ai.google.dev/gemini-api/docs',
    placeholder_key: 'AIza...',
    notice:
      'Gemini-API ist nicht OpenAI-kompatibel. Spoke wird angelegt, '
      + 'fuer Routing braucht es einen spaeteren Adapter-Patch.',
  },
  {
    id: 'mistral',
    label: 'Mistral AI',
    base_url: 'https://api.mistral.ai',
    type: 'openai',
    auth_header: 'Authorization',
    auth_value_prefix: 'Bearer ',
    capabilities: ['llm', 'embedding'],
    test_endpoint: '/v1/models',
    docs_url: 'https://docs.mistral.ai/api/',
    placeholder_key: 'sk-...',
  },
  {
    id: 'cohere',
    label: 'Cohere',
    base_url: 'https://api.cohere.com',
    type: 'openai',
    auth_header: 'Authorization',
    auth_value_prefix: 'Bearer ',
    capabilities: ['llm', 'embedding', 'rerank'],
    test_endpoint: '/v1/models',
    docs_url: 'https://docs.cohere.com/reference/about',
    placeholder_key: 'co-...',
  },
  {
    id: 'together',
    label: 'Together AI',
    base_url: 'https://api.together.xyz',
    type: 'openai',
    auth_header: 'Authorization',
    auth_value_prefix: 'Bearer ',
    capabilities: ['llm', 'embedding'],
    test_endpoint: '/v1/models',
    docs_url: 'https://docs.together.ai/reference/completions-1',
    placeholder_key: 'tgp_...',
  },
  {
    id: 'groq',
    label: 'Groq',
    base_url: 'https://api.groq.com/openai',
    type: 'openai',
    auth_header: 'Authorization',
    auth_value_prefix: 'Bearer ',
    capabilities: ['llm'],
    test_endpoint: '/v1/models',
    docs_url: 'https://console.groq.com/docs/api-reference',
    placeholder_key: 'gsk_...',
  },
  {
    id: 'ollama-local',
    label: 'Ollama (lokal)',
    base_url: 'http://localhost:11434',
    type: 'ollama',
    auth_header: 'Authorization',
    auth_value_prefix: '',
    capabilities: ['llm', 'embedding'],
    test_endpoint: '/api/tags',
    docs_url: 'https://github.com/ollama/ollama/blob/main/docs/api.md',
  },
]

/** Lookup eines Presets per ID. Liefert Custom-Preset als Fallback. */
export function getProviderPreset(id: string): ProviderPreset {
  return PROVIDER_PRESETS.find(p => p.id === id) ?? CUSTOM_PRESET
}

/**
 * Wendet das Praefix auf den User-Input an. Idempotent — wenn der Wert das
 * Praefix bereits enthaelt, wird es nicht doppelt eingefuegt.
 */
export function applyAuthPrefix(value: string, prefix?: string): string {
  const v = value.trim()
  if (!v) return ''
  if (!prefix) return v
  if (v.toLowerCase().startsWith(prefix.toLowerCase())) return v
  return `${prefix}${v}`
}

/**
 * Entfernt das Praefix vom gespeicherten Wert, damit das Input-Feld beim
 * Edit eines Spokes den blanken Token zeigt (User soll keine "Bearer "-
 * Praefixe sehen wenn das Preset sie ohnehin verwaltet).
 */
export function stripAuthPrefix(value: string | undefined, prefix?: string): string {
  if (!value) return ''
  if (!prefix) return value
  if (value.toLowerCase().startsWith(prefix.toLowerCase())) {
    return value.slice(prefix.length)
  }
  return value
}
