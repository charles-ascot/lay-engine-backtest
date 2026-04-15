# Changelog

All notable changes to the CHIMERA Live Data Recorder are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

## [1.4.0] - 2026-02-18

### Added
- **Country filter toggle buttons** on the dashboard (GB, IE, ZA, FR) matching the Lay Engine's UI pattern (`7611063`)
- **`POST /api/countries`** endpoint for quick country toggling without going through full config save
- **`MARKET_DESCRIPTION`** added to default catalogue projections, so `description.marketType` is now stored in NDJSON output (`edc9665`)

### Changed
- Country filter is now accessible directly from the dashboard instead of only through the Settings tab

## [1.3.0] - 2026-02-14

### Fixed
- **TOO_MUCH_DATA error** from Betfair API: reduced `listMarketCatalogue` maxResults from 1000 to 200 (`9131395`)
- **TOO_MUCH_DATA error** (continued): added `marketTypeCodes: ["WIN"]` filter and reduced catalogue projections to `EVENT`, `MARKET_START_TIME`, `RUNNER_DESCRIPTION` (`f53037a`)

### Changed
- Default `market_types` changed from `[]` (all) to `["WIN"]` to reduce API data weight
- Default `catalogue_projections` reduced from 7 projections to 3 (now 4 with MARKET_DESCRIPTION) to stay within Betfair weight limits

## [1.2.0] - 2026-02-13

### Added
- **Activity log** with real-time visibility into recorder operations; new "Log" tab in dashboard (`032db6b`)
- **Betfair API connection status lamp** in header — pulsing green when connected, red when disconnected (`1f887c9`)
- **`/api/debug/catalogue`** endpoint for raw Betfair API inspection (`dfc6db3`)

### Fixed
- Settings form being wiped by the 5-second state polling cycle (`7a1cd0f`)
- `maxResults` type mismatch causing API errors (`4d1338f`)
- Reverted REST API experiment back to JSON-RPC format matching the working Lay Engine reference (`a360863`)

## [1.1.0] - 2026-02-12

### Added
- **GCS config persistence** for durability across Cloud Run cold starts (`9eb6bfc`). Three-tier config loading: environment variables, GCS overlay, /tmp fallback
- **Comma-separated CORS origins** support in `FRONTEND_URL` (`fb2be2f`)

### Reverted
- "CHIMERA DataPulse" rebrand reverted back to "CHIMERA Live Recorder" (`f5d1083`)

## [1.0.0] - 2026-02-12

### Added
- Initial release: CHIMERA Live Data Recorder (`e7768ec`)
- **FastAPI backend** with Betfair Exchange API client (read-only, JSON-RPC)
- **React/Vite frontend** with glassmorphism dashboard (cyan/purple theme)
- **Recorder engine** with configurable polling interval (default 60s)
- **GCS NDJSON writer** with timestamped catalogue and books storage
- **Data feed API** (`/api/feed/*`) as drop-in Betfair replacement for the Lay Bet App
- **Cloud Run** deployment with Docker (europe-west2)
- **Cloudflare Pages** frontend deployment
- **Cloud Scheduler** keep-warm endpoint (`/api/keepalive`)
- Dashboard tabs: Dashboard, Markets, Log, Settings, Errors
- Session validation and GCS connection testing from the UI
- Automatic Betfair session keepalive every 15 minutes
- Automatic day rollover at midnight UTC
- State persistence to `/tmp` for Cloud Run warm-restart recovery
- Auto-batching of market book requests respecting Betfair's 200-weight limit

---

## Data Format

### GCS Storage Hierarchy

```
gs://{bucket}/{base_path}/{event_type}/{YYYY-MM-DD}/
  ├── catalogue/{HH-MM-SS}.ndjson
  └── books/{HH-MM-SS}.ndjson
```

### NDJSON Record Enrichment

Every record written to GCS includes metadata fields:
- `_recorded_at` — ISO 8601 timestamp of capture
- `_data_type` — `"catalogue"` or `"books"`

### Catalogue Record Fields (per market)

| Field | Source |
|---|---|
| `marketId` | Betfair API |
| `marketName` | Betfair API |
| `marketStartTime` | `MARKET_START_TIME` projection |
| `event.venue` | `EVENT` projection |
| `event.countryCode` | `EVENT` projection |
| `event.name` | `EVENT` projection |
| `description.marketType` | `MARKET_DESCRIPTION` projection (added v1.4.0) |
| `description.marketTime` | `MARKET_DESCRIPTION` projection (added v1.4.0) |
| `runners[].selectionId` | `RUNNER_DESCRIPTION` projection |
| `runners[].runnerName` | `RUNNER_DESCRIPTION` projection |

### Books Record Fields (per market)

| Field | Source |
|---|---|
| `marketId` | Betfair API |
| `status` | Market status (OPEN, SUSPENDED, CLOSED) |
| `inPlay` | Whether the market is in-play |
| `totalMatched` | Total amount matched on market |
| `runners[].selectionId` | Runner identifier |
| `runners[].status` | Runner status (ACTIVE, REMOVED, WINNER, LOSER) |
| `runners[].ex.availableToBack` | Back prices and sizes |
| `runners[].ex.availableToLay` | Lay prices and sizes |
| `runners[].ex.tradedVolume` | Traded volume at each price |
| `runners[].sp.nearPrice` | SP near price |
| `runners[].sp.farPrice` | SP far price |

---

## Downstream Consumers

| App | How it uses recorder data |
|---|---|
| **CHIMERA Lay Engine** | Reads GCS NDJSON for "Auto Dry Run" feature — replays recorded data through strategy rules for drift analysis |
| **CHIMERA Lay Engine** | Can use Feed API (`/api/feed/*`) as a drop-in replacement for direct Betfair API calls |
