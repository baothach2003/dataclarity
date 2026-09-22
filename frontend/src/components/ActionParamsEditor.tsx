// The params editor for the currently selected action (docs/SPECS.md section
// 4.2 B: "Proposed action ... dropdown + params"). Rendered inline below the
// Action select rather than in a floating popover (design/mockups/Review -
// Edit Action.png shows a popover) — a deliberate simplification for this
// build; see the session notes for the tradeoff.

import {
  CASE_MODE_LABELS,
  CASE_MODES,
  CAST_TARGET_LABELS,
  CAST_TARGETS,
  NEGATIVE_STRATEGIES,
  NEGATIVE_STRATEGY_LABELS,
} from '../domain/transformCatalog.ts'
import { boolParam, mappingParam, numberParam, stringParam } from '../domain/transformParams.ts'
import type { Params, TransformAction } from '../types/contracts.ts'

interface ActionParamsEditorProps {
  action: TransformAction
  params: Params
  onChange: (params: Params) => void
}

export function ActionParamsEditor({ action, params, onChange }: ActionParamsEditorProps) {
  switch (action) {
    case 'impute_constant':
      return (
        <label className="action-params__field">
          Fill with
          <input
            className="text-input"
            type="text"
            value={stringParam(params, 'value')}
            onChange={(event) => {
              onChange({ ...params, value: event.target.value })
            }}
          />
        </label>
      )
    case 'cast_type':
      return (
        <label className="action-params__field">
          Convert to
          <select
            className="select"
            value={stringParam(params, 'target', CAST_TARGETS[0])}
            onChange={(event) => {
              onChange({ ...params, target: event.target.value })
            }}
          >
            {CAST_TARGETS.map((target) => (
              <option key={target} value={target}>
                {CAST_TARGET_LABELS[target]}
              </option>
            ))}
          </select>
        </label>
      )
    case 'normalize_case':
      return (
        <label className="action-params__field">
          Case
          <select
            className="select"
            value={stringParam(params, 'mode', CASE_MODES[0])}
            onChange={(event) => {
              onChange({ ...params, mode: event.target.value })
            }}
          >
            {CASE_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {CASE_MODE_LABELS[mode]}
              </option>
            ))}
          </select>
        </label>
      )
    case 'fix_negative':
      return (
        <label className="action-params__field">
          Negative values
          <select
            className="select"
            value={stringParam(params, 'strategy', NEGATIVE_STRATEGIES[0])}
            onChange={(event) => {
              onChange({ ...params, strategy: event.target.value })
            }}
          >
            {NEGATIVE_STRATEGIES.map((strategy) => (
              <option key={strategy} value={strategy}>
                {NEGATIVE_STRATEGY_LABELS[strategy]}
              </option>
            ))}
          </select>
        </label>
      )
    case 'clip_outliers_iqr':
      return (
        <label className="action-params__field">
          IQR multiplier (k)
          <input
            className="number-input"
            type="number"
            min={0}
            step={0.1}
            value={numberParam(params, 'k', 1.5)}
            onChange={(event) => {
              const k = Number(event.target.value)
              onChange({ ...params, k: Number.isFinite(k) ? k : 0 })
            }}
          />
        </label>
      )
    case 'flag_only':
      return (
        <label className="action-params__field">
          Note (optional)
          <input
            className="text-input"
            type="text"
            value={stringParam(params, 'note')}
            onChange={(event) => {
              onChange({ ...params, note: event.target.value })
            }}
          />
        </label>
      )
    case 'standardize_categories':
      return <MappingEditor mapping={mappingParam(params, 'mapping')} onChange={(mapping) => { onChange({ ...params, mapping }) }} />
    case 'parse_datetime':
      return (
        <div className="action-params__row">
          <label className="action-params__field">
            Format (optional)
            <input
              className="text-input"
              type="text"
              placeholder="e.g. %Y-%m-%d, leave blank to auto-detect"
              value={stringParam(params, 'format')}
              onChange={(event) => {
                const format = event.target.value
                if (format) {
                  onChange({ ...params, format })
                  return
                }
                const rest: Params = {}
                for (const [key, value] of Object.entries(params)) {
                  if (key !== 'format') {
                    rest[key] = value
                  }
                }
                onChange(rest)
              }}
            />
          </label>
          <label className="action-params__checkbox">
            <input
              type="checkbox"
              checked={boolParam(params, 'dayfirst')}
              onChange={(event) => {
                onChange({ ...params, dayfirst: event.target.checked })
              }}
            />
            Day before month
          </label>
        </div>
      )
    case 'impute_median':
    case 'impute_mean':
    case 'impute_mode':
    case 'drop_rows_missing':
    case 'drop_column':
    case 'trim_whitespace':
    case 'remove_exact_duplicates':
    case 'flag_duplicate_keys':
      return null
  }
}

function MappingEditor({
  mapping,
  onChange,
}: {
  mapping: Record<string, string>
  onChange: (mapping: Record<string, string>) => void
}) {
  const entries = Object.entries(mapping)

  function replaceAt(index: number, pair: [string, string]) {
    onChange(Object.fromEntries(entries.map((entry, i) => (i === index ? pair : entry))))
  }

  return (
    <div className="mapping-editor">
      <span className="action-params__field">Merge labels</span>
      {entries.map(([from, to], index) => (
        <div className="mapping-editor__row" key={index}>
          <input
            className="text-input"
            aria-label="From label"
            value={from}
            onChange={(event) => {
              replaceAt(index, [event.target.value, to])
            }}
          />
          <span aria-hidden>&rarr;</span>
          <input
            className="text-input"
            aria-label="To label"
            value={to}
            onChange={(event) => {
              replaceAt(index, [from, event.target.value])
            }}
          />
          <button
            type="button"
            className="link-button"
            onClick={() => {
              onChange(Object.fromEntries(entries.filter((_, i) => i !== index)))
            }}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        className="link-button"
        onClick={() => {
          onChange({ ...mapping, '': '' })
        }}
      >
        + Add merge
      </button>
    </div>
  )
}
