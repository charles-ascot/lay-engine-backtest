export default function RaceSelector({ venues, selectedMarkets, onSelectedChange }) {
  if (!venues || venues.length === 0) {
    return <div className="race-list"><span className="empty">No WIN markets found</span></div>
  }

  const allMarketIds = venues.flatMap(v => v.markets.map(m => m.market_id))

  const toggleMarket = (id) => {
    if (selectedMarkets.includes(id)) {
      onSelectedChange(selectedMarkets.filter(m => m !== id))
    } else {
      onSelectedChange([...selectedMarkets, id])
    }
  }

  const selectAll = () => onSelectedChange([...allMarketIds])
  const selectNone = () => onSelectedChange([])

  const formatTime = (iso) => {
    try {
      const d = new Date(iso)
      return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    } catch { return '' }
  }

  return (
    <div className="race-list">
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
        {venues.map(venue => (
          <div key={venue.venue} className="venue-group">
            <div className="venue-name">{venue.venue}</div>
            {venue.markets.map(m => (
              <label key={m.market_id} className="race-item">
                <input
                  type="checkbox"
                  checked={selectedMarkets.includes(m.market_id)}
                  onChange={() => toggleMarket(m.market_id)}
                />
                <span className="race-time">{formatTime(m.market_start_time)}</span>
                <span className="race-name">{m.market_name}</span>
                <span className="race-runners">({m.runner_count})</span>
              </label>
            ))}
          </div>
        ))}
      </div>
      <div className="race-controls">
        <button className="btn-sm" onClick={selectAll}>Select All</button>
        <button className="btn-sm" onClick={selectNone}>Clear</button>
        <span style={{ color: 'var(--muted)', fontSize: '12px' }}>
          {selectedMarkets.length} of {allMarketIds.length} selected
        </span>
      </div>
    </div>
  )
}
