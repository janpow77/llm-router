# LLM-Router Admin UI

Vue 3 + TypeScript + Tailwind 4 Admin-Konsole für den `llm-router`.

## Quickstart

```bash
cd frontend
npm install

# Mit Mock-Daten (kein Backend nötig)
VITE_USE_MOCKS=true npm run dev

# Gegen lokales Backend (Port 7842)
npm run dev
```

Öffne http://localhost:5180/admin/

**Mock-Login-Passwort:** `admin`

## Build

```bash
npm run build       # → dist/  (Tailwind, gzipped JS deutlich unter 1 MB)
npm run preview     # statisch ausliefern
```

`dist/` kann das Backend per `StaticFiles` unter `/admin/` mounten.

## Tests

```bash
npm test            # Vitest, läuft mit Mock-Daten
npm run type-check  # vue-tsc --noEmit
npm run lint        # ESLint flat config
```

## Struktur

| Pfad | Inhalt |
|------|--------|
| `src/api/` | Pro Resource ein Modul (apps, spokes, ...) — Mock/Real-Switch |
| `src/api/mock.ts` | Hardcoded Sample-Daten + In-Memory-State |
| `src/api/types.ts` | Domain-Typen aus API-Contract |
| `src/components/layout/` | AppShell, Sidebar, TopBar |
| `src/components/shared/` | Card, Badge, Modal, ConfirmDialog, ProgressBar, Sparkline, Toasts |
| `src/components/tables/SortableTable.vue` | Generische sortierbare Tabelle |
| `src/views/` | 9 Views (Dashboard, Apps, Spokes, Models, Routes, Quotas, Logs, Audit, Settings) + Login |
| `src/router/` | Vue Router 4 mit Auth-Guard |
| `src/stores/` | Pinia (auth, theme, toast) |
| `src/utils/` | format.ts (de-DE), chart.ts (SVG-Helpers) |
| `tests/` | Vitest — Setup + 5 Test-Suiten |

## API-Contract

Siehe [`api-contract.md`](./api-contract.md) — verbindlich für Backend.

## Konvention zu mock vs. real

Alle `src/api/<resource>.ts` Module exportieren async-Funktionen. Bei
`VITE_USE_MOCKS=true` wird auf `src/api/mock.ts` umgeleitet, sonst läuft der
Call gegen das echte Backend (`/admin/api/...`).

Im **dev-Default** (kein Env-Var gesetzt) wird gegen das echte Backend
geredet — Vite-Proxy leitet auf `localhost:7842`. Wenn das Backend nicht
läuft, sieht man Fehler-Toasts (kein Crash).

## Auth-Flow

1. `/admin/login` → Passwort an `POST /admin/api/auth/login`
2. Token in `localStorage` als `llm_router_admin_token`
3. Axios-Interceptor setzt `Authorization: Bearer <token>` für alle Calls
4. Bei `401` → automatischer Redirect zu Login
5. `/admin/logout` (TopBar-Button) löscht Token

## Theme

- Hell/Dunkel-Toggle in TopBar
- Persistenz: `localStorage['llm_router_theme']`
- Initial: System-Preference
- Dark-Mode-Detection vor Mount in `main.ts` (verhindert Flash)
