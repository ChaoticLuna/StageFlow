import { useCallback, useState } from "react";
import type { Edge } from "reactflow";
import type { EdgeData, ConditionDef } from "../types";
import {
  CONDITION_TYPES,
  CONDITION_MAP,
  defaultParams,
  type ParamDef,
} from "./conditionDefs";

interface EdgeEditorProps {
  edge: Edge<EdgeData>;
  stageNames: string[];
  onUpdate: (edgeId: string, data: EdgeData) => void;
  onClose: () => void;
}

export default function EdgeEditor({ edge, stageNames, onUpdate, onClose }: EdgeEditorProps) {
  const data = edge.data ?? { conditions: [], on_fail: null, description: "" };
  const existingOnFail = data.on_fail;

  const [description, setDescription] = useState(data.description ?? "");
  const [onFail, setOnFail] = useState(existingOnFail ?? "");
  const [logicMode, setLogicMode] = useState<"all" | "any">(() => {
    if (data.conditions.length === 1 && data.conditions[0].type === "any_of") {
      return "any";
    }
    return "all";
  });

  const [conditions, setConditions] = useState<ConditionDef[]>(() => {
    if (data.conditions.length === 1 && data.conditions[0].type === "any_of") {
      const inner = data.conditions[0].params.conditions;
      if (Array.isArray(inner)) return inner as ConditionDef[];
    }
    return data.conditions.map((c) => ({ ...c, params: { ...c.params } }));
  });

  const addCondition = useCallback(() => {
    const first = CONDITION_TYPES[0];
    setConditions((prev) => [
      ...prev,
      { type: first.type, params: defaultParams(first.type) },
    ]);
  }, []);

  const removeCondition = useCallback((index: number) => {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const updateConditionType = useCallback((index: number, newType: string) => {
    setConditions((prev) =>
      prev.map((c, i) =>
        i === index ? { type: newType, params: defaultParams(newType) } : c
      )
    );
  }, []);

  const updateConditionParam = useCallback(
    (index: number, paramName: string, value: unknown) => {
      setConditions((prev) =>
        prev.map((c, i) =>
          i === index ? { ...c, params: { ...c.params, [paramName]: value } } : c
        )
      );
    },
    []
  );

  const handleSave = useCallback(() => {
    let finalConditions: ConditionDef[];
    if (logicMode === "any" && conditions.length > 1) {
      finalConditions = [
        { type: "any_of", params: { conditions: [...conditions] } },
      ];
    } else {
      finalConditions = conditions.map((c) => ({ ...c }));
    }
    onUpdate(edge.id, {
      conditions: finalConditions,
      on_fail: onFail.trim() || null,
      description: description.trim(),
    });
    onClose();
  }, [edge.id, conditions, logicMode, onFail, description, onUpdate, onClose]);

  const failTargets = stageNames.filter(
    (n) => n !== edge.source && n !== edge.target
  );

  return (
    <div className="edge-editor-overlay" onClick={onClose}>
      <div className="edge-editor-modal" onClick={(e) => e.stopPropagation()}>
        <div className="edge-editor-header">
          <h3>
            {edge.source} &rarr; {edge.target}
          </h3>
          <button className="close-btn" onClick={onClose}>
            &times;
          </button>
        </div>
        <div className="edge-editor-body">
          <div className="prop-group">
            <label>Description</label>
            <input
              className="prop-input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe this transition..."
            />
          </div>

          <div className="prop-group">
            <div className="hook-header">
              <label>
                Conditions ({conditions.length})
              </label>
              <div className="edge-editor-actions">
                <LogicToggle mode={logicMode} onChange={setLogicMode} />
                <button className="add-btn small" onClick={addCondition}>
                  + Add
                </button>
              </div>
            </div>
            <p className="logic-hint">
              {logicMode === "all"
                ? "ALL conditions must pass for the transition to fire."
                : "ANY condition can pass for the transition to fire."}
            </p>
            {conditions.length === 0 ? (
              <p className="empty-state hint">
                No conditions. This is equivalent to "always" — the transition
                will always fire.
              </p>
            ) : (
              <ul className="condition-edit-list">
                {conditions.map((c, i) => (
                  <ConditionEditor
                    key={i}
                    index={i}
                    condition={c}
                    onChangeType={(t) => updateConditionType(i, t)}
                    onChangeParam={(name, val) =>
                      updateConditionParam(i, name, val)
                    }
                    onRemove={() => removeCondition(i)}
                  />
                ))}
              </ul>
            )}
          </div>

          <div className="prop-group">
            <label>On Failure Target</label>
            <select
              className="prop-input"
              value={onFail}
              onChange={(e) => setOnFail(e.target.value)}
            >
              <option value="">None — block transition on failure</option>
              {edge.source !== onFail && onFail && !failTargets.includes(onFail) && (
                <option value={onFail}>{onFail} (current)</option>
              )}
              {failTargets.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <p className="logic-hint">
              If conditions fail, the engine will try to transition here instead.
            </p>
          </div>

          <div className="edge-editor-footer">
            <button className="add-btn" onClick={handleSave}>
              Save Changes
            </button>
            <button className="toolbar-btn cancel-btn" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function LogicToggle({
  mode,
  onChange,
}: {
  mode: "all" | "any";
  onChange: (m: "all" | "any") => void;
}) {
  return (
    <div className="logic-toggle">
      <button
        className={`logic-option ${mode === "all" ? "active" : ""}`}
        onClick={() => onChange("all")}
      >
        AND
      </button>
      <button
        className={`logic-option ${mode === "any" ? "active" : ""}`}
        onClick={() => onChange("any")}
      >
        OR
      </button>
    </div>
  );
}

function ConditionEditor({
  index,
  condition,
  onChangeType,
  onChangeParam,
  onRemove,
}: {
  index: number;
  condition: ConditionDef;
  onChangeType: (type: string) => void;
  onChangeParam: (name: string, value: unknown) => void;
  onRemove: () => void;
}) {
  const def = CONDITION_MAP.get(condition.type);
  const params = def?.params ?? [];

  return (
    <li className="condition-edit-item">
      <div className="condition-edit-header">
        <span className="condition-ordinal">#{index + 1}</span>
        <select
          className="prop-input condition-type-select"
          value={condition.type}
          onChange={(e) => onChangeType(e.target.value)}
        >
          {CONDITION_TYPES.map((ct) => (
            <option key={ct.type} value={ct.type}>
              {ct.label} ({ct.type})
            </option>
          ))}
        </select>
        <button
          className="hook-remove condition-remove"
          onClick={onRemove}
          title="Remove condition"
        >
          &times;
        </button>
      </div>
      <p className="condition-desc">{def?.description ?? ""}</p>
      {params.length > 0 && (
        <div className="param-form">
          {params.map((p) => (
            <ParamInput
              key={p.name}
              param={p}
              value={condition.params[p.name]}
              onChange={(val) => onChangeParam(p.name, val)}
            />
          ))}
        </div>
      )}
    </li>
  );
}

function ParamInput({
  param,
  value,
  onChange,
}: {
  param: ParamDef;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  if (param.type === "select" && param.options) {
    return (
      <div className="param-field">
        <label className="param-label">{param.label}</label>
        <select
          className="prop-input"
          value={String(value ?? param.default ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {param.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (param.type === "number") {
    return (
      <div className="param-field">
        <label className="param-label">{param.label}</label>
        <input
          className="prop-input"
          type="number"
          value={value != null ? String(value) : ""}
          placeholder={param.placeholder}
          onChange={(e) => {
            const v = e.target.value;
            onChange(v === "" ? undefined : Number(v));
          }}
        />
      </div>
    );
  }

  if (param.type === "textarea" || param.type === "json") {
    return (
      <div className="param-field">
        <label className="param-label">{param.label}</label>
        <textarea
          className="prop-input mono"
          value={typeof value === "string" ? value : JSON.stringify(value, null, 2)}
          placeholder={param.placeholder}
          rows={param.type === "json" ? 3 : 2}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    );
  }

  return (
    <div className="param-field">
      <label className="param-label">{param.label}</label>
      <input
        className="prop-input"
        type="text"
        value={typeof value === "string" ? value : ""}
        placeholder={param.placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
