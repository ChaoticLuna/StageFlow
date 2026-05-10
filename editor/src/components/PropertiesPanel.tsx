import type { StageNode } from "../types";

interface PropertiesPanelProps {
  node: StageNode | null;
}

export default function PropertiesPanel({ node }: PropertiesPanelProps) {
  if (!node) {
    return (
      <div className="properties-panel">
        <h2>Properties</h2>
        <p className="empty-state">Select a node to view its properties.</p>
      </div>
    );
  }

  const data = node.data;

  return (
    <div className="properties-panel">
      <h2>{data.name}</h2>

      <div className="prop-group">
        <label>Description</label>
        <p>{data.description || "(none)"}</p>
      </div>

      <div className="prop-group">
        <label>Tools ({data.tools.length})</label>
        {data.tools.length > 0 ? (
          <ul className="tool-list">
            {data.tools.map((t, i) => (
              <li key={i} className="tool-tag">{t}</li>
            ))}
          </ul>
        ) : (
          <p className="empty-state">All tools allowed</p>
        )}
      </div>

      <div className="prop-group">
        <label>on_enter hooks ({data.on_enter.length})</label>
        {data.on_enter.length === 0 && <p className="empty-state">None</p>}
      </div>

      <div className="prop-group">
        <label>on_exit hooks ({data.on_exit.length})</label>
        {data.on_exit.length === 0 && <p className="empty-state">None</p>}
      </div>
    </div>
  );
}
