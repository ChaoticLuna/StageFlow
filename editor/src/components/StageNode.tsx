import { Handle, Position, type NodeProps } from "reactflow";
import type { StageData } from "../types";

export default function StageNode({ data, selected }: NodeProps<StageData>) {
  const toolCount = data.tools.length;
  const isTerminal = data.isTerminal === true;
  const unlimitedTools = data.tools.length === 0 && !isTerminal;

  return (
    <div
      className={`stage-node${selected ? " selected" : ""}${isTerminal ? " terminal" : ""}`}
    >
      <Handle type="target" position={Position.Left} />

      <div className="stage-node-header">
        <span className={`stage-icon${isTerminal ? " terminal-icon" : ""}`}>
          {isTerminal ? "✔" : "●"}
        </span>
        <span className="stage-node-name">{data.name}</span>
      </div>

      {data.description && (
        <div className="stage-node-desc">{data.description}</div>
      )}

      <div className="stage-node-footer">
        {isTerminal ? (
          <span className="stage-badge terminal-badge">terminal</span>
        ) : unlimitedTools ? (
          <span className="stage-badge all-badge">all tools</span>
        ) : toolCount > 0 ? (
          <span className="stage-badge">{toolCount} tool{toolCount !== 1 ? "s" : ""}</span>
        ) : (
          <span className="stage-badge empty-badge">0 tools</span>
        )}
        {data.on_enter.length > 0 && (
          <span className="stage-badge hook-badge" title={`${data.on_enter.length} on_enter hook(s)`}>
            {data.on_enter.length} in
          </span>
        )}
        {data.on_exit.length > 0 && (
          <span className="stage-badge hook-badge" title={`${data.on_exit.length} on_exit hook(s)`}>
            {data.on_exit.length} out
          </span>
        )}
      </div>

      <Handle type="source" position={Position.Right} />
    </div>
  );
}
