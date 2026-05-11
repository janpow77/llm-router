# Externe LLM-Provider als Spokes

Der llm-router unterstuetzt externe LLM-APIs (OpenAI, Anthropic, Mistral,
Gemini, ...) als Fallback-Spokes. Im Admin-UI (`/admin/spokes` → "Neuer
Spoke") gibt es ein Dropdown "Provider-Vorlage", das die wichtigsten Felder
(base_url, auth_header, capabilities, test_endpoint) auto-fuellt.

Die kuratierte Preset-Liste lebt in
[`frontend/src/data/providers.ts`](../frontend/src/data/providers.ts).

## Kategorien

### 1. OpenAI-kompatibel (Spoke-Typ `openai`)

Provider, die dem OpenAI-API-Schema folgen
(`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`). Diese
funktionieren direkt mit dem bestehenden Proxy/Routing — **kein Adapter
noetig**.

| Provider     | base_url                          | Auth-Header     | Praefix    |
|--------------|-----------------------------------|-----------------|------------|
| OpenAI       | `https://api.openai.com`          | `Authorization` | `Bearer `  |
| Mistral AI   | `https://api.mistral.ai`          | `Authorization` | `Bearer `  |
| Cohere       | `https://api.cohere.com`          | `Authorization` | `Bearer `  |
| Together AI  | `https://api.together.xyz`        | `Authorization` | `Bearer `  |
| Groq         | `https://api.groq.com/openai`     | `Authorization` | `Bearer `  |

### 2. Eigene Schemas (Spoke-Typ `custom`)

Provider mit nicht-OpenAI-kompatibler API. Spoke kann angelegt werden, das
Routing braucht aber einen **spaeteren Adapter-Patch**, bevor der Proxy
Requests dorthin weiterleiten kann. Im UI erscheint ein gelber Hinweis-
Banner.

| Provider | API-Pfad statt `/v1/chat/completions` | Auth-Header        | Hinweis                                |
|----------|---------------------------------------|--------------------|----------------------------------------|
| Anthropic | `/v1/messages`                       | `x-api-key` (kein Bearer-Praefix) | Adapter-Patch ausstehend |
| Google Gemini | `/v1beta/models/{name}:generateContent` | `X-Goog-Api-Key` (oder `?key=...`) | Adapter-Patch ausstehend |

### 3. Lokale Provider

| Provider        | base_url                  | Spoke-Typ |
|-----------------|---------------------------|-----------|
| Ollama (lokal)  | `http://localhost:11434`  | `ollama`  |

## Test-Connection

Der Button "Verbindung testen" im Form ruft `POST
/admin/api/spokes/test-connection` auf. Das Backend macht einen GET auf
`base_url + test_endpoint` (Default `/v1/models`) mit Timeout 5s, parst
die Antwort und liefert `models_count` zurueck.

- Auth-Werte werden ausschliesslich im Request an den Provider verwendet,
  **nicht persistiert** und **nicht geloggt**.
- Bei 401/403 vom Provider wird `{ok: false, error: "HTTP 401"}` geliefert
  — der Provider-Response-Body wird nicht durchgereicht, um Leaks zu
  vermeiden.

## Neuen Provider hinzufuegen

1. Eintrag in `PROVIDER_PRESETS` in
   `frontend/src/data/providers.ts` ergaenzen.
2. Wenn die API OpenAI-kompatibel ist: `type: 'openai'` setzen.
3. Wenn nicht: `type: 'custom'` + `notice` mit Adapter-Hinweis setzen.
4. `test_endpoint` auf den GET-fuer-Modell-Liste-Endpoint setzen (oder
   `/health` falls keine Modell-Discovery vorhanden).
5. Frontend-Tests laufen lassen: `cd frontend && npm test`.

## Roadmap: Adapter fuer nicht-OpenAI-kompatible Provider

- **Anthropic-Adapter**: Mappt `/v1/chat/completions`-Requests auf
  `/v1/messages`. Konvertiert `messages[].role: system` zu Top-Level
  `system`-Parameter. Streaming via SSE bleibt erhalten.
- **Gemini-Adapter**: Mappt auf
  `/v1beta/models/{model}:generateContent`. Authentifizierung wahlweise
  via Header `X-Goog-Api-Key` oder Query-Param `?key=`.

Status: Konzept — Implementierung in separatem PR.
