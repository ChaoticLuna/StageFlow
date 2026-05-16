class NoopResizeObserver implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

const browserGlobal = globalThis as typeof globalThis & {
  ResizeObserver?: typeof ResizeObserver;
};

if (typeof browserGlobal.ResizeObserver === "undefined") {
  browserGlobal.ResizeObserver = NoopResizeObserver;
}
