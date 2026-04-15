import { useState, useEffect, useCallback, useRef } from 'react'

const API = import.meta.env.VITE_API_URL || ''

// ═══════════════════════════════════════════
//  API HELPERS
// ═══════════════════════════════════════════

async function api(path, opts = {}) {
  const url = `${API}${path}`
  let res
  try {
    res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    })
  } catch (networkErr) {
    // Network-level failure: CORS block, wrong URL, backend down
    const hint = !API
      ? ' (VITE_API_URL is empty — frontend is calling its own origin, not the backend)'
      : ` (targeting ${API})`
    throw new Error(`Network error: ${networkErr.message}${hint}`)
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.message || res.statusText)
  }
  return res.json()
}

const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) })

// ═══════════════════════════════════════════
//  STATUS HELPERS
// ═══════════════════════════════════════════

const COUNTRY_LABELS = { GB: '🇬🇧 GB', IE: '🇮🇪 IE', ZA: '🇿🇦 ZA', FR: '🇫🇷 FR' }
const ALL_COUNTRIES = ['GB', 'IE', 'ZA', 'FR']

const STATUS_COLORS = {
  RUNNING: '#00D4FF',
  POLLING: '#00D4FF',
  WRITING: '#9D4EDD',
  STOPPED: '#6b7280',
  STARTING: '#f59e0b',
  AUTH_ERROR: '#ef4444',
}

function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || '#6b7280'
  return (
    <span className="status-badge" style={{ '--badge-color': color }}>
      <span className="status-dot" />
      {status}
    </span>
  )
}

function StatCard({ label, value, sub }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value ?? '—'}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

// ═══════════════════════════════════════════
//  SETTINGS PANEL
// ═══════════════════════════════════════════

function SettingsPanel({ config, onSave, onValidateSession, onTestGCS }) {
  const [form, setForm] = useState({
    betfair_app_key: '',
    betfair_ssoid: '',
    gcs_project_id: '',
    gcs_bucket_name: '',
    gcs_base_path: 'betfair-live',
    poll_interval_seconds: 60,
    countries: 'GB,IE',
    price_projection: 'EX_BEST_OFFERS,EX_TRADED',
  })
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [testingGCS, setTestingGCS] = useState(false)
  const [message, setMessage] = useState(null)
  const initializedRef = useRef(false)

  useEffect(() => {
    if (config && !initializedRef.current) {
      initializedRef.current = true
      setForm({
        betfair_app_key: config.betfair?.app_key || '',
        betfair_ssoid: '',
        gcs_project_id: config.gcs?.project_id || '',
        gcs_bucket_name: config.gcs?.bucket_name || '',
        gcs_base_path: config.gcs?.base_path || 'betfair-live',
        poll_interval_seconds: config.recorder?.poll_interval_seconds || 60,
        countries: (config.recorder?.countries || ['GB', 'IE']).join(','),
        price_projection: (config.recorder?.price_projection || ['EX_BEST_OFFERS', 'EX_TRADED']).join(','),
      })
    }
  }, [config])

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const payload = {}
      if (form.betfair_app_key) payload.betfair_app_key = form.betfair_app_key
      if (form.betfair_ssoid) payload.betfair_ssoid = form.betfair_ssoid
      if (form.gcs_project_id) payload.gcs_project_id = form.gcs_project_id
      if (form.gcs_bucket_name) payload.gcs_bucket_name = form.gcs_bucket_name
      if (form.gcs_base_path) payload.gcs_base_path = form.gcs_base_path
      payload.poll_interval_seconds = parseInt(form.poll_interval_seconds) || 60
      payload.countries = form.countries.split(',').map((c) => c.trim()).filter(Boolean)
      payload.price_projection = form.price_projection.split(',').map((p) => p.trim()).filter(Boolean)
      await onSave(payload)
      initializedRef.current = false  // Allow form to refresh from saved config
      setMessage({ type: 'success', text: 'Configuration saved' })
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setSaving(false)
  }

  const handleValidate = async () => {
    if (!form.betfair_app_key && !config?.betfair?.app_key) {
      setMessage({ type: 'error', text: 'Enter your Betfair Application Key first.' })
      return
    }
    if (!form.betfair_ssoid) {
      setMessage({ type: 'error', text: 'Paste your Betfair SSOID (session token) first.' })
      return
    }
    setValidating(true)
    setMessage(null)
    try {
      const res = await onValidateSession(form.betfair_ssoid, form.betfair_app_key)
      setMessage({
        type: res.valid ? 'success' : 'error',
        text: res.valid ? `Session valid — ${res.message}` : res.message,
      })
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setValidating(false)
  }

  const handleTestGCS = async () => {
    setTestingGCS(true)
    setMessage(null)
    try {
      const res = await onTestGCS()
      setMessage({
        type: res.success ? 'success' : 'error',
        text: res.message,
      })
    } catch (e) {
      setMessage({ type: 'error', text: e.message })
    }
    setTestingGCS(false)
  }

  return (
    <div className="settings-panel">
      {message && (
        <div className={`msg msg-${message.type}`}>{message.text}</div>
      )}

      <div className="settings-section">
        <h3 className="section-title">Betfair API</h3>
        <div className="field-group">
          <label>App Key</label>
          <input type="text" value={form.betfair_app_key} onChange={set('betfair_app_key')} placeholder="Your Betfair app key" />
        </div>
        <div className="field-group">
          <label>SSOID (Session Token)</label>
          <div className="input-row">
            <input type="password" value={form.betfair_ssoid} onChange={set('betfair_ssoid')} placeholder="Paste SSOID here" />
            <button className="btn btn-sm" onClick={handleValidate} disabled={validating || !form.betfair_ssoid}>
              {validating ? 'Testing…' : 'Validate'}
            </button>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <h3 className="section-title">Google Cloud Storage</h3>
        <div className="field-group">
          <label>Project ID</label>
          <input type="text" value={form.gcs_project_id} onChange={set('gcs_project_id')} placeholder="your-gcp-project" />
        </div>
        <div className="field-group">
          <label>Bucket Name</label>
          <div className="input-row">
            <input type="text" value={form.gcs_bucket_name} onChange={set('gcs_bucket_name')} placeholder="your-bucket-name" />
            <button className="btn btn-sm" onClick={handleTestGCS} disabled={testingGCS}>
              {testingGCS ? 'Testing…' : 'Test'}
            </button>
          </div>
        </div>
        <div className="field-group">
          <label>Base Path</label>
          <input type="text" value={form.gcs_base_path} onChange={set('gcs_base_path')} placeholder="betfair-live" />
        </div>
      </div>

      <div className="settings-section">
        <h3 className="section-title">Recorder</h3>
        <div className="field-row">
          <div className="field-group">
            <label>Poll Interval (s)</label>
            <input type="number" min="10" max="300" value={form.poll_interval_seconds} onChange={set('poll_interval_seconds')} />
          </div>
          <div className="field-group">
            <label>Countries</label>
            <input type="text" value={form.countries} onChange={set('countries')} placeholder="GB,IE" />
          </div>
        </div>
        <div className="field-group">
          <label>Price Projection</label>
          <input type="text" value={form.price_projection} onChange={set('price_projection')} placeholder="EX_BEST_OFFERS,EX_TRADED" />
        </div>
      </div>

      <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
        {saving ? 'Saving…' : 'Save Configuration'}
      </button>
    </div>
  )
}

// ═══════════════════════════════════════════
//  MARKET TABLE
// ═══════════════════════════════════════════

function MarketTable({ markets }) {
  if (!markets || markets.length === 0) {
    return <div className="empty-state">No markets loaded yet. Start recording or run a manual poll.</div>
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Venue</th>
            <th>Race</th>
            <th>Time</th>
            <th>Mins to Off</th>
            <th>Runners</th>
            <th>Status</th>
            <th>Matched</th>
            <th>Book</th>
          </tr>
        </thead>
        <tbody>
          {markets.map((m) => {
            const mto = m.minutesToOff
            const timeClass = mto != null && mto <= 5 ? 'text-warn' : mto != null && mto <= 0 ? 'text-live' : ''
            return (
              <tr key={m.marketId}>
                <td className="text-accent">{m.venue || '—'}</td>
                <td>{m.marketName || m.event || '—'}</td>
                <td className="mono">{m.marketStartTime ? new Date(m.marketStartTime).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                <td className={`mono ${timeClass}`}>{mto != null ? `${mto.toFixed(0)}m` : '—'}</td>
                <td className="mono">{m.runners ?? '—'}</td>
                <td><StatusBadge status={m.inPlay ? 'IN_PLAY' : m.status || 'UNKNOWN'} /></td>
                <td className="mono">{m.totalMatched ? `£${Number(m.totalMatched).toLocaleString()}` : '—'}</td>
                <td>{m.hasBookData ? '✓' : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ═══════════════════════════════════════════
//  ACTIVITY LOG
// ═══════════════════════════════════════════

const LOG_LEVEL_COLORS = {
  info: '#00D4FF',
  warn: '#f59e0b',
  error: '#ef4444',
}

function ActivityLog({ log }) {
  if (!log || log.length === 0) {
    return <div className="empty-state">No activity yet. Start the recorder or run a manual poll.</div>
  }
  return (
    <div className="activity-log">
      {log.slice().reverse().map((entry, i) => (
        <div key={i} className={`log-entry log-${entry.level || 'info'}`}>
          <span className="mono log-time">{new Date(entry.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          <span className="log-level" style={{ color: LOG_LEVEL_COLORS[entry.level] || '#00D4FF' }}>
            {(entry.level || 'info').toUpperCase()}
          </span>
          <span className="log-msg">{entry.message}</span>
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════
//  ERROR LOG
// ═══════════════════════════════════════════

function ErrorLog({ errors }) {
  if (!errors || errors.length === 0) {
    return <div className="empty-state">No errors. Everything is running clean.</div>
  }
  return (
    <div className="error-log">
      {errors.slice().reverse().map((e, i) => (
        <div key={i} className="error-entry">
          <span className="mono text-muted">{new Date(e.timestamp).toLocaleTimeString('en-GB')}</span>
          <span>{e.message}</span>
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════
//  MAIN APP
// ═══════════════════════════════════════════

export default function App() {
  const [tab, setTab] = useState('dashboard')
  const [state, setState] = useState(null)
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(true)
  const [connError, setConnError] = useState(null)
  const [actionMsg, setActionMsg] = useState(null)
  const pollRef = useRef(null)

  // ── Fetch state ──
  const fetchState = useCallback(async () => {
    try {
      const s = await api('/api/state')
      setState(s)
      setConfig(s.config)
      setConnError(null)
      setLoading(false)
    } catch (e) {
      console.error('State fetch failed:', e)
      setConnError(e.message)
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchState()
    pollRef.current = setInterval(fetchState, 5000)
    return () => clearInterval(pollRef.current)
  }, [fetchState])

  // ── Actions ──
  const handleStart = async () => {
    try {
      await post('/api/recorder/start')
      setActionMsg({ type: 'success', text: 'Recorder started' })
      fetchState()
    } catch (e) {
      setActionMsg({ type: 'error', text: e.message })
    }
  }

  const handleStop = async () => {
    try {
      await post('/api/recorder/stop')
      setActionMsg({ type: 'success', text: 'Recorder stopped' })
      fetchState()
    } catch (e) {
      setActionMsg({ type: 'error', text: e.message })
    }
  }

  const handlePoll = async () => {
    try {
      setActionMsg({ type: 'info', text: 'Running poll…' })
      const res = await post('/api/recorder/poll')
      setActionMsg({ type: 'success', text: res.message })
      fetchState()
    } catch (e) {
      setActionMsg({ type: 'error', text: e.message })
    }
  }

  const handleSaveConfig = async (payload) => {
    const res = await post('/api/config', payload)
    setConfig(res.config)
    fetchState()
  }

  const handleValidateSession = async (ssoid, appKey) => {
    return await post('/api/validate-session', { ssoid, app_key: appKey || undefined })
  }

  const handleTestGCS = async () => {
    return await post('/api/test-gcs', {})
  }

  const handleToggleCountry = async (country) => {
    const current = config?.recorder?.countries || ['GB', 'IE']
    const updated = current.includes(country)
      ? current.filter(c => c !== country)
      : [...current, country]
    if (updated.length === 0) return
    try {
      const res = await post('/api/countries', { countries: updated })
      setConfig(prev => ({ ...prev, recorder: { ...prev?.recorder, countries: res.countries } }))
      fetchState()
    } catch (e) {
      setActionMsg({ type: 'error', text: e.message })
    }
  }

  // ── Derived ──
  const status = state?.status || 'LOADING'
  const isRunning = status === 'RUNNING' || status === 'POLLING' || status === 'WRITING'
  const isAuthenticated = state?.authenticated || false
  const stats = state?.stats || {}
  const gcs = state?.gcs || {}

  if (loading && !state) {
    return (
      <div className="app-shell">
        <div className="loading-screen">
          <div className="spinner" />
          <p>Connecting to recorder…</p>
          <p className="mono text-muted" style={{ fontSize: '0.75rem', marginTop: '8px' }}>
            API: {API || `${window.location.origin} (no VITE_API_URL set)`}
          </p>
        </div>
      </div>
    )
  }

  if (connError && !state) {
    return (
      <div className="app-shell">
        <div className="loading-screen">
          <h2 style={{ color: '#ef4444', marginBottom: '16px' }}>Backend Unreachable</h2>
          <p className="mono" style={{ color: '#f59e0b', maxWidth: '600px', wordBreak: 'break-all', fontSize: '0.85rem' }}>
            {connError}
          </p>
          <div style={{ marginTop: '24px', textAlign: 'left', maxWidth: '500px', fontSize: '0.85rem', lineHeight: '1.6' }}>
            <p style={{ color: '#9ca3af', marginBottom: '8px' }}><strong style={{ color: '#e5e7eb' }}>API target:</strong> <code>{API || '(empty — same origin)'}</code></p>
            <p style={{ color: '#9ca3af', marginBottom: '8px' }}><strong style={{ color: '#e5e7eb' }}>Frontend origin:</strong> <code>{window.location.origin}</code></p>
            <p style={{ color: '#9ca3af', marginBottom: '16px' }}><strong style={{ color: '#e5e7eb' }}>Calling:</strong> <code>{API || window.location.origin}/api/state</code></p>
            <p style={{ color: '#9ca3af' }}>
              {!API
                ? 'VITE_API_URL is not set. Set it in Cloudflare Pages → Settings → Environment Variables → add VITE_API_URL = your Cloud Run backend URL, then trigger a new deployment.'
                : 'Check that the Cloud Run backend is deployed and that FRONTEND_URL is set to this frontend\'s URL in the Cloud Run environment variables.'}
            </p>
          </div>
          <button className="btn btn-secondary" onClick={fetchState} style={{ marginTop: '20px' }}>
            ↻ Retry Connection
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      {/* ── HEADER ── */}
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">
            <span className="title-accent">CHIMERA</span> Live Recorder
          </h1>
          <StatusBadge status={status} />
          <span className={`api-lamp ${isAuthenticated ? 'api-live' : 'api-disconnected'}`}>
            <span className="api-lamp-dot" />
            {isAuthenticated ? 'Betfair Live' : 'Disconnected'}
          </span>
        </div>
        <div className="header-right">
          <span className="header-date mono">{state?.date || '—'}</span>
          <span className="header-sep">|</span>
          <span className="mono">Poll #{state?.pollCount ?? 0}</span>
        </div>
      </header>

      {/* ── CONNECTION ERROR BANNER (backend dropped mid-session) ── */}
      {connError && state && (
        <div className="msg msg-error msg-global" style={{ cursor: 'default' }}>
          ⚠ Backend connection lost: {connError}
        </div>
      )}

      {/* ── ACTION MSG ── */}
      {actionMsg && (
        <div className={`msg msg-${actionMsg.type} msg-global`} onClick={() => setActionMsg(null)}>
          {actionMsg.text}
        </div>
      )}

      {/* ── TABS ── */}
      <nav className="tab-bar">
        {['dashboard', 'markets', 'log', 'settings', 'errors'].map((t) => (
          <button key={t} className={`tab ${tab === t ? 'tab-active' : ''}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>

      {/* ── CONTENT ── */}
      <main className="app-main">
        {tab === 'dashboard' && (
          <div className="dashboard">
            {/* Controls */}
            <div className="glass-panel controls-panel">
              <div className="controls-row">
                {!isRunning ? (
                  <button className="btn btn-primary" onClick={handleStart}>▶ Start Recording</button>
                ) : (
                  <button className="btn btn-danger" onClick={handleStop}>■ Stop</button>
                )}
                <button className="btn btn-secondary" onClick={handlePoll} disabled={isRunning}>
                  ↻ Manual Poll
                </button>
              </div>
              {state?.lastPoll && (
                <div className="last-poll mono">
                  Last poll: {new Date(state.lastPoll).toLocaleTimeString('en-GB')} · 
                  Interval: {state.pollInterval}s
                </div>
              )}
            </div>

            {/* Country Toggles */}
            <div className="country-toggles">
              <span className="country-label">Markets:</span>
              {ALL_COUNTRIES.map(c => (
                <button
                  key={c}
                  className={`btn-country ${(config?.recorder?.countries || ['GB', 'IE']).includes(c) ? 'active' : ''}`}
                  onClick={() => handleToggleCountry(c)}
                >
                  {COUNTRY_LABELS[c]}
                </button>
              ))}
            </div>

            {/* Stats Grid */}
            <div className="stats-grid">
              <StatCard label="Total Polls" value={stats.total_polls} />
              <StatCard label="Markets Cached" value={stats.markets_cached} />
              <StatCard label="Books Cached" value={stats.books_cached} />
              <StatCard label="GCS Writes" value={stats.total_gcs_writes} />
              <StatCard label="GCS Errors" value={stats.gcs_errors} />
              <StatCard label="API Errors" value={stats.api_errors} />
            </div>

            {/* GCS Status */}
            <div className="glass-panel">
              <h3 className="section-title">Storage</h3>
              <div className="kv-grid">
                <span className="kv-key">Bucket</span>
                <span className="kv-val mono">{gcs.bucket || 'Not configured'}</span>
                <span className="kv-key">Status</span>
                <span className="kv-val">
                  {gcs.configured ? (
                    <span className="text-success">● Configured</span>
                  ) : (
                    <span className="text-warn">● Not configured</span>
                  )}
                </span>
                <span className="kv-key">Last Catalogue</span>
                <span className="kv-val mono text-muted">{state?.lastCataloguePath || '—'}</span>
                <span className="kv-key">Last Books</span>
                <span className="kv-val mono text-muted">{state?.lastBooksPath || '—'}</span>
              </div>
            </div>

            {/* Feed Status */}
            <div className="glass-panel">
              <h3 className="section-title">Data Feed</h3>
              <p className="text-muted" style={{ marginBottom: '8px' }}>
                The Lay Bet App can consume live data from this recorder's feed API.
              </p>
              <div className="kv-grid">
                <span className="kv-key">Feed URL</span>
                <span className="kv-val mono">{window.location.origin}/api/feed/</span>
                <span className="kv-key">Markets Available</span>
                <span className="kv-val mono">{stats.markets_cached ?? 0}</span>
                <span className="kv-key">Books Available</span>
                <span className="kv-val mono">{stats.books_cached ?? 0}</span>
              </div>
            </div>
          </div>
        )}

        {tab === 'markets' && (
          <div className="glass-panel">
            <h3 className="section-title">
              Markets ({state?.markets?.length || 0})
            </h3>
            <MarketTable markets={state?.markets} />
          </div>
        )}

        {tab === 'log' && (
          <div className="glass-panel">
            <h3 className="section-title">
              Activity Log ({state?.log?.length || 0})
            </h3>
            <ActivityLog log={state?.log} />
          </div>
        )}

        {tab === 'settings' && (
          <div className="glass-panel">
            <h3 className="section-title">Configuration</h3>
            <SettingsPanel
              config={config}
              onSave={handleSaveConfig}
              onValidateSession={handleValidateSession}
              onTestGCS={handleTestGCS}
            />
            <div style={{ marginTop: '24px', padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
              <h4 style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Connection Diagnostics</h4>
              <div className="kv-grid" style={{ fontSize: '0.8rem' }}>
                <span className="kv-key">API URL</span>
                <span className="kv-val mono">{API || '(not set — using same origin)'}</span>
                <span className="kv-key">Frontend Origin</span>
                <span className="kv-val mono">{window.location.origin}</span>
                <span className="kv-key">Backend Status</span>
                <span className="kv-val">{connError ? <span style={{ color: '#ef4444' }}>● Disconnected</span> : <span style={{ color: '#10b981' }}>● Connected</span>}</span>
              </div>
            </div>
          </div>
        )}

        {tab === 'errors' && (
          <div className="glass-panel">
            <h3 className="section-title">
              Error Log ({state?.errors?.length || 0})
            </h3>
            <ErrorLog errors={state?.errors} />
          </div>
        )}
      </main>
    </div>
  )
}
