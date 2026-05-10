import type { Edge } from "reactflow";
import type { EdgeData } from "../types";

interface EdgeEditorProps {
  edge: Edge<EdgeData>;
  onClose: () => void;
}

export default function EdgeEditor({ edge, onClose }: EdgeEditorProps) {
  const conditions = edge.data?.conditions ?? [];

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
          <h4>Conditions ({conditions.length})</h4>
          {conditions.length === 0 ? (
            <p className="empty-state">No conditions. Equivalent to "always".</p>
          ) : (
            <ul className="condition-list">
              {conditions.map((c, i) => (
                <li key={i} className="condition-item">
                  <code>{c.type}</code>
                </li>
              ))}
            </ul>
          )}
          {edge.data?.on_fail && (
            <p className="on-fail">
              On failure: <strong>{edge.data.on_fail}</strong>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
