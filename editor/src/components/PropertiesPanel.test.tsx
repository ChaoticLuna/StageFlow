import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import PropertiesPanel from "./PropertiesPanel";
import type { StageNode } from "../types";

function makeNode(overrides: Partial<StageNode> = {}): StageNode {
  return {
    id: "test-node",
    type: "stageNode",
    position: { x: 0, y: 0 },
    data: {
      name: "implement",
      tools: ["Edit", "Write"],
      description: "Implementation phase",
      on_enter: [],
      on_exit: [],
    },
    ...overrides,
  };
}

describe("PropertiesPanel", () => {
  describe("empty state", () => {
    it("renders placeholder when no node is selected", () => {
      render(<PropertiesPanel node={null} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("Select a node to edit its properties.")).toBeDefined();
    });

    it("renders the Properties heading in empty state", () => {
      render(<PropertiesPanel node={null} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("Properties")).toBeDefined();
    });
  });

  describe("node display", () => {
    it("renders the stage name in the heading", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("implement")).toBeDefined();
    });

    it("shows (terminal) suffix for terminal stage names", () => {
      render(
        <PropertiesPanel
          node={makeNode({ data: { name: "done", tools: [], description: "", on_enter: [], on_exit: [] } })}
          onNodeUpdate={vi.fn()}
        />
      );
      expect(screen.getByText("done (terminal)")).toBeDefined();
    });

    it("does not show (terminal) suffix for non-terminal names", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      expect(screen.queryByText("implement (terminal)")).toBeNull();
    });

    it("renders the Stage ID input with the name value", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      const input = screen.getByDisplayValue("implement");
      expect(input).toBeDefined();
    });

    it("renders the description input", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      const input = screen.getByDisplayValue("Implementation phase");
      expect(input).toBeDefined();
    });
  });

  describe("name editing", () => {
    it("calls onNodeUpdate when name is changed", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const input = screen.getByDisplayValue("implement");
      fireEvent.change(input, { target: { value: "deploy" } });
      expect(onUpdate).toHaveBeenCalledWith("test-node", expect.objectContaining({ name: "deploy" }));
    });
  });

  describe("description editing", () => {
    it("calls onNodeUpdate when description is changed", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const input = screen.getByDisplayValue("Implementation phase");
      fireEvent.change(input, { target: { value: "Deploy to production" } });
      expect(onUpdate).toHaveBeenCalledWith("test-node", expect.objectContaining({ description: "Deploy to production" }));
    });
  });

  describe("tool editor", () => {
    it("shows tool count in the label", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("Tools (2)")).toBeDefined();
    });

    it("renders each tool as a code element", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("Edit")).toBeDefined();
      expect(screen.getByText("Write")).toBeDefined();
    });

    it("shows hint when tools list is empty", () => {
      render(
        <PropertiesPanel
          node={makeNode({ data: { name: "review", tools: [], description: "", on_enter: [], on_exit: [] } })}
          onNodeUpdate={vi.fn()}
        />
      );
      expect(screen.getByText("No tools listed. Empty = all tools allowed in this stage.")).toBeDefined();
    });

    it("adds a tool when Add button is clicked", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const input = screen.getByPlaceholderText("e.g., Bash(git *)");
      fireEvent.change(input, { target: { value: "Bash" } });
      fireEvent.click(screen.getByText("Add"));
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ tools: ["Edit", "Write", "Bash"] })
      );
    });

    it("adds a tool when Enter is pressed", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const input = screen.getByPlaceholderText("e.g., Bash(git *)");
      fireEvent.change(input, { target: { value: "Glob" } });
      fireEvent.keyDown(input, { key: "Enter" });
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ tools: ["Edit", "Write", "Glob"] })
      );
    });

    it("does not add duplicate tool", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const input = screen.getByPlaceholderText("e.g., Bash(git *)");
      fireEvent.change(input, { target: { value: "Edit" } });
      fireEvent.click(screen.getByText("Add"));
      expect(onUpdate).not.toHaveBeenCalled();
    });

    it("does not add empty tool name", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const addBtn = screen.getByText("Add");
      expect((addBtn as HTMLButtonElement).disabled).toBe(true);
    });

    it("removes a tool when × is clicked", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const removeButtons = screen.getAllByText("×");
      fireEvent.click(removeButtons[0]);
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ tools: ["Write"] })
      );
    });
  });

  describe("hook editor", () => {
    it("shows on_enter and on_exit labels", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("on_enter hooks (0)")).toBeDefined();
      expect(screen.getByText("on_exit hooks (0)")).toBeDefined();
    });

    it("shows hint when no hooks are defined", () => {
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={vi.fn()} />);
      expect(screen.getByText("No on_enter hooks defined.")).toBeDefined();
      expect(screen.getByText("No on_exit hooks defined.")).toBeDefined();
    });

    it("renders existing hooks", () => {
      render(
        <PropertiesPanel
          node={makeNode({
            data: {
              name: "analyze",
              tools: [],
              description: "",
              on_enter: [{ shell: "echo in" }],
              on_exit: [{ python: "print('out')" }],
            },
          })}
          onNodeUpdate={vi.fn()}
        />
      );
      expect(screen.getByDisplayValue("echo in")).toBeDefined();
      expect(screen.getByDisplayValue("print('out')")).toBeDefined();
    });

    it("adds a default shell hook when + Add is clicked", () => {
      const onUpdate = vi.fn();
      render(<PropertiesPanel node={makeNode()} onNodeUpdate={onUpdate} />);
      const addButtons = screen.getAllByText("+ Add");
      fireEvent.click(addButtons[0]); // on_enter
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ on_enter: [{ shell: "" }] })
      );
    });

    it("removes a hook when × is clicked", () => {
      const onUpdate = vi.fn();
      render(
        <PropertiesPanel
          node={makeNode({
            data: {
              name: "analyze",
              tools: [],
              description: "",
              on_enter: [{ shell: "echo in" }, { python: "print('x')" }],
              on_exit: [],
            },
          })}
          onNodeUpdate={onUpdate}
        />
      );
      const removeButtons = screen.getAllByText("×");
      fireEvent.click(removeButtons[0]); // first hook's remove
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ on_enter: [{ python: "print('x')" }] })
      );
    });

    it("toggles hook kind from shell to python", () => {
      const onUpdate = vi.fn();
      render(
        <PropertiesPanel
          node={makeNode({
            data: {
              name: "analyze",
              tools: [],
              description: "",
              on_enter: [{ shell: "echo hi" }],
              on_exit: [],
            },
          })}
          onNodeUpdate={onUpdate}
        />
      );
      const kindToggle = screen.getByText("shell");
      fireEvent.click(kindToggle);
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ on_enter: [{ shell: "echo hi", python: "echo hi" }] })
      );
    });

    it("toggles hook kind from python to shell", () => {
      const onUpdate = vi.fn();
      render(
        <PropertiesPanel
          node={makeNode({
            data: {
              name: "analyze",
              tools: [],
              description: "",
              on_enter: [],
              on_exit: [{ python: "print('x')" }],
            },
          })}
          onNodeUpdate={onUpdate}
        />
      );
      const kindToggle = screen.getByText("python");
      fireEvent.click(kindToggle);
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ on_exit: [{ python: "print('x')", shell: "print('x')" }] })
      );
    });

    it("updates hook value on change", () => {
      const onUpdate = vi.fn();
      render(
        <PropertiesPanel
          node={makeNode({
            data: {
              name: "analyze",
              tools: [],
              description: "",
              on_enter: [{ shell: "echo hi" }],
              on_exit: [],
            },
          })}
          onNodeUpdate={onUpdate}
        />
      );
      const input = screen.getByDisplayValue("echo hi");
      fireEvent.change(input, { target: { value: "echo updated" } });
      expect(onUpdate).toHaveBeenCalledWith(
        "test-node",
        expect.objectContaining({ on_enter: [{ shell: "echo updated" }] })
      );
    });
  });
});
