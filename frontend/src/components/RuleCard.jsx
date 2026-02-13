import ConditionRow from './ConditionRow'
import ActionRow from './ActionRow'

export default function RuleCard({ rule, onChange, onDelete }) {
  const update = (key, val) => {
    onChange({ ...rule, [key]: val })
  }

  const updateCondition = (index, updated) => {
    const conditions = [...rule.conditions]
    conditions[index] = updated
    update('conditions', conditions)
  }

  const deleteCondition = (index) => {
    update('conditions', rule.conditions.filter((_, i) => i !== index))
  }

  const addCondition = () => {
    update('conditions', [
      ...rule.conditions,
      { field: 'fav_lay_odds', operator: 'lt', value: 2.0, value_high: null },
    ])
  }

  const updateAction = (index, updated) => {
    const actions = [...rule.actions]
    actions[index] = updated
    update('actions', actions)
  }

  const deleteAction = (index) => {
    update('actions', rule.actions.filter((_, i) => i !== index))
  }

  const addAction = () => {
    update('actions', [
      ...rule.actions,
      { target: 'favourite', bet_type: 'LAY', stake: 1.0 },
    ])
  }

  return (
    <div className="rule-card">
      <div className="rule-header">
        <input
          type="text"
          value={rule.name}
          onChange={e => update('name', e.target.value)}
          placeholder="Rule name"
        />
        <label>
          P:
          <input
            type="number"
            value={rule.priority}
            onChange={e => update('priority', parseInt(e.target.value) || 1)}
            min="1"
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={rule.stop_on_match}
            onChange={e => update('stop_on_match', e.target.checked)}
          />
          Stop
        </label>
        <button className="btn-icon" onClick={onDelete} title="Delete rule">&times;</button>
      </div>

      <div className="section-label">IF all of:</div>
      {rule.conditions.map((c, i) => (
        <ConditionRow
          key={i}
          condition={c}
          onChange={updated => updateCondition(i, updated)}
          onDelete={() => deleteCondition(i)}
        />
      ))}
      <button className="add-btn" onClick={addCondition}>+ condition</button>

      <div className="section-label">THEN:</div>
      {rule.actions.map((a, i) => (
        <ActionRow
          key={i}
          action={a}
          onChange={updated => updateAction(i, updated)}
          onDelete={() => deleteAction(i)}
        />
      ))}
      <button className="add-btn" onClick={addAction}>+ action</button>
    </div>
  )
}
