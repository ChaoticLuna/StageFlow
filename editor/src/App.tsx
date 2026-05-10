import { useCallback, useState } from "react";
import { ReactFlowProvider } from "reactflow";
import "reactflow/dist/style.css";
import Canvas from "./components/Canvas";
import PropertiesPanel from "./components/PropertiesPanel";
import type { StageNode } from "./types";

export default function App() {
  const [selectedNode, setSelectedNode] = useState<StageNode | null>(null);

  const handleNodeSelect = useCallback((node: StageNode | null) => {
    setSelectedNode(node);
  }, []);

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>StageFlow Editor</h1>
        <span className="app-badge">Visual Workflow Designer</span>
      </header>
      <div className="app-body">
        <ReactFlowProvider>
          <Canvas onNodeSelect={handleNodeSelect} />
        </ReactFlowProvider>
        <PropertiesPanel node={selectedNode} />
      </div>
    </div>
  );
}
