const TARGETS = [
  { value: 'favourite', label: 'Favourite' },
  { value: 'second_favourite', label: '2nd Favourite' },
  { value: 'third_favourite', label: '3rd Favourite' },
]

export default function ActionRow({ action, onChange, onDelete }) {
  const update = (key, val) => {
    onChange({ ...action, [key]: val })
  }

  return (
    <div className="action-row">
      <select value={action.bet_type} onChange={e => update('bet_type', e.target.value)}>
        <option value="LAY">LAY</option>
        <option value="BACK">BACK</option>
      </select>
      <select value={action.target} onChange={e => update('target', e.target.value)}>
        {TARGETS.map(t => (
          <option key={t.value} value={t.value}>{t.label}</option>
        ))}
      </select>
      <span style={{ color: 'var(--muted)', fontSize: '12px' }}>£</span>
      <input
        type="number"
        step="0.5"
        min="0.01"
        value={action.stake}
        onChange={e => update('stake', parseFloat(e.target.value) || 0)}
      />
      <button className="btn-icon" onClick={onDelete} title="Remove action">&times;</button>
    </div>
  )
}
