# CHIMERA Live Data Recorder

Standalone app within the Chimera Platform that connects to Betfair's Live Exchange API, polls every 60 seconds for UK/IE horse racing data, saves to Google Cloud Storage in NDJSON format, and serves a live data feed for the Lay Bet App.

## Architecture

```
┌─────────────────────┐     ┌───────────────────────────┐     ┌──────────┐
│  React/Vite Frontend│────▶│  FastAPI Backend           │────▶│  Betfair │
│  (Cloudflare Pages) │     │  (Cloud Run, europe-west2) │     │  Live API│
└─────────────────────┘     │                             │     └──────────┘
                            │  ┌──────────────────────┐   │
                            │  │ Recorder Engine       │───┼──▶ GCS (NDJSON)
                            │  │  - Market Catalogue   │   │
                            │  │  - Market Books       │   │
                            │  │  - In-Memory Cache    │   │
                            │  └──────────────────────┘   │
                            │  ┌──────────────────────┐   │
                            │  │ Feed API (drop-in     │◀──┼── Lay Bet App
                            │  │  Betfair replacement) │   │
                            │  └──────────────────────┘   │
                            └───────────────────────────┘
```

## Project Structure

```
chimera-live-recorder/
├── backend/
│   ├── main.py               # FastAPI server & all API endpoints
│   ├── config.py             # Configuration (env vars + GCS persistence)
│   ├── recorder.py           # Core recording engine & state management
│   ├── betfair_client.py     # Betfair Exchange API client (read-only)
│   ├── gcs_writer.py         # GCS NDJSON writer
│   ├── Dockerfile            # Cloud Run container image
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Main React component (single-file app)
│   │   ├── App.css           # Styling (glass-morphism, cyan/purple theme)
│   │   └── main.jsx          # React entrypoint
│   ├── index.html
│   ├── vite.config.js        # Vite config with API proxy
│   └── package.json
├── reference/                # Working Lay Engine code (for comparison)
│   ├── betfair_client.py
│   ├── engine.py
│   ├── main.py
│   └── Betfair API Docs.pdf
├── .env.example              # Environment variable template
└── README.md                 # This file
```

---

## Quick Start (Local Dev)

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # Edit with your credentials
python main.py
```

Server starts at `http://localhost:8080`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard opens at `http://localhost:5173`. The Vite dev server proxies `/api/*` to `localhost:8080`.

---

## Environment Variables

### Backend

| Variable | Required | Default | Description |
|---|---|---|---|
| `BETFAIR_APP_KEY` | Yes | — | Betfair application key for API authentication |
| `BETFAIR_SSOID` | No | — | Betfair session token (can be set via dashboard UI) |
| `GCS_PROJECT_ID` | Yes | — | Google Cloud project ID |
| `GCS_BUCKET_NAME` | Yes | — | GCS bucket name for NDJSON storage |
| `GCS_BASE_PATH` | No | `betfair-live` | Root path prefix inside the bucket |
| `FRONTEND_URL` | No | `https://recorder.thync.online` | CORS origin(s), supports comma-separated list |
| `POLL_INTERVAL` | No | `60` | Seconds between polling cycles |
| `PORT` | No | `8080` | HTTP server port (set by Cloud Run) |
| `RUNTIME_CONFIG_FILE` | No | `/tmp/chimera_recorder_config.json` | Local config cache path |

### Frontend

| Variable | Required | Default | Description |
|---|---|---|---|
| `VITE_API_URL` | No | `''` (empty, uses relative `/api`) | Backend API base URL |

---

## API Endpoints

All endpoints return JSON. Base path: `/api/`.

### Health & Keepalive

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | `GET` | Health check. Returns `{"status": "ok", "recorder": "<status>"}` |
| `/api/keepalive` | `GET` | Keep-warm for Cloud Scheduler. Also triggers Betfair session keepalive if recorder is running |

### Configuration

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | `GET` | Returns current config (SSOID masked) |
| `/api/config` | `POST` | Update config fields. Persists to `/tmp` and GCS |
| `/api/countries` | `POST` | Quick-toggle country filter from dashboard. Body: `{"countries": ["GB", "IE"]}` |

**POST `/api/config` body** (all fields optional):

```json
{
  "betfair_app_key": "string",
  "betfair_ssoid": "string",
  "gcs_project_id": "string",
  "gcs_bucket_name": "string",
  "gcs_base_path": "string",
  "poll_interval_seconds": 60,
  "countries": ["GB", "IE"],
  "market_types": ["WIN"],
  "price_projection": ["EX_BEST_OFFERS", "EX_ALL_OFFERS", "EX_TRADED", "SP_AVAILABLE", "SP_TRADED"],
  "catalogue_projections": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION", "MARKET_DESCRIPTION"]
}
```

### Session & Connection Testing

| Endpoint | Method | Description |
|---|---|---|
| `/api/validate-session` | `POST` | Test a Betfair SSOID before saving. Body: `{"ssoid": "...", "app_key": "..."}` |
| `/api/test-gcs` | `POST` | Test GCS bucket connection with current config |

### Recorder Lifecycle

| Endpoint | Method | Description |
|---|---|---|
| `/api/recorder/start` | `POST` | Start the polling loop (validates session first) |
| `/api/recorder/stop` | `POST` | Stop the polling loop and save state |
| `/api/recorder/poll` | `POST` | Execute a single manual poll cycle |

**Responses**: `{"success": true/false, "message": "..."}`

### Dashboard State

| Endpoint | Method | Description |
|---|---|---|
| `/api/state` | `GET` | Full engine state for the frontend dashboard |

**Response structure:**

```json
{
  "status": "RUNNING",
  "authenticated": true,
  "date": "2026-02-13",
  "lastPoll": "2026-02-13T14:30:00+00:00",
  "pollCount": 42,
  "pollInterval": 60,
  "stats": {
    "total_polls": 42,
    "total_markets_recorded": 1260,
    "total_books_recorded": 1260,
    "total_gcs_writes": 84,
    "gcs_errors": 0,
    "api_errors": 0,
    "markets_cached": 30,
    "books_cached": 30
  },
  "gcs": {
    "enabled": true,
    "configured": true,
    "bucket": "my-bucket",
    "base_path": "betfair-live",
    "writes": 84,
    "errors": 0,
    "last_error": null
  },
  "lastCataloguePath": "betfair-live/7/2026-02-13/catalogue/14-30-00.ndjson",
  "lastBooksPath": "betfair-live/7/2026-02-13/books/14-30-00.ndjson",
  "markets": [
    {
      "marketId": "1.234567890",
      "marketName": "2m Hcap Chs",
      "marketStartTime": "2026-02-13T15:00:00.000Z",
      "venue": "Cheltenham",
      "event": "Cheltenham 13th Feb",
      "runners": 12,
      "status": "OPEN",
      "inPlay": false,
      "totalMatched": 45230.50,
      "minutesToOff": 30.0,
      "hasBookData": true
    }
  ],
  "errors": [],
  "log": [
    {
      "timestamp": "2026-02-13T14:30:00+00:00",
      "level": "info",
      "message": "Poll #42 complete: 30 markets, 30 books"
    }
  ],
  "config": { }
}
```

### Data Feed API (Lay Bet App Integration)

These endpoints mirror Betfair's response format for drop-in replacement:

| Endpoint | Method | Description |
|---|---|---|
| `/api/feed/markets` | `GET` | Cached market catalogue (same as `listMarketCatalogue`) |
| `/api/feed/book/{market_id}` | `GET` | Cached market book for one market (same as `listMarketBook`) |
| `/api/feed/books` | `POST` | Cached books for multiple markets. Body: `{"market_ids": ["1.234..."]}` |

### Debug

| Endpoint | Method | Description |
|---|---|---|
| `/api/debug/catalogue` | `GET` | Raw `listMarketCatalogue` call with minimal params (for debugging) |

---

## Recorder Engine

### Status Values

| Status | Meaning |
|---|---|
| `STOPPED` | Engine is not running |
| `STARTING` | Engine is starting up |
| `RUNNING` | Engine is running, waiting for next poll |
| `POLLING` | Currently fetching data from Betfair |
| `WRITING` | Currently writing data to GCS |
| `AUTH_ERROR` | Betfair session expired or invalid |

### Poll Cycle

Each poll cycle (default every 60 seconds):

1. **Day rollover check** — resets daily state at midnight UTC
2. **Session keepalive** — sends keepalive to Betfair if >15 min since last
3. **Fetch catalogue** — `listMarketCatalogue` for configured countries (default: GB/IE) and market types (default: WIN only)
4. **Fetch books** — `listMarketBook` for all discovered markets (auto-batched per weight limits)
5. **Write to GCS** — catalogue and books as separate NDJSON files
6. **Update caches** — in-memory caches for the feed API and dashboard
7. **Save state** — persists to `/tmp` every 5 polls for cold-start recovery

### Configuration Defaults

| Setting | Default | Description |
|---|---|---|
| `poll_interval_seconds` | `60` | Seconds between polls |
| `countries` | `["GB", "IE"]` | Market country filter |
| `event_type_id` | `"7"` | Horse Racing |
| `market_types` | `["WIN"]` | Market type filter. Set to `[]` for all types (WIN, PLACE, EACH_WAY, etc.) |
| `price_projection` | `["EX_BEST_OFFERS", "EX_ALL_OFFERS", "EX_TRADED", "SP_AVAILABLE", "SP_TRADED"]` | Price data requested per market book |
| `max_markets_per_request` | `6` | Betfair weight limit safeguard |
| `catalogue_projections` | `["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION", "MARKET_DESCRIPTION"]` | Data projections for catalogue. `MARKET_DESCRIPTION` includes `marketType` in output |

### Betfair API Weight Limits

Market book requests are auto-batched to stay within Betfair's 200-weight limit:

| Price Data | Weight |
|---|---|
| `EX_BEST_OFFERS` | 5 |
| `EX_ALL_OFFERS` | 17 |
| `EX_TRADED` | 17 |
| `SP_AVAILABLE` | 3 |
| `SP_TRADED` | 7 |
| `EX_BEST_OFFERS` + `EX_TRADED` (combined) | 20 |
| `EX_ALL_OFFERS` + `EX_TRADED` (combined) | 32 |

Formula: `batch_size = 200 / total_weight_per_market`

With the default price projection (all 5 fields), batch size = ~6 markets per API call.

---

## GCS Storage Format

```
gs://{bucket}/{base_path}/7/{YYYY-MM-DD}/
  ├── catalogue/
  │   ├── 08-30-00.ndjson
  │   ├── 08-31-00.ndjson
  │   └── ...
  └── books/
      ├── 08-30-00.ndjson
      ├── 08-31-00.ndjson
      └── ...
```

Each `.ndjson` file contains one JSON object per line (one market per line). Every record is enriched with:

| Field | Description |
|---|---|
| `_recorded_at` | ISO 8601 timestamp of when the data was captured |
| `_data_type` | `"catalogue"` or `"books"` |

### Config Persistence

Runtime config (SSOID, poll interval, etc.) is also saved to GCS to survive cold starts:

```
gs://{bucket}/{base_path}/config/runtime_config.json
```

**Load priority on startup:**
1. Environment variables (always first, provides GCS coordinates)
2. GCS config overlay (durable, survives cold starts and redeployments)
3. `/tmp` fallback (only if GCS unavailable)

---

## Deployment

### Backend to Google Cloud Run

```bash
cd backend

# Build and push
gcloud builds submit --tag gcr.io/YOUR_PROJECT/chimera-recorder

# Deploy
gcloud run deploy chimera-recorder \
  --image gcr.io/YOUR_PROJECT/chimera-recorder \
  --region europe-west2 \
  --allow-unauthenticated \
  --memory 512Mi \
  --min-instances 1 \
  --max-instances 1 \
  --set-env-vars "\
BETFAIR_APP_KEY=your-app-key,\
GCS_PROJECT_ID=your-project,\
GCS_BUCKET_NAME=your-bucket,\
FRONTEND_URL=https://your-domain.pages.dev"
```

### Frontend to Cloudflare Pages

1. Push to GitHub
2. In Cloudflare Pages, connect the repo
3. Build settings:
   - **Root directory**: `frontend`
   - **Build command**: `npm run build`
   - **Output directory**: `dist`
4. Environment variable: `VITE_API_URL=https://chimera-recorder-xxxxx.run.app`

### Cloud Scheduler (Keep-Warm)

Prevents Cloud Run cold starts by hitting the keepalive endpoint every 10 minutes:

```bash
gcloud scheduler jobs create http chimera-recorder-warmup \
  --schedule "*/10 * * * *" \
  --uri "https://chimera-recorder-xxxxx.run.app/api/keepalive" \
  --http-method GET \
  --location europe-west2
```

---

## Betfair API Notes

- **Endpoint**: JSON-RPC v1 (`https://api.betfair.com/exchange/betting/json-rpc/v1`)
- **Format**: Array-wrapped JSON-RPC payload (`json=[{jsonrpc, method, params, id}]`)
- **Auth**: SSOID passed as `X-Authentication` header, app key as `X-Application`
- **Session**: Keepalive sent every 15 minutes to `https://identitysso.betfair.com/api/keepAlive`
- **Event type**: Horse Racing = `"7"`
- **Max results**: 200 per `listMarketCatalogue` call
- **`listMarketCatalogue`** does not return CLOSED markets

---

## Dependencies

### Backend (Python 3.12)

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.6 | Web framework |
| `uvicorn[standard]` | 0.34.0 | ASGI server |
| `requests` | 2.32.3 | HTTP client for Betfair API |
| `google-cloud-storage` | 2.18.2 | GCS SDK |
| `pydantic` | 2.10.4 | Data validation & request models |
| `python-dotenv` | 1.0.1 | `.env` file loading |

### Frontend (Node.js)

| Package | Version | Purpose |
|---|---|---|
| `react` | 18.3.1 | UI framework |
| `react-dom` | 18.3.1 | React DOM renderer |
| `vite` | 6.0.3 | Build tool & dev server |
| `@vitejs/plugin-react` | 4.3.4 | React support for Vite |

---

## Changelog

### 2026-03-30 — Domain migration prep
- Replaced hardcoded `thync.online` domain references with environment variables
- `ALLOWED_ORIGINS` env var (Cloud Run) now controls CORS allowed origins — comma-separated list
- Default falls back to `http://localhost:5173` for local development

See [CHANGELOG.md](CHANGELOG.md) for a complete version history.
