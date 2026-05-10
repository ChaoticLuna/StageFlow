import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  BackgroundVariant,
} from "reactflow";
import StageNode from "./StageNode";
import EdgeEditor from "./EdgeEditor";
import { formatConditionSummary } from "./conditionDefs";
import { exportToYaml, importFromYaml } from "../utils/yaml";
import type { StageNode as StageNodeType, EdgeData, StageData } from "../types";

const nodeTypes = { stageNode: StageNode };

const TERMINAL_STAGES = new Set(["done", "complete", "finished", "end"]);

export interface CanvasHandle {
  updateNodeData: (nodeId: string, data: StageData) => void;
  updateEdgeData: (edgeId: string, data: EdgeData) => void;
  getNodes: () => StageNodeType[];
  getEdges: () => Edge<EdgeData>[];
  getStageNames: () => string[];
}

let _nodeCounter = 0;

function newStageId(): string {
  _nodeCounter += 1;
  return `stage_${_nodeCounter}`;
}

const initialNodes: StageNodeType[] = [
  {
    id: "pick",
    type: "stageNode",
    position: { x: 80, y: 120 },
    data: { name: "pick", tools: ["Read", "Grep", "Glob"], description: "Pick an issue", on_enter: [], on_exit: [] },
  },
  {
    id: "analyze",
    type: "stageNode",
    position: { x: 320, y: 120 },
    data: { name: "analyze", tools: ["Read", "Grep", "WebSearch"], description: "Analyze root cause", on_enter: [], on_exit: [] },
  },
  {
    id: "plan",
    type: "stageNode",
    position: { x: 560, y: 120 },
    data: { name: "plan", tools: ["Read", "Write"], description: "Plan the fix", on_enter: [], on_exit: [] },
  },
  {
    id: "done",
    type: "stageNode",
    position: { x: 800, y: 120 },
    data: { name: "done", tools: [], description: "Work complete", on_enter: [], on_exit: [] },
  },
];

const initialEdges: Edge<EdgeData>[] = [
  { id: "pick-analyze", source: "pick", target: "analyze", data: { conditions: [{ type: "always", params: {} }], on_fail: null, description: "Start analysis" } },
  { id: "analyze-plan", source: "analyze", target: "plan", data: { conditions: [{ type: "file_exists", params: { path: "artifacts/analyze/findings.md" } }], on_fail: "analyze", description: "Findings ready" } },
  { id: "plan-done", source: "plan", target: "done", data: { conditions: [{ type: "file_exists", params: { path: "artifacts/plan/plan.md" } }], on_fail: "plan", description: "Plan delivered" } },
];

interface CanvasProps {
  onNodeSelect: (node: StageNodeType | null) => void;
}

const Canvas = forwardRef<CanvasHandle, CanvasProps>(function Canvas(
  { onNodeSelect },
  ref
) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedEdge, setSelectedEdge] = useState<Edge<EdgeData> | null>(null);
  const reactFlow = useReactFlow();

  useImperativeHandle(ref, () => ({
    updateNodeData(nodeId: string, data: StageData) {
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data: { ...data } } : n)));
    },
    updateEdgeData(edgeId: string, data: EdgeData) {
      setEdges((eds) => eds.map((e) => (e.id === edgeId ? { ...e, data: { ...data } } : e)));
    },
    getNodes() {
      return nodes as StageNodeType[];
    },
    getEdges() {
      return edges as Edge<EdgeData>[];
    },
    getStageNames() {
      return nodes.map((n) => n.data?.name ?? n.id);
    },
  }), [nodes, edges, setNodes, setEdges]);

  const labeledEdges = useMemo(
    () =>
      edges.map((e) => ({
        ...e,
        label: formatConditionSummary(e.data?.conditions ?? []),
        labelStyle: { fill: "#555", fontSize: 10, fontWeight: 500 },
        labelBgStyle: { fill: "#fff", fillOpacity: 0.9 },
        labelBgPadding: [4, 3] as [number, number],
        labelBgBorderRadius: 3,
      })),
    [edges]
  );

  const stageNames = useMemo(
    () => nodes.map((n) => n.data?.name ?? n.id),
    [nodes]
  );

  const handleEdgeUpdate = useCallback(
    (edgeId: string, data: EdgeData) => {
      setEdges((eds) =>
        eds.map((e) => (e.id === edgeId ? { ...e, data: { ...data } } : e))
      );
      setSelectedEdge(null);
    },
    [setEdges]
  );

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((eds) =>
        addEdge(
          { ...connection, data: { conditions: [], on_fail: null, description: "" } },
          eds
        )
      ),
    [setEdges]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onNodeSelect(node as StageNodeType),
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

  const addStage = useCallback(() => {
    const id = newStageId();
    const center = reactFlow.screenToFlowPosition({
      x: window.innerWidth / 2,
      y: window.innerHeight / 3,
    });
    const offsetX = (Math.random() - 0.5) * 160;
    const offsetY = (Math.random() - 0.5) * 120;
    const newNode: StageNodeType = {
      id,
      type: "stageNode",
      position: { x: center.x + offsetX, y: center.y + offsetY },
      data: {
        name: id,
        tools: ["Read", "Write"],
        description: "New stage",
        on_enter: [],
        on_exit: [],
      },
    };
    setNodes((nds) => nds.concat(newNode));
    onNodeSelect(newNode);
  }, [setNodes, onNodeSelect, reactFlow]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExport = useCallback(() => {
    const yamlStr = exportToYaml(nodes as StageNodeType[], edges as Edge<EdgeData>[]);
    const blob = new Blob([yamlStr], { type: "application/x-yaml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "stages.yaml";
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, edges]);

  const handleImport = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const text = reader.result as string;
        const result = importFromYaml(text);
        if ("error" in result) {
          alert(`Import failed: ${result.error}`);
          return;
        }
        setNodes(result.nodes);
        setEdges(result.edges);
        _nodeCounter = result.nodes.length;
        onNodeSelect(null);
        setSelectedEdge(null);
      };
      reader.readAsText(file);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [setNodes, setEdges, onNodeSelect]
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === "Delete" || event.key === "Backspace") {
        const sel = reactFlow.getNodes().find((n) => n.selected);
        if (sel) {
          setNodes((nds) => nds.filter((n) => n.id !== sel.id));
          setEdges((eds) => eds.filter((e) => e.source !== sel.id && e.target !== sel.id));
          onNodeSelect(null);
        }
      }
    },
    [setNodes, setEdges, onNodeSelect, reactFlow]
  );

  const activeNodes = nodes.filter((n) => !TERMINAL_STAGES.has(n.data?.name ?? ""));
  const terminalNodes = nodes.filter((n) => TERMINAL_STAGES.has(n.data?.name ?? ""));

  return (
    <div className="canvas-wrapper" onKeyDown={onKeyDown} tabIndex={0}>
      <div className="canvas-toolbar">
        <button className="toolbar-btn add-stage-btn" onClick={addStage} title="Add a new stage">
          <span className="btn-icon">+</span>
          Add Stage
        </button>
        <button className="toolbar-btn" onClick={handleExport} title="Export canvas to stages.yaml">
          &darr; Export YAML
        </button>
        <button className="toolbar-btn" onClick={handleImport} title="Import stages.yaml into canvas">
          &uarr; Import YAML
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".yaml,.yml"
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
        <span className="toolbar-info">
          {nodes.length} stage{nodes.length !== 1 ? "s" : ""}
          <span className="toolbar-dot active-dot" /> {activeNodes.length} normal
          <span className="toolbar-dot terminal-dot" /> {terminalNodes.length} terminal
        </span>
      </div>
      <ReactFlow
        nodes={nodes}
        edges={labeledEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        deleteKeyCode={["Delete", "Backspace"]}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            const name = node.data?.name ?? "";
            return TERMINAL_STAGES.has(name) ? "#607d8b" : "#1565c0";
          }}
        />
      </ReactFlow>
      {selectedEdge && (
        <EdgeEditor
          edge={selectedEdge}
          stageNames={stageNames}
          onUpdate={handleEdgeUpdate}
          onClose={() => setSelectedEdge(null)}
        />
      )}
    </div>
  );
});

export default Canvas;
