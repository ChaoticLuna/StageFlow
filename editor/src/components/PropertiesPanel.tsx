import { useCallback, useState } from "react";
import type { StageNode, StageData, HookDef } from "../types";

interface PropertiesPanelProps {
  node: StageNode | null;
  onNodeUpdate: (nodeId: string, data: StageData) => void;
}

export default function PropertiesPanel({ node, onNodeUpdate }: PropertiesPanelProps) {
  if (!node) {
    return (
      <div className="properties-panel">
        <h2>Properties</h2>
        <p className="empty-state">Select a node to edit its properties.</p>
      </div>
    );
  }

  return (
    <div className="properties-panel">
      <NodeEditor node={node} onNodeUpdate={onNodeUpdate} />
    </div>
  );
}

function NodeEditor({ node, onNodeUpdate }: PropertiesPanelProps & { node: StageNode }) {
  const data = node.data;
  const isTerminal = data.isTerminal === true;

  const update = useCallback(
    (patch: Partial<StageData>) => {
      onNodeUpdate(node.id, { ...data, ...patch });
    },
    [node.id, data, onNodeUpdate]
  );

  return (
    <>
      <h2>{isTerminal ? `${data.name} (terminal)` : data.name}</h2>

      <div className="prop-group">
        <label>Stage ID</label>
        <input
          className="prop-input mono"
          value={data.name}
          onChange={(e) => update({ name: e.target.value })}
        />
      </div>

      <div className="prop-group">
        <label>Description</label>
        <input
          className="prop-input"
          value={data.description}
          onChange={(e) => update({ description: e.target.value })}
          placeholder="Describe this stage..."
        />
      </div>

      <ToolEditor tools={data.tools} update={update} />

      <HookEditor
        label="on_enter"
        hooks={data.on_enter}
        onChange={(hooks) => update({ on_enter: hooks })}
      />

      <HookEditor
        label="on_exit"
        hooks={data.on_exit}
        onChange={(hooks) => update({ on_exit: hooks })}
      />
    </>
  );
}

function ToolEditor({
  tools,
  update,
}: {
  tools: string[];
  update: (patch: Partial<StageData>) => void;
}) {
  const [input, setInput] = useState("");

  const addTool = useCallback(() => {
    const trimmed = input.trim();
    if (trimmed && !tools.includes(trimmed)) {
      update({ tools: [...tools, trimmed] });
    }
    setInput("");
  }, [input, tools, update]);

  const removeTool = useCallback(
    (index: number) => {
      update({ tools: tools.filter((_, i) => i !== index) });
    },
    [tools, update]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        addTool();
      }
    },
    [addTool]
  );

  return (
    <div className="prop-group">
      <label>Tools ({tools.length})</label>
      <div className="tool-editor">
        {tools.length > 0 ? (
          <ul className="tool-list editable">
            {tools.map((t, i) => (
              <li key={i} className="tool-tag editable">
                <code>{t}</code>
                <button className="tool-remove" onClick={() => removeTool(i)}>
                  &times;
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty-state hint">
            {tools.length === 0
              ? "No tools listed. Empty = all tools allowed in this stage."
              : ""}
          </p>
        )}
        <div className="tool-add-row">
          <input
            className="prop-input tool-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g., Bash(git *)"
          />
          <button className="add-btn" onClick={addTool} disabled={!input.trim()}>
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

function HookEditor({
  label,
  hooks,
  onChange,
}: {
  label: string;
  hooks: HookDef[];
  onChange: (hooks: HookDef[]) => void;
}) {
  const addHook = useCallback(() => {
    onChange([...hooks, { shell: "" }]);
  }, [hooks, onChange]);

  const removeHook = useCallback(
    (index: number) => {
      onChange(hooks.filter((_, i) => i !== index));
    },
    [hooks, onChange]
  );

  const updateHook = useCallback(
    (index: number, patch: Partial<HookDef>) => {
      onChange(hooks.map((h, i) => (i === index ? { ...h, ...patch } : h)));
    },
    [hooks, onChange]
  );

  const toggleHookKind = useCallback(
    (index: number) => {
      const current = hooks[index];
      const val = current.shell ?? current.python ?? "";
      if ("shell" in current) {
        onChange(hooks.map((h, i) => (i === index ? { python: val } : h)));
      } else {
        onChange(hooks.map((h, i) => (i === index ? { shell: val } : h)));
      }
    },
    [hooks, onChange]
  );

  return (
    <div className="prop-group">
      <div className="hook-header">
        <label>
          {label} hooks ({hooks.length})
        </label>
        <button className="add-btn small" onClick={addHook}>
          + Add
        </button>
      </div>
      {hooks.length === 0 ? (
        <p className="empty-state hint">No {label} hooks defined.</p>
      ) : (
        <ul className="hook-list">
          {hooks.map((hook, i) => {
            const kind = "shell" in hook ? "shell" : "python";
            const value = hook.shell ?? hook.python ?? "";
            return (
              <li key={i} className="hook-item">
                <div className="hook-row">
                  <button
                    className={`hook-kind-toggle ${kind}`}
                    onClick={() => toggleHookKind(i)}
                    title="Click to toggle shell/python"
                  >
                    {kind}
                  </button>
                  <button className="hook-remove" onClick={() => removeHook(i)}>
                    &times;
                  </button>
                </div>
                {kind === "shell" ? (
                  <input
                    className="prop-input mono hook-value"
                    value={value}
                    onChange={(e) => updateHook(i, { shell: e.target.value })}
                    placeholder="echo hello"
                  />
                ) : (
                  <textarea
                    className="prop-input mono hook-value"
                    value={value}
                    onChange={(e) => updateHook(i, { python: e.target.value })}
                    placeholder="sm.set_var('key', True)"
                    rows={2}
                  />
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
