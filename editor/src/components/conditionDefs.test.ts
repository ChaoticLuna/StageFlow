import { describe, it, expect } from "vitest";
import { defaultParams, formatConditionSummary, CONDITION_TYPES, CONDITION_MAP } from "./conditionDefs";

describe("CONDITION_TYPES", () => {
  it("has at least 20 condition types registered", () => {
    expect(CONDITION_TYPES.length).toBeGreaterThanOrEqual(20);
  });

  it("every type has a label and description", () => {
    for (const ct of CONDITION_TYPES) {
      expect(ct.type).toBeTruthy();
      expect(ct.label).toBeTruthy();
      expect(ct.description).toBeTruthy();
      expect(Array.isArray(ct.params)).toBe(true);
    }
  });
});

describe("CONDITION_MAP", () => {
  it("maps every type to its definition", () => {
    expect(CONDITION_MAP.get("file_exists")?.label).toBe("File Exists");
    expect(CONDITION_MAP.get("always")?.label).toBe("Always");
    expect(CONDITION_MAP.get("unknown_type")).toBeUndefined();
  });
});

describe("defaultParams", () => {
  it("returns empty object for unknown type", () => {
    expect(defaultParams("nonexistent")).toEqual({});
  });

  it("returns empty params for 'always'", () => {
    expect(defaultParams("always")).toEqual({});
  });

  it("returns path param for file_exists", () => {
    const p = defaultParams("file_exists");
    expect(p).toHaveProperty("path");
    expect(p.path).toBe("");
  });

  it("returns default values for http_status", () => {
    const p = defaultParams("http_status");
    expect(p.method).toBe("GET");
    expect(p.expected_status).toBe(200);
    expect(p.timeout).toBe(10);
  });

  it("returns default for retry", () => {
    const p = defaultParams("retry");
    expect(p.max_attempts).toBe(12);
    expect(p.delay).toBe(5);
  });
});

describe("formatConditionSummary", () => {
  it("returns 'always' for empty array", () => {
    expect(formatConditionSummary([])).toBe("always");
  });

  it("returns label for single condition", () => {
    expect(formatConditionSummary([{ type: "always", params: {} }])).toBe("Always");
  });

  it("includes short path in summary", () => {
    const summary = formatConditionSummary([
      { type: "file_exists", params: { path: "findings.md" } },
    ]);
    expect(summary).toContain("File Exists");
    expect(summary).toContain("findings.md");
  });

  it("joins two conditions with +", () => {
    const summary = formatConditionSummary([
      { type: "file_exists", params: { path: "x.md" } },
      { type: "always", params: {} },
    ]);
    expect(summary).toContain("+");
  });

  it("shows count for 3+ conditions", () => {
    const summary = formatConditionSummary([
      { type: "file_exists", params: {} },
      { type: "always", params: {} },
      { type: "never", params: { reason: "nope" } },
    ]);
    expect(summary).toBe("3 conditions");
  });
});
