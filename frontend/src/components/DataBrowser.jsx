import { useState, useEffect } from 'react'
import { fetchDates, fetchMarkets } from '../api'
import RaceSelector from './RaceSelector'

export default function DataBrowser({ onMarketsLoaded, selectedMarkets, onSelectedChange }) {
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('')
  const [marketsData, setMarketsData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchDates().then(data => {
      setDates(data.dates || [])
      if (data.dates?.length > 0) {
        setSelectedDate(data.dates[data.dates.length - 1])
      }
    })
  }, [])

  useEffect(() => {
    if (!selectedDate) return
    setLoading(true)
    fetchMarkets(selectedDate).then(data => {
      setMarketsData(data)
      onMarketsLoaded(selectedDate, data)
      setLoading(false)
    })
  }, [selectedDate])

  return (
    <div className="top-bar">
      <div className="date-picker">
        <label>Date</label>
        <select
          value={selectedDate}
          onChange={e => setSelectedDate(e.target.value)}
        >
          {dates.length === 0 && <option value="">No data</option>}
          {dates.map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        {marketsData && (
          <span className="badge badge-source">
            {marketsData.total_markets} markets / {marketsData.snapshot_count} snapshots
          </span>
        )}
      </div>

      {loading && <div className="loading">Loading markets...</div>}

      {marketsData && !loading && (
        <RaceSelector
          venues={marketsData.venues}
          selectedMarkets={selectedMarkets}
          onSelectedChange={onSelectedChange}
        />
      )}
    </div>
  )
}
