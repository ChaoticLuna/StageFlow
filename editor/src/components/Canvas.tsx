import { useCallback, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  BackgroundVariant,
} from "reactflow";
import StageNode from "./StageNode";
import EdgeEditor from "./EdgeEditor";
import type { StageNode as StageNodeType, EdgeData } from "../types";

const nodeTypes = { stageNode: StageNode };

const initialNodes: StageNodeType[] = [
  {
    id: "pick",
    type: "stageNode",
    position: { x: 80, y: 100 },
    data: { name: "pick", tools: ["Read", "Grep", "Glob"], description: "Pick an issue", on_enter: [], on_exit: [] },
  },
  {
    id: "analyze",
    type: "stageNode",
    position: { x: 320, y: 100 },
    data: { name: "analyze", tools: ["Read", "Grep", "WebSearch"], description: "Analyze root cause", on_enter: [], on_exit: [] },
  },
  {
    id: "plan",
    type: "stageNode",
    position: { x: 560, y: 100 },
    data: { name: "plan", tools: ["Read", "Write"], description: "Plan the fix", on_enter: [], on_exit: [] },
  },
];

const initialEdges: Edge<EdgeData>[] = [
  { id: "pick-analyze", source: "pick", target: "analyze", data: { conditions: [{ type: "always", params: {} }], on_fail: null, description: "Start analysis" } },
  { id: "analyze-plan", source: "analyze", target: "plan", data: { conditions: [{ type: "file_exists", params: { path: "artifacts/analyze/findings.md" } }], on_fail: "analyze", description: "Findings ready" } },
];

interface CanvasProps {
  onNodeSelect: (node: StageNodeType | null) => void;
}

export default function Canvas({ onNodeSelect }: CanvasProps) {
  const [nodes, _setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedEdge, setSelectedEdge] = useState<Edge<EdgeData> | null>(null);

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge({ ...connection, data: { conditions: [], on_fail: null, description: "" } }, eds)),
    [setEdges]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: StageNodeType) => onNodeSelect(node),
    [onNodeSelect]
  );

  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => setSelectedEdge(edge as Edge<EdgeData>),
    []
  );

  const onPaneClick = useCallback(() => {
    onNodeSelect(null);
    setSelectedEdge(null);
  }, [onNodeSelect]);

  return (
    <>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls />
        <MiniMap />
      </ReactFlow>
      {selectedEdge && (
        <EdgeEditor edge={selectedEdge} onClose={() => setSelectedEdge(null)} />
      )}
    </>
  );
}
