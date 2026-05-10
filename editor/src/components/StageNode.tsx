import { Handle, Position, type NodeProps } from "reactflow";
import type { StageData } from "../types";

export default function StageNode({ data, selected }: NodeProps<StageData>) {
  const toolCount = data.tools.length;
  const isTerminal = data.name === "done";

  return (
    <div className={`stage-node ${selected ? "selected" : ""} ${isTerminal ? "terminal" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="stage-node-header">
        <span className="stage-node-name">{data.name}</span>
        {!isTerminal && toolCount > 0 && (
          <span className="stage-node-badge">{toolCount} tools</span>
        )}
      </div>
      {data.description && (
        <div className="stage-node-desc">{data.description}</div>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
