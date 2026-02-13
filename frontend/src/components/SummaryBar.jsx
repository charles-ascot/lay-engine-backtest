export default function SummaryBar({ summary }) {
  if (!summary) return null

  const pnlClass = summary.total_pnl > 0
    ? 'pnl-positive'
    : summary.total_pnl < 0
      ? 'pnl-negative'
      : 'pnl-zero'

  return (
    <div className="summary-bar">
      <div className="summary-stat">
        <div className="label">P&L</div>
        <div className={`value ${pnlClass}`}>
          {summary.total_pnl >= 0 ? '+' : ''}£{summary.total_pnl.toFixed(2)}
        </div>
      </div>
      <div className="summary-stat">
        <div className="label">Wins</div>
        <div className="value pnl-positive">{summary.win_count}</div>
      </div>
      <div className="summary-stat">
        <div className="label">Losses</div>
        <div className="value pnl-negative">{summary.loss_count}</div>
      </div>
      <div className="summary-stat">
        <div className="label">Win Rate</div>
        <div className="value">
          {summary.win_count + summary.loss_count > 0
            ? ((summary.win_count / (summary.win_count + summary.loss_count)) * 100).toFixed(1)
            : '0'}%
        </div>
      </div>
      <div className="summary-stat">
        <div className="label">ROI</div>
        <div className={`value ${pnlClass}`}>{summary.roi_percent.toFixed(1)}%</div>
      </div>
      <div className="summary-stat">
        <div className="label">Staked</div>
        <div className="value">£{summary.total_stake.toFixed(2)}</div>
      </div>
      <div className="summary-stat">
        <div className="label">Liability</div>
        <div className="value">£{summary.total_liability.toFixed(2)}</div>
      </div>
      <div className="summary-stat">
        <div className="label">Avg Win</div>
        <div className="value pnl-positive">£{summary.avg_win.toFixed(2)}</div>
      </div>
      <div className="summary-stat">
        <div className="label">Avg Loss</div>
        <div className="value pnl-negative">£{summary.avg_loss.toFixed(2)}</div>
      </div>
    </div>
  )
}
