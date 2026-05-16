import { useCallback, useEffect, useRef, useState } from "react";
import { ReactFlowProvider } from "reactflow";
import "reactflow/dist/style.css";
import Canvas from "./components/Canvas";
import type { CanvasHandle } from "./components/Canvas";
import PropertiesPanel from "./components/PropertiesPanel";
import type { StageNode, StageData } from "./types";
import {
  fetchProjectConfig,
  saveProjectConfig,
  ApiError,
  type ProjectConfig,
} from "./utils/api";

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

type SaveState = "idle" | "saving" | "saved" | "error" | "blocked";

export default function App() {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [selectedNode, setSelectedNode] = useState<StageNode | null>(null);
  const canvasRef = useRef<CanvasHandle>(null);

  // Project state
  const [projectInfo, setProjectInfo] = useState<ProjectConfig | null>(null);
  const [projectLoadError, setProjectLoadError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveMessage, setSaveMessage] = useState<string>("");

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Auto-load project config on mount
  useEffect(() => {
    let cancelled = false;
    fetchProjectConfig()
      .then((config) => {
        if (cancelled) return;
        setProjectInfo(config);
        setProjectLoadError(null);
        if (config.yaml) {
          canvasRef.current?.loadFromYaml(config.yaml);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 400) {
          // No project found — use default demo data silently
          setProjectLoadError(null);
        } else if (err instanceof ApiError && err.status === 404) {
          setProjectLoadError("Project config file not found.");
        } else {
          setProjectLoadError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => { cancelled = true; };
  }, []);

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

  const handleSave = useCallback(async () => {
    const yaml = canvasRef.current?.exportToYaml();
    if (yaml === undefined) return;

    setSaveState("saving");
    setSaveMessage("");

    try {
      const result = await saveProjectConfig(yaml);
      setSaveState("saved");
      setSaveMessage(result.message);
      setTimeout(() => {
        setSaveState((s) => (s === "saved" ? "idle" : s));
      }, 4000);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setSaveState("blocked");
          setSaveMessage(err.message);
        } else {
          setSaveState("error");
          setSaveMessage(err.message);
        }
      } else {
        setSaveState("error");
        setSaveMessage(
          err instanceof Error ? err.message : "Save failed"
        );
      }
    }
  }, []);

  const saveAllowed = projectInfo?.save_allowed !== false;

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>StageFlow Editor</h1>
        <span className="app-badge">Visual Workflow Designer</span>
        <div className="app-header-spacer" />
        {projectInfo && (
          <span className="app-project-path" title={projectInfo.config_path}>
            {projectInfo.project_root}
          </span>
        )}
        <button
          className={`toolbar-btn save-btn${saveState === "saving" ? " saving" : ""}`}
          onClick={handleSave}
          disabled={!saveAllowed || saveState === "saving"}
          title={
            !saveAllowed
              ? "Save blocked: complete or reset the active run first"
              : "Save workflow to project config"
          }
        >
          {saveState === "saving" ? "Saving..." : "Save"}
        </button>
        {saveState !== "idle" && (
          <span
            className={`app-save-status save-status-${saveState}`}
            role="status"
          >
            {saveState === "saving" && "Saving..."}
            {saveState === "saved" && saveMessage}
            {saveState === "error" && saveMessage}
            {saveState === "blocked" && saveMessage}
          </span>
        )}
        <button
          className="theme-toggle"
          onClick={toggleTheme}
          title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        >
          {theme === "light" ? "☾" : "☀"}
        </button>
      </header>
      {projectLoadError && (
        <div className="app-load-error" role="alert">
          {projectLoadError}
        </div>
      )}
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
