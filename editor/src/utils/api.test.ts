import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchProjectConfig, saveProjectConfig, ApiError } from "./api";

function mockFetchResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: () => Promise.resolve(data),
  };
}

describe("fetchProjectConfig", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it("returns config on success", async () => {
    const mockConfig = {
      yaml: "stages: []",
      config_path: "/proj/.stageflow/config/stages.yaml",
      project_root: "/proj",
      marker_type: "new",
      current_stage: null,
      run_status: null,
      save_allowed: true,
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse(mockConfig)
    );

    const result = await fetchProjectConfig();
    expect(result.yaml).toBe("stages: []");
    expect(result.save_allowed).toBe(true);
    expect(result.project_root).toBe("/proj");
  });

  it("throws ApiError on 400 (no project)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse({ detail: "No StageFlow project found" }, false, 400)
    );

    await expect(fetchProjectConfig()).rejects.toThrow(ApiError);
    await expect(fetchProjectConfig()).rejects.toMatchObject({
      status: 400,
    });
  });

  it("throws ApiError on 404 (config missing)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse({ detail: "Config not found" }, false, 404)
    );

    await expect(fetchProjectConfig()).rejects.toThrow(ApiError);
    await expect(fetchProjectConfig()).rejects.toMatchObject({
      status: 404,
    });
  });

  it("handles non-json error response gracefully", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(fetchProjectConfig()).rejects.toThrow(ApiError);
    await expect(fetchProjectConfig()).rejects.toMatchObject({
      status: 500,
    });
  });
});

describe("saveProjectConfig", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  it("saves successfully", async () => {
    const mockResult = {
      saved: true,
      config_path: "/proj/.stageflow/config/stages.yaml",
      message: "Config saved. Current state: no active run.",
    };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse(mockResult)
    );

    const result = await saveProjectConfig("stages: []");
    expect(result.saved).toBe(true);
    expect(result.message).toContain("no active run");
  });

  it("throws ApiError on 403 (save blocked by active run)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse(
        { detail: "Cannot save workflow config while a run is active (current stage: 'alpha')." },
        false,
        403
      )
    );

    await expect(saveProjectConfig("stages: []")).rejects.toThrow(ApiError);
    await expect(saveProjectConfig("stages: []")).rejects.toMatchObject({
      status: 403,
    });
  });

  it("throws ApiError on 400 (invalid YAML)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse(
        { detail: "YAML parse error: unexpected token" },
        false,
        400
      )
    );

    await expect(saveProjectConfig("not: [valid")).rejects.toThrow(ApiError);
    await expect(saveProjectConfig("not: [valid")).rejects.toMatchObject({
      status: 400,
    });
  });

  it("includes yaml in POST body", async () => {
    const mockResult = { saved: true, config_path: "/p", message: "ok" };
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockFetchResponse(mockResult)
    );

    await saveProjectConfig("stages:\n  - name: alpha");

    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/project/save-config",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml: "stages:\n  - name: alpha" }),
      })
    );
  });
});
