import SummaryBar from './SummaryBar'

export default function ResultsPanel({ results }) {
  if (!results) {
    return (
      <div className="panel">
        <h2>Results</h2>
        <div className="empty">
          Select races and run a back-test to see results
        </div>
      </div>
    )
  }

  const { bet_outcomes, evaluations, summary } = results

  // Build running P&L
  let runningPnl = 0
  const outcomesWithRunning = bet_outcomes.map(o => {
    runningPnl += o.profit
    return { ...o, running_pnl: runningPnl }
  })

  return (
    <div className="panel">
      <h2>Results — {results.strategy_name}</h2>

      <SummaryBar summary={summary} />

      <div style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '12px' }}>
        {results.markets_evaluated} markets evaluated /
        {results.markets_with_bets} with bets /
        {results.bets_placed} bets placed
      </div>

      {bet_outcomes.length === 0 ? (
        <div className="empty">No bets placed by this strategy</div>
      ) : (
        <div className="scroll-panel">
          <table>
            <thead>
              <tr>
                <th>Venue</th>
                <th>Market</th>
                <th>Runner</th>
                <th>Rule</th>
                <th>Type</th>
                <th>Odds</th>
                <th>Stake</th>
                <th>Liability</th>
                <th>Result</th>
                <th>P&L</th>
                <th>Running</th>
              </tr>
            </thead>
            <tbody>
              {outcomesWithRunning.map((o, i) => {
                const pnlClass = o.profit > 0
                  ? 'result-win'
                  : o.profit < 0
                    ? 'result-loss'
                    : 'result-void'
                const runClass = o.running_pnl > 0
                  ? 'pnl-positive'
                  : o.running_pnl < 0
                    ? 'pnl-negative'
                    : 'pnl-zero'

                // Find the evaluation for this market to get venue
                const eval_ = evaluations.find(e => e.market_id === o.market_id) || {}

                return (
                  <tr key={i}>
                    <td>{eval_.venue || ''}</td>
                    <td>{eval_.market_name || ''}</td>
                    <td>{o.runner_name}</td>
                    <td><code>{o.rule_id}</code></td>
                    <td>{o.bet_type}</td>
                    <td>{o.price?.toFixed(2)}</td>
                    <td>£{o.stake?.toFixed(2)}</td>
                    <td>£{o.liability?.toFixed(2)}</td>
                    <td className={pnlClass}>{o.runner_result}</td>
                    <td className={pnlClass}>
                      {o.profit >= 0 ? '+' : ''}£{o.profit?.toFixed(2)}
                    </td>
                    <td className={runClass}>
                      {o.running_pnl >= 0 ? '+' : ''}£{o.running_pnl.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
