import { useState, useCallback } from 'react'
import DataBrowser from './components/DataBrowser'
import StrategyEditor from './components/StrategyEditor'
import ResultsPanel from './components/ResultsPanel'
import { runSimulation } from './api'

export default function App() {
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedMarkets, setSelectedMarkets] = useState([])
  const [strategy, setStrategy] = useState(null)
  const [results, setResults] = useState(null)
  const [running, setRunning] = useState(false)

  const onMarketsLoaded = useCallback((date, data) => {
    setSelectedDate(date)
    // Auto-select all WIN markets
    const allIds = (data.venues || []).flatMap(v => v.markets.map(m => m.market_id))
    setSelectedMarkets(allIds)
    setResults(null)
  }, [])

  const handleRun = async () => {
    if (!selectedDate || !strategy) return
    setRunning(true)
    try {
      const marketIds = selectedMarkets.length > 0 ? selectedMarkets : null
      const data = await runSimulation(selectedDate, strategy, marketIds)
      setResults(data)
    } catch (err) {
      console.error('Simulation error:', err)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="app">
      <header>
        <div className="header-left">
          <h1>CHIMERA Back-Test Workbench</h1>
        </div>
        <div className="header-right">
          <button
            className="btn btn-primary"
            onClick={handleRun}
            disabled={running || !selectedDate || !strategy}
          >
            {running ? 'Running...' : 'Run Back-Test'}
          </button>
        </div>
      </header>

      <DataBrowser
        onMarketsLoaded={onMarketsLoaded}
        selectedMarkets={selectedMarkets}
        onSelectedChange={setSelectedMarkets}
      />

      <div className="main-grid">
        <StrategyEditor
          strategy={strategy}
          onChange={setStrategy}
        />
        <ResultsPanel results={results} />
      </div>
    </div>
  )
}
