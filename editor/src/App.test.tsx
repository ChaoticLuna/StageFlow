import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("./components/Canvas", () => ({
  default: vi.fn(() => <div data-testid="mock-canvas">Canvas</div>),
}));

import App from "./App";

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
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
});
