const BASE = ''

export async function fetchDates() {
  const r = await fetch(`${BASE}/api/dates`)
  return r.json()
}

export async function fetchMarkets(date) {
  const r = await fetch(`${BASE}/api/markets/${date}`)
  return r.json()
}

export async function fetchDefaultStrategy() {
  const r = await fetch(`${BASE}/api/strategies/default`)
  return r.json()
}

export async function fetchStrategies() {
  const r = await fetch(`${BASE}/api/strategies`)
  return r.json()
}

export async function fetchStrategy(id) {
  const r = await fetch(`${BASE}/api/strategies/${id}`)
  return r.json()
}

export async function saveStrategy(strategy) {
  const r = await fetch(`${BASE}/api/strategies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strategy }),
  })
  return r.json()
}

export async function runSimulation(date, strategy, marketIds = null) {
  const r = await fetch(`${BASE}/api/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, strategy, market_ids: marketIds }),
  })
  return r.json()
}
