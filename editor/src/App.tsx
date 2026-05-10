import { useCallback, useEffect, useRef, useState } from "react";
import { ReactFlowProvider } from "reactflow";
import "reactflow/dist/style.css";
import Canvas from "./components/Canvas";
import type { CanvasHandle } from "./components/Canvas";
import PropertiesPanel from "./components/PropertiesPanel";
import type { StageNode, StageData } from "./types";

type Theme = "light" | "dark";

function loadTheme(): Theme {
  try {
    const stored = localStorage.getItem("stageflow-theme");
    if (stored === "dark" || stored === "light") return stored;
  } catch {
    // localStorage unavailable
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(t: Theme) {
  document.documentElement.setAttribute("data-theme", t);
  try {
    localStorage.setItem("stageflow-theme", t);
  } catch {
    // ignore
  }
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [selectedNode, setSelectedNode] = useState<StageNode | null>(null);
  const canvasRef = useRef<CanvasHandle>(null);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === "light" ? "dark" : "light"));
  }, []);

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
        <div className="app-header-spacer" />
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        >
          {theme === "light" ? "☾" : "☀"}
        </button>
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
