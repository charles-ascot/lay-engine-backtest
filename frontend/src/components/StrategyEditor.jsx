import { useEffect } from 'react'
import RuleCard from './RuleCard'
import { fetchDefaultStrategy, saveStrategy as apiSaveStrategy } from '../api'

export default function StrategyEditor({ strategy, onChange }) {
  // Load default strategy on mount if no strategy loaded
  useEffect(() => {
    if (!strategy) {
      fetchDefaultStrategy().then(data => onChange(data))
    }
  }, [])

  if (!strategy) {
    return (
      <div className="panel">
        <h2>Strategy</h2>
        <div className="loading">Loading strategy...</div>
      </div>
    )
  }

  const updateRule = (index, updated) => {
    const rules = [...strategy.rules]
    rules[index] = updated
    onChange({ ...strategy, rules })
  }

  const deleteRule = (index) => {
    onChange({ ...strategy, rules: strategy.rules.filter((_, i) => i !== index) })
  }

  const addRule = () => {
    const newId = `RULE_${Date.now()}`
    onChange({
      ...strategy,
      rules: [
        ...strategy.rules,
        {
          id: newId,
          name: 'New Rule',
          priority: strategy.rules.length + 1,
          conditions: [{ field: 'fav_lay_odds', operator: 'lt', value: 2.0, value_high: null }],
          actions: [{ target: 'favourite', bet_type: 'LAY', stake: 1.0 }],
          stop_on_match: true,
        },
      ],
    })
  }

  const loadDefault = () => {
    fetchDefaultStrategy().then(data => onChange(data))
  }

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(strategy, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${strategy.id || 'strategy'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importJSON = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.json'
    input.onchange = (e) => {
      const file = e.target.files[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (ev) => {
        try {
          const data = JSON.parse(ev.target.result)
          onChange(data)
        } catch (err) {
          alert('Invalid JSON file')
        }
      }
      reader.readAsText(file)
    }
    input.click()
  }

  const saveToServer = () => {
    apiSaveStrategy(strategy).then(() => {
      alert(`Strategy "${strategy.name}" saved`)
    })
  }

  return (
    <div className="panel">
      <h2>Strategy</h2>

      <div className="strategy-header">
        <input
          value={strategy.name}
          onChange={e => onChange({ ...strategy, name: e.target.value })}
          placeholder="Strategy name"
        />
      </div>

      <div className="scroll-panel">
        {strategy.rules
          .sort((a, b) => a.priority - b.priority)
          .map((rule, i) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              onChange={updated => updateRule(i, updated)}
              onDelete={() => deleteRule(i)}
            />
          ))}

        <button className="add-btn" onClick={addRule} style={{ width: '100%', padding: '8px' }}>
          + Add New Rule
        </button>
      </div>

      <div className="strategy-actions">
        <button className="btn-sm" onClick={loadDefault}>Load Default</button>
        <button className="btn-sm" onClick={importJSON}>Import JSON</button>
        <button className="btn-sm" onClick={exportJSON}>Export JSON</button>
        <button className="btn-sm" onClick={saveToServer}>Save</button>
      </div>
    </div>
  )
}
