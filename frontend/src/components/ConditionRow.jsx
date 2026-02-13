const FIELDS = [
  { value: 'fav_lay_odds', label: 'Fav lay odds' },
  { value: 'fav_back_odds', label: 'Fav back odds' },
  { value: 'second_fav_lay_odds', label: '2nd fav lay odds' },
  { value: 'second_fav_back_odds', label: '2nd fav back odds' },
  { value: 'gap_to_second', label: 'Gap to 2nd' },
  { value: 'runner_count', label: 'Runner count' },
  { value: 'total_matched', label: 'Total matched' },
  { value: 'fav_total_matched', label: 'Fav total matched' },
]

const OPERATORS = [
  { value: 'lt', label: '<' },
  { value: 'lte', label: '<=' },
  { value: 'gt', label: '>' },
  { value: 'gte', label: '>=' },
  { value: 'eq', label: '=' },
  { value: 'neq', label: '!=' },
  { value: 'between', label: 'between' },
]

export default function ConditionRow({ condition, onChange, onDelete }) {
  const update = (key, val) => {
    onChange({ ...condition, [key]: val })
  }

  return (
    <div className="condition-row">
      <select value={condition.field} onChange={e => update('field', e.target.value)}>
        {FIELDS.map(f => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>
      <select value={condition.operator} onChange={e => update('operator', e.target.value)}>
        {OPERATORS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <input
        type="number"
        step="0.1"
        value={condition.value}
        onChange={e => update('value', parseFloat(e.target.value) || 0)}
      />
      {condition.operator === 'between' && (
        <>
          <span style={{ color: 'var(--muted)', fontSize: '12px' }}>and</span>
          <input
            type="number"
            step="0.1"
            value={condition.value_high || ''}
            onChange={e => update('value_high', parseFloat(e.target.value) || 0)}
          />
        </>
      )}
      <button className="btn-icon" onClick={onDelete} title="Remove condition">&times;</button>
    </div>
  )
}
