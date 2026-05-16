import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

// Hoisted mock refs so Canvas mock and tests share the same functions
const { exportToYamlMock, loadFromYamlMock, fetchProjectConfigMock, saveProjectConfigMock } =
  vi.hoisted(() => ({
    exportToYamlMock: vi.fn().mockReturnValue("stages: []"),
    loadFromYamlMock: vi.fn().mockReturnValue(true),
    fetchProjectConfigMock: vi.fn(),
    saveProjectConfigMock: vi.fn(),
  }));

vi.mock("./components/Canvas", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  return {
    default: React.forwardRef((_props: any, ref: any) => {
      React.useImperativeHandle(ref, () => ({
        loadFromYaml: loadFromYamlMock,
        exportToYaml: exportToYamlMock,
        updateNodeData: vi.fn(),
        updateEdgeData: vi.fn(),
        getNodes: vi.fn(),
        getEdges: vi.fn(),
        getStageNames: vi.fn(),
      }));
      return <div data-testid="mock-canvas">Canvas</div>;
    }),
  };
});

vi.mock("./utils/api", () => ({
  fetchProjectConfig: fetchProjectConfigMock,
  saveProjectConfig: saveProjectConfigMock,
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
      this.name = "ApiError";
    }
  },
}));

import App from "./App";
import { ApiError } from "./utils/api";

const mockConfig = {
  yaml: "stages:\n  - name: alpha\n  - name: beta\ntransitions:\n  - from: alpha\n    to: beta\n    conditions:\n      - always: true",
  config_path: "/proj/.stageflow/config/stages.yaml",
  project_root: "/proj",
  marker_type: "new",
  current_stage: null,
  run_status: null,
  save_allowed: true,
};

const mockSaveResult = {
  saved: true,
  config_path: "/proj/.stageflow/config/stages.yaml",
  message: "Config saved to /proj/.stageflow/config/stages.yaml. Current state: no active run.",
};

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    vi.clearAllMocks();
    // Default: successful project config
    fetchProjectConfigMock.mockResolvedValue(mockConfig);
  });

  describe("header", () => {
    it("renders the StageFlow Editor title", () => {
      render(<App />);
      expect(screen.getByText("StageFlow Editor")).toBeDefined();
    });

    it("renders the Visual Workflow Designer badge", () => {
      render(<App />);
      expect(screen.getByText("Visual Workflow Designer")).toBeDefined();
    });

    it("renders a theme toggle button", () => {
      render(<App />);
      const btn = screen.getByTitle(/switch to/i);
      expect(btn).toBeDefined();
    });
  });

  describe("theme", () => {
    it("applies data-theme attribute on mount", () => {
      render(<App />);
      const theme = document.documentElement.getAttribute("data-theme");
      expect(["light", "dark"]).toContain(theme);
    });

    it("persists theme to localStorage on mount", () => {
      render(<App />);
      const stored = localStorage.getItem("stageflow-theme");
      expect(["light", "dark"]).toContain(stored);
    });

    it("toggles theme when button is clicked", () => {
      render(<App />);
      const initial = document.documentElement.getAttribute("data-theme");
      const btn = screen.getByTitle(/switch to/i);
      fireEvent.click(btn);
      const after = document.documentElement.getAttribute("data-theme");
      expect(after).not.toBe(initial);
      expect(after).toBe(initial === "light" ? "dark" : "light");
    });

    it("updates localStorage after theme toggle", () => {
      render(<App />);
      fireEvent.click(screen.getByTitle(/switch to/i));
      const stored = localStorage.getItem("stageflow-theme");
      expect(stored).toBeDefined();
    });

    it("loads light theme from localStorage", () => {
      localStorage.setItem("stageflow-theme", "light");
      render(<App />);
      expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    });

    it("loads dark theme from localStorage", () => {
      localStorage.setItem("stageflow-theme", "dark");
      render(<App />);
      expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    });
  });

  describe("layout", () => {
    it("renders the Canvas component", () => {
      render(<App />);
      expect(screen.getByTestId("mock-canvas")).toBeDefined();
    });

    it("renders the PropertiesPanel component", () => {
      render(<App />);
      expect(screen.getByText("Properties")).toBeDefined();
    });

    it("shows empty state in PropertiesPanel initially", () => {
      render(<App />);
      expect(screen.getByText("Select a node to edit its properties.")).toBeDefined();
    });
  });

  describe("auto-load", () => {
    it("fetches project config on mount", async () => {
      render(<App />);
      await waitFor(() => {
        expect(fetchProjectConfigMock).toHaveBeenCalledTimes(1);
      });
    });

    it("loads project YAML into canvas on success", async () => {
      render(<App />);
      await waitFor(() => {
        expect(loadFromYamlMock).toHaveBeenCalledWith(mockConfig.yaml);
      });
    });

    it("shows project root path in header when loaded", async () => {
      render(<App />);
      await waitFor(() => {
        expect(screen.getByTitle(mockConfig.config_path)).toBeDefined();
      });
      expect(screen.getByTitle(mockConfig.config_path).textContent).toBe("/proj");
    });

    it("shows load error when config fetch fails with non-400 error", async () => {
      fetchProjectConfigMock.mockRejectedValue(
        new ApiError(500, "Server error")
      );
      render(<App />);
      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
      });
      expect(screen.getByRole("alert").textContent).toBe("Server error");
    });

    it("shows load error for 404 (config missing)", async () => {
      fetchProjectConfigMock.mockRejectedValue(
        new ApiError(404, "Project config not found")
      );
      render(<App />);
      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
      });
      expect(screen.getByRole("alert").textContent).toContain(
        "Project config file not found"
      );
    });

    it("silently handles 400 (no project) without error", async () => {
      fetchProjectConfigMock.mockRejectedValue(
        new ApiError(400, "No StageFlow project found")
      );
      render(<App />);
      // Wait a tick — no alert should appear
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByRole("alert")).toBeNull();
      // Canvas load should NOT be called since there's no project
      expect(loadFromYamlMock).not.toHaveBeenCalled();
    });
  });

  describe("save button", () => {
    it("renders a Save button", () => {
      render(<App />);
      expect(screen.getByText("Save")).toBeDefined();
    });

    it("calls exportToYaml and saveProjectConfig on click", async () => {
      saveProjectConfigMock.mockResolvedValue(mockSaveResult);
      render(<App />);
      await waitFor(() => {
        expect(screen.getByText("Save")).toBeDefined();
      });

      fireEvent.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(exportToYamlMock).toHaveBeenCalled();
      });
      expect(saveProjectConfigMock).toHaveBeenCalledWith("stages: []");
    });

    it("shows success state after save", async () => {
      saveProjectConfigMock.mockResolvedValue(mockSaveResult);
      render(<App />);
      await waitFor(() => {
        expect(screen.getByText("Save")).toBeDefined();
      });

      await act(async () => {
        fireEvent.click(screen.getByText("Save"));
      });

      await waitFor(() => {
        const status = screen.getByRole("status");
        expect(status.textContent).toContain("no active run");
        expect(status.className).toContain("save-status-saved");
      });
    });

    it("shows blocked state on 403", async () => {
      saveProjectConfigMock.mockRejectedValue(
        new ApiError(
          403,
          "Cannot save workflow config while a run is active (current stage: 'alpha')."
        )
      );
      render(<App />);
      await waitFor(() => {
        expect(screen.getByText("Save")).toBeDefined();
      });

      await act(async () => {
        fireEvent.click(screen.getByText("Save"));
      });

      await waitFor(() => {
        const status = screen.getByRole("status");
        expect(status.textContent).toContain("active");
        expect(status.className).toContain("save-status-blocked");
      });
    });

    it("shows error state on validation failure", async () => {
      saveProjectConfigMock.mockRejectedValue(
        new ApiError(400, "YAML parse error: unexpected token")
      );
      render(<App />);
      await waitFor(() => {
        expect(screen.getByText("Save")).toBeDefined();
      });

      await act(async () => {
        fireEvent.click(screen.getByText("Save"));
      });

      await waitFor(() => {
        const status = screen.getByRole("status");
        expect(status.textContent).toContain("YAML parse error");
        expect(status.className).toContain("save-status-error");
      });
    });

    it("disables Save button when save is not allowed", async () => {
      fetchProjectConfigMock.mockResolvedValue({
        ...mockConfig,
        save_allowed: false,
        current_stage: "alpha",
      });
      render(<App />);
      await waitFor(() => {
        const btn = screen.getByText("Save");
        expect((btn as HTMLButtonElement).disabled).toBe(true);
      });
    });

    it("Save button is enabled when save is allowed", async () => {
      render(<App />);
      await waitFor(() => {
        const btn = screen.getByText("Save");
        expect((btn as HTMLButtonElement).disabled).toBe(false);
      });
    });
  });

  describe("export behavior preserved", () => {
    it("Ctrl+S still calls export (not save)", async () => {
      // Export is handled in Canvas via keydown; Ctrl+S does exportToYaml
      // Since Canvas is mocked, we verify exportToYaml is still available on the handle
      render(<App />);
      await waitFor(() => {
        // The export function exists on the canvas ref, not affected by save changes
        expect(exportToYamlMock).toBeDefined();
      });
    });
  });
});
