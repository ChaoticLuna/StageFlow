import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
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

export interface CanvasHandle {
  updateNodeData: (nodeId: string, data: StageData) => void;
  updateEdgeData: (edgeId: string, data: EdgeData) => void;
  getNodes: () => StageNodeType[];
  getEdges: () => Edge<EdgeData>[];
  getStageNames: () => string[];
  loadFromYaml: (yamlStr: string) => boolean;
  exportToYaml: () => string;
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
  { id: "analyze-plan", source: "analyze", target: "plan", data: { conditions: [{ type: "file_exists", params: { path: "artifacts/runs/{{var.run_id}}/analyze/findings.md" } }], on_fail: "analyze", description: "Findings ready" } },
  { id: "plan-done", source: "plan", target: "done", data: { conditions: [{ type: "file_exists", params: { path: "artifacts/runs/{{var.run_id}}/plan/plan.md" } }], on_fail: "plan", description: "Plan delivered" } },
];

interface CanvasProps {
  onNodeSelect: (node: StageNodeType | null) => void;
}

interface Snapshot {
  nodes: StageNodeType[];
  edges: Edge<EdgeData>[];
  counter: number;
}

const Canvas = forwardRef<CanvasHandle, CanvasProps>(function Canvas(
  { onNodeSelect },
  ref
) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [selectedEdge, setSelectedEdge] = useState<Edge<EdgeData> | null>(null);
  const [highlightedEdgeId, setHighlightedEdgeId] = useState<string | null>(null);
  const [mermaidOpen, setMermaidOpen] = useState(false);
  const [undoToast, setUndoToast] = useState(false);
  const reactFlow = useReactFlow();

  const undoStack = useRef<Snapshot[]>([]);
  const MAX_UNDO = 50;

  const takeSnapshot = useCallback((): Snapshot => ({
    nodes: nodes as StageNodeType[],
    edges: edges as Edge<EdgeData>[],
    counter: _nodeCounter,
  }), [nodes, edges]);

  const pushUndo = useCallback(() => {
    undoStack.current.push(takeSnapshot());
    if (undoStack.current.length > MAX_UNDO) {
      undoStack.current.shift();
    }
  }, [takeSnapshot]);

  const popUndo = useCallback(() => {
    const snap = undoStack.current.pop();
    if (!snap) return;
    setNodes(snap.nodes);
    setEdges(snap.edges);
    _nodeCounter = snap.counter;
    setUndoToast(true);
    setTimeout(() => setUndoToast(false), 1200);
  }, [setNodes, setEdges]);

  useImperativeHandle(ref, () => ({
    updateNodeData(nodeId: string, data: StageData) {
      pushUndo();
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data: { ...data } } : n)));
    },
    updateEdgeData(edgeId: string, data: EdgeData) {
      pushUndo();
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
    loadFromYaml(yamlStr: string) {
      const result = importFromYaml(yamlStr);
      if ("error" in result) {
        console.error("Failed to load project config:", result.error);
        return false;
      }
      _nodeCounter = result.nodes.length;
      setNodes(result.nodes);
      setEdges(result.edges);
      setHighlightedEdgeId(null);
      setSelectedEdge(null);
      return true;
    },
    exportToYaml() {
      return exportToYaml(nodes as StageNodeType[], edges as Edge<EdgeData>[]);
    },
  }), [nodes, edges, setNodes, setEdges, pushUndo]);

  const labeledEdges = useMemo(
    () =>
      edges.map((e) => ({
        ...e,
        selected: e.id === highlightedEdgeId,
        animated: e.id === highlightedEdgeId ? true : e.animated,
        style: {
          ...e.style,
          ...(e.id === highlightedEdgeId
            ? { stroke: "#4f8fe8", strokeWidth: 3 }
            : {}),
        },
        label: formatConditionSummary(e.data?.conditions ?? []),
        labelStyle: {
          fill: e.id === highlightedEdgeId ? "#4f8fe8" : "var(--text-secondary, #555)",
          fontSize: 10,
          fontWeight: e.id === highlightedEdgeId ? 700 : 500,
        },
        labelBgStyle: { fill: "var(--bg-toolbar, #fff)", fillOpacity: 0.9 },
        labelBgPadding: [4, 3] as [number, number],
        labelBgBorderRadius: 3,
      })),
    [edges, highlightedEdgeId]
  );

  useEffect(() => {
    if (highlightedEdgeId && !edges.some((e) => e.id === highlightedEdgeId)) {
      setHighlightedEdgeId(null);
      setSelectedEdge(null);
    }
  }, [edges, highlightedEdgeId]);

  const stageNames = useMemo(
    () => nodes.map((n) => n.data?.name ?? n.id),
    [nodes]
  );

  const terminalNodeIds = useMemo(() => {
    const sources = new Set(edges.map((e) => e.source));
    return new Set(nodes.filter((n) => !sources.has(n.id)).map((n) => n.id));
  }, [nodes, edges]);

  const displayNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        data: {
          ...n.data,
          isTerminal: terminalNodeIds.has(n.id),
        },
      })),
    [nodes, terminalNodeIds]
  );

  const handleEdgeUpdate = useCallback(
    (edgeId: string, data: EdgeData) => {
      pushUndo();
      setEdges((eds) =>
        eds.map((e) => (e.id === edgeId ? { ...e, data: { ...data } } : e))
      );
      setSelectedEdge(null);
      setHighlightedEdgeId(null);
    },
    [setEdges, pushUndo]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      pushUndo();
      setEdges((eds) =>
        addEdge(
          { ...connection, data: { conditions: [], on_fail: null, description: "" } },
          eds
        )
      );
    },
    [setEdges, pushUndo]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setHighlightedEdgeId(null);
      onNodeSelect(node as StageNodeType);
    },
    [onNodeSelect]
  );

  const onEdgeClick = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      event.stopPropagation();
      onNodeSelect(null);
      if (highlightedEdgeId === edge.id) {
        setSelectedEdge(edge as Edge<EdgeData>);
        return;
      }
      setHighlightedEdgeId(edge.id);
      setSelectedEdge(null);
    },
    [highlightedEdgeId, onNodeSelect]
  );

  const onPaneClick = useCallback(() => {
    onNodeSelect(null);
    setSelectedEdge(null);
    setHighlightedEdgeId(null);
  }, [onNodeSelect]);

  const addStage = useCallback(() => {
    pushUndo();
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
  }, [setNodes, onNodeSelect, reactFlow, pushUndo]);

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
        pushUndo();
        setNodes(result.nodes);
        setEdges(result.edges);
        _nodeCounter = result.nodes.length;
        onNodeSelect(null);
        setSelectedEdge(null);
        setHighlightedEdgeId(null);
      };
      reader.readAsText(file);
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    [setNodes, setEdges, onNodeSelect, pushUndo]
  );

  const autoLayout = useCallback(() => {
    pushUndo();
    const currentNodes = reactFlow.getNodes() as StageNodeType[];
    const currentEdges = reactFlow.getEdges() as Edge<EdgeData>[];
    const outEdges = new Map<string, string[]>();
    const nodeIds = new Set(currentNodes.map((n) => n.id));
    for (const n of currentNodes) {
      outEdges.set(n.id, []);
    }
    for (const e of currentEdges) {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
      const outs = outEdges.get(e.source) ?? [];
      outs.push(e.target);
      outEdges.set(e.source, outs);
    }

    const layers = new Map<string, number>();
    const visiting = new Set<string>();
    const maxDepth = Math.max(currentNodes.length, 1);

    const assignLayer = (id: string, layer: number) => {
      if (visiting.has(id) || layer > maxDepth) return;
      const prev = layers.get(id);
      if (prev !== undefined && prev >= layer) return;
      layers.set(id, layer);
      visiting.add(id);
      for (const nextId of outEdges.get(id) ?? []) {
        assignLayer(nextId, layer + 1);
      }
      visiting.delete(id);
    };

    const targets = new Set(currentEdges.map((e) => e.target));
    const roots = currentNodes.filter((n) => !targets.has(n.id));
    const starts = roots.length > 0 ? roots : currentNodes;
    for (const node of starts) {
      assignLayer(node.id, 0);
    }

    const fallbackLayer = Math.max(0, ...Array.from(layers.values())) + 1;
    for (const node of currentNodes) {
      if (!layers.has(node.id)) {
        layers.set(node.id, fallbackLayer);
      }
    }

    const layerNodes = new Map<number, string[]>();
    for (const [id, layer] of layers) {
      const arr = layerNodes.get(layer) ?? [];
      arr.push(id);
      layerNodes.set(layer, arr);
    }

    const X_GAP = 240;
    const Y_GAP = 100;
    const updated = currentNodes.map((n) => {
      const layer = layers.get(n.id) ?? 0;
      const siblings = layerNodes.get(layer) ?? [n.id];
      const idx = siblings.indexOf(n.id);
      return {
        ...n,
        position: {
          x: 80 + layer * X_GAP,
          y: 80 + (idx >= 0 ? idx : 0) * Y_GAP,
        },
      };
    });
    setNodes(updated);
  }, [reactFlow, setNodes, pushUndo]);

  const mermaidCode = useMemo(() => {
    const lines: string[] = ["flowchart LR"];
    const nameSet = new Set<string>();
    for (const n of nodes) {
      const name = n.data?.name ?? n.id;
      nameSet.add(name);
      const label = n.data?.description
        ? `${name}: ${n.data.description}`
        : name;
      const safeLabel = label.replace(/"/g, "'");
      lines.push(`  ${n.id}["${safeLabel}"]`);
    }
    for (const e of edges) {
      const label = formatConditionSummary(e.data?.conditions ?? []);
      const safeLabel = label.replace(/"/g, "'");
      const hasLabel = label && label !== "always";
      const arrow = hasLabel ? `-->|"${safeLabel}"|` : "-->";
      lines.push(`  ${e.source} ${arrow} ${e.target}`);
    }
    return lines.join("\n");
  }, [nodes, edges]);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "s") {
        event.preventDefault();
        handleExport();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "z") {
        event.preventDefault();
        popUndo();
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        const sel = reactFlow.getNodes().find((n) => n.selected);
        if (sel) {
          pushUndo();
          setNodes((nds) => nds.filter((n) => n.id !== sel.id));
          setEdges((eds) => eds.filter((e) => e.source !== sel.id && e.target !== sel.id));
          onNodeSelect(null);
        }
      }
    },
    [setNodes, setEdges, onNodeSelect, reactFlow, handleExport, popUndo, pushUndo]
  );

  const handleCopyMermaid = useCallback(() => {
    navigator.clipboard.writeText(mermaidCode).catch(() => {});
  }, [mermaidCode]);

  const activeNodes = nodes.filter((n) => !terminalNodeIds.has(n.id));
  const terminalNodes = nodes.filter((n) => terminalNodeIds.has(n.id));

  return (
    <div className="canvas-wrapper" onKeyDown={onKeyDown} tabIndex={0}>
      <div className="canvas-toolbar">
        <button className="toolbar-btn add-stage-btn" onClick={addStage} title="Add a new stage">
          <span className="btn-icon">+</span>
          Add Stage
        </button>
        <button className="toolbar-btn" onClick={handleExport} title="Export canvas to stages.yaml (Ctrl+S)">
          &darr; Export YAML
        </button>
        <button className="toolbar-btn" onClick={handleImport} title="Import stages.yaml into canvas">
          &uarr; Import YAML
        </button>
        <span className="toolbar-separator" />
        <button className="toolbar-btn" onClick={autoLayout} title="Auto-arrange nodes in layered layout">
          &#9633; Auto Layout
        </button>
        <button className="toolbar-btn" onClick={() => setMermaidOpen(true)} title="Show Mermaid flowchart preview">
          &#9654; Mermaid
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
        nodes={displayNodes}
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
            return node.data?.isTerminal === true ? "#607d8b" : "#1565c0";
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
      {mermaidOpen && (
        <div className="edge-editor-overlay" onClick={() => setMermaidOpen(false)}>
          <div className="edge-editor-modal mermaid-modal" onClick={(e) => e.stopPropagation()}>
            <div className="edge-editor-header">
              <h3>Mermaid Preview</h3>
              <button className="close-btn" onClick={() => setMermaidOpen(false)}>
                &times;
              </button>
            </div>
            <div className="mermaid-body">
              <pre className="mermaid-code">{mermaidCode}</pre>
            </div>
            <div className="mermaid-footer">
              <button className="add-btn" onClick={handleCopyMermaid}>
                Copy to Clipboard
              </button>
              <button
                className="toolbar-btn cancel-btn"
                onClick={() => setMermaidOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      {undoToast && (
        <div className={`undo-toast${undoToast ? "" : " fade"}`}>Undo (Ctrl+Z)</div>
      )}
    </div>
  );
});

export default Canvas;
