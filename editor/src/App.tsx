import { useCallback, useRef, useState } from "react";
import { ReactFlowProvider } from "reactflow";
import "reactflow/dist/style.css";
import Canvas from "./components/Canvas";
import type { CanvasHandle } from "./components/Canvas";
import PropertiesPanel from "./components/PropertiesPanel";
import type { StageNode, StageData } from "./types";

export default function App() {
  const [selectedNode, setSelectedNode] = useState<StageNode | null>(null);
  const canvasRef = useRef<CanvasHandle>(null);

  const handleNodeSelect = useCallback((node: StageNode | null) => {
    setSelectedNode(node);
  }, []);

  const handleNodeUpdate = useCallback((nodeId: string, data: StageData) => {
    canvasRef.current?.updateNodeData(nodeId, data);
    setSelectedNode((prev) =>
      prev?.id === nodeId ? { ...prev, data: { ...data } } : prev
    );
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>StageFlow Editor</h1>
        <span className="app-badge">Visual Workflow Designer</span>
      </header>
      <div className="app-body">
        <ReactFlowProvider>
          <Canvas ref={canvasRef} onNodeSelect={handleNodeSelect} />
        </ReactFlowProvider>
        <PropertiesPanel
          node={selectedNode}
          onNodeUpdate={handleNodeUpdate}
        />
      </div>
    </div>
  );
}
