# Cloudflare-Tunnel-Hot-Backup fuer NUC-ML-Services

Stand: 2026-05-11
Autor: Ops-Automation

## Warum

Primaerer Pfad CCX23 → NUC laeuft heute ueber Tailscale (`100.102.132.11`).
Wenn Tailscale auf der NUC ausfaellt (Service-Crash, Key-Expiry, Kernel-Modul,
Provider-Outage in Hessen), kann der `llm-router` (CCX23) den NUC-`ollama` (11434)
und `reranker-service` (8004) nicht mehr erreichen — der Workshop und audit_designer
verlieren ihre LLM-Backends.

Loesung: zusaetzliche Cloudflare-Tunnel-URLs als zweite Bahn. Die Tunnels
sind durch Cloudflare-Access geschuetzt (Service-Token), damit kein Internet-Bot
auf `https://ollama-nuc.flowaudit.de` Modelle ziehen kann.

## Architektur

```
                                Tailscale (primary)
   ┌─────────────┐       ┌─────────────────────────┐       ┌────────────────┐
   │  llm-router │──────▶│ 100.102.132.11:11434    │──────▶│ NUC ollama     │
   │  (CCX23)    │       │ 100.102.132.11:8004     │──────▶│ NUC reranker   │
   └──────┬──────┘       └─────────────────────────┘       └────────────────┘
          │
          │  bei 3× 5xx/Timeout → Failover
          ▼
   ┌─────────────────────────────────────────┐       ┌────────────────┐
   │  https://ollama-nuc.flowaudit.de        │       │ NUC ollama     │
   │  + CF-Access-Client-Id/Secret-Header    │──────▶│ via Cloudflare │
   │  https://reranker-nuc.flowaudit.de      │       │ Tunnel         │
   └─────────────────────────────────────────┘       └────────────────┘
```

## Was unangetastet bleibt

- `audit_designer_cloudflared` (Tunnel-ID `6dfb66b3-a977-4be5-9041-b01e2c18aae3`,
  Token in `/home/janpow/Projekte/audit_designer/.env`) — bedient
  `audit_designer.flowaudit.de` und bleibt der NUC-Dev-Tunnel.
- `kira_cloudflared` — bedient den Kira-Memory-Service (Telegram-Bot).
- `auditworkshop`-Tunnel auf CCX23 (workshop.flowaudit.de geht direkt ueber Caddy,
  kein Tunnel mehr).

Der neue Tunnel ist eigenstaendig, eigener Token, eigene Hostnames mit eigener
Access-Policy. Er steht parallel zu den anderen Tunnels auf der NUC.

## Schritt-fuer-Schritt: was der User manuell tun muss

### 1) Tunnel anlegen (Cloudflare-UI)

1. https://one.dash.cloudflare.com/ → Account `flowaudit.de`
2. Sidebar **Networks** → **Tunnels** → **Create a tunnel**
3. Connector: **Cloudflared** auswaehlen → **Next**
4. **Tunnel name**: `nuc-ml-fallback` → **Save tunnel**
5. Im Schritt "Install and run a connector":
   - Environment: **Docker**
   - Der eingeblendete Befehl enthaelt den **Tunnel-Token**
     (Format `eyJhIjoi…`).
   - Token kopieren — wird NICHT direkt ausgefuehrt. Stattdessen in Schritt 3 verwendet.
6. **Next** klicken (Public Hostnames legen wir gleich an).

Alternative CLI (wenn cloudflared lokal installiert):
```bash
cloudflared tunnel login                    # einmalig oeffnet Browser
cloudflared tunnel create nuc-ml-fallback   # liefert tunnel-id
# Token via UI auslesen (CLI gibt nur Credentials-JSON)
```

### 2) Public Hostnames im Tunnel konfigurieren

Im selben Tunnel ("Public Hostnames"-Tab) drei Hostnames anlegen:

| Subdomain    | Domain         | Path | Service-Type | URL                       |
|--------------|----------------|------|--------------|---------------------------|
| ollama-nuc   | flowaudit.de   | /    | HTTP         | http://localhost:11434    |
| reranker-nuc | flowaudit.de   | /    | HTTP         | http://localhost:8004     |
| vision-nuc   | flowaudit.de   | /    | HTTP         | http://localhost:8005     |

Wichtig:
- Im Service-Feld `localhost` weil der Container im `network_mode: host` laeuft.
- Bei `ollama-nuc` und `reranker-nuc` unter "Additional application settings"
  → "HTTP Settings" → **noTLSVerify**: an (Backend ist HTTP, kein TLS).
- `vision-nuc` kann jetzt schon konfiguriert werden — der Backend-Port 8005
  existiert noch nicht, der Tunnel liefert dann 502, aber der Eintrag steht.

### 3) Token in .env auf der NUC eintragen + Tunnel starten

Auf NUC:
```bash
sudo mkdir -p /etc/llm-router-fallback
sudo nano /etc/llm-router-fallback/.env
```

Inhalt:
```
TUNNEL_TOKEN_FALLBACK=eyJhIjoi…   # der in Schritt 1.5 kopierte Token
```

```bash
sudo chmod 600 /etc/llm-router-fallback/.env

# Compose-Snippet ins Repo legen (oder direkt aus llm-router/docs nehmen):
mkdir -p ~/Projekte/llm-router-fallback
cp ~/Projekte/llm-router/docs/nuc-cloudflared-fallback.compose.yaml \
   ~/Projekte/llm-router-fallback/compose.yaml

cd ~/Projekte/llm-router-fallback
docker compose --env-file /etc/llm-router-fallback/.env up -d
docker logs nuc_ml_fallback_cloudflared --tail 30
```

Erwartete Ausgabe: `Registered tunnel connection` + 4 Connections (4 Cloudflare-PoPs).

### 4) Cloudflare-Access-Application pro Hostname

Damit nur authentifizierte Requests durch den Tunnel kommen.

In Cloudflare-Zero-Trust-Dashboard:
1. Sidebar **Access** → **Applications** → **Add an application**
2. Application Type: **Self-hosted**
3. **Application name**: `NUC Ollama Fallback`
4. **Application domain**: `ollama-nuc.flowaudit.de`
5. **Identity providers**: keine ankreuzen (wir wollen nur Service-Token, keinen
   Browser-Login)
6. **Next** → bei **Policies** **Add a policy**:
   - Policy name: `llm-router service`
   - Action: **Service Auth**
   - Configure rules → Include: **Service Token** = `<wird in Schritt 5 angelegt>`
   - Falls noch kein Token existiert: erst Schritt 5 ausfuehren, dann hierher
     zurueck und die Policy fertig konfigurieren.
7. **Next** → defaults uebernehmen → **Add application**

Dasselbe fuer `reranker-nuc.flowaudit.de` und `vision-nuc.flowaudit.de`.

Hinweis: alle drei Applications koennen denselben Service-Token verwenden.

### 5) Service-Token generieren

1. **Access** → **Service Auth** → **Service Tokens** → **Create Service Token**
2. **Service Token Name**: `llm-router-ccx23`
3. **Duration**: `Non-expiring` (oder 1 year, jaehrlich rotieren)
4. **Generate Token**
5. **Client ID** und **Client Secret** kopieren — werden NUR EINMAL angezeigt.

### 6) Service-Token auf CCX23 hinterlegen

Auf CCX23:
```bash
sudo nano /etc/llm-router/env
```

Folgende zwei Zeilen eintragen (oder ergaenzen):
```
CF_ACCESS_CLIENT_ID=<Client-ID aus Schritt 5>.access
CF_ACCESS_CLIENT_SECRET=<Client-Secret aus Schritt 5>
```

```bash
sudo chmod 600 /etc/llm-router/env
sudo systemctl restart llm-router          # oder: cd /opt/llm-router && docker compose up -d
```

Der llm-router liest die Env-Vars beim Start und setzt sie automatisch als
HTTP-Header auf jedem Failover-Request (siehe `docs/fallback-patch.diff`).

### 7) Spoke-Konfiguration anpassen

Im llm-router-Admin (https://router.flowaudit.de/admin/spokes oder via API)
fuer jeden Spoke, der einen Fallback nutzen soll, das Feld `fallback_url`
setzen:

| Spoke         | base_url                          | fallback_url                            |
|---------------|-----------------------------------|-----------------------------------------|
| nuc-ollama    | http://100.102.132.11:11434       | https://ollama-nuc.flowaudit.de         |
| nuc-reranker  | http://100.102.132.11:8004        | https://reranker-nuc.flowaudit.de       |
| nuc-vision    | http://100.102.132.11:8005        | https://vision-nuc.flowaudit.de         |

YAML-Variante (falls noch im YAML-Fallback-Mode):
```yaml
spokes:
  - name: nuc-reranker
    base_url: http://100.102.132.11:8004
    fallback_url: https://reranker-nuc.flowaudit.de
    capabilities: [rerank]
    auto_failover: true
```

### 8) Verifikation

Auf CCX23:
```bash
# 1) Direkt-Test gegen den Fallback (mit Service-Token)
curl -i https://reranker-nuc.flowaudit.de/health \
  -H "CF-Access-Client-Id: $(grep CF_ACCESS_CLIENT_ID /etc/llm-router/env | cut -d= -f2-)" \
  -H "CF-Access-Client-Secret: $(grep CF_ACCESS_CLIENT_SECRET /etc/llm-router/env | cut -d= -f2-)"

# Erwartet: HTTP/2 200 + JSON
```

```bash
# 2) Ohne Token muss Access ablehnen
curl -i https://reranker-nuc.flowaudit.de/health
# Erwartet: HTTP/2 302 redirect zu Cloudflare-Login oder 401
```

Failover-Test:
```bash
# Auf NUC Tailscale stoppen
sudo tailscale down

# Auf CCX23 einen rerank-Request schicken
curl -i -X POST https://router.flowaudit.de/v1/rerank \
  -H "X-App-Id: audit_designer" \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-reranker","query":"test","documents":["a","b"]}'

# Im llm-router-Log nach "failover" suchen:
docker logs llm-router 2>&1 | grep -i failover

# Audit-Log im Admin pruefen — Action "route.failover"
```

```bash
# Wiederherstellen
sudo tailscale up
```

## Anti-Patterns / was NICHT tun

- **Token NICHT in YAML/git committen** — nur in `/etc/llm-router/env` (chmod 600).
- **Cloudflare-Access-Policy NICHT auf "Allow / Everyone"** — dann kann jeder im
  Internet `https://ollama-nuc.flowaudit.de/api/generate` mit grossen Prompts
  abfeuern und die NUC-GPU dichthalten. **Service Auth** ist Pflicht.
- **TUNNEL_TOKEN nicht recyclen** — nicht denselben Token wie audit_designer
  verwenden, das wuerde die Hostname-Liste in dem anderen Tunnel mischen.
- **Tailscale nicht abschalten "weil's ja Fallback gibt"** — Tailscale bleibt der
  Primaerpfad (kein TLS-Overhead, kein Cloudflare-Roundtrip). Cloudflare ist
  fuer Outages.

## Operative Hinweise

- **Tunnel-Status**: `docker logs nuc_ml_fallback_cloudflared` oder Cloudflare-UI
  → Tunnels → `nuc-ml-fallback` zeigt 4 aktive Verbindungen (gruen).
- **Token-Rotation**: Service-Token alle 12 Monate erneuern. Neuer Token
  hinzufuegen, in Access-Policy beide Tokens whitelisten, dann in
  `/etc/llm-router/env` umstellen, dann alten Token loeschen.
- **Beobachten**: Wenn `route.failover` mehr als 1× pro Tag im Audit-Log erscheint,
  ist Tailscale instabil — Ursache pruefen.
- **Vision-Service**: sobald `vision-service` auf Port 8005 lebt, ist der
  Fallback-Hostname schon aktiv (kein neuer Cloudflare-Schritt noetig).
