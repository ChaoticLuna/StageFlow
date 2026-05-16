export interface ProjectConfig {
  yaml: string;
  config_path: string;
  project_root: string;
  marker_type: string;
  current_stage: string | null;
  run_status: string | null;
  save_allowed: boolean;
}

export interface ProjectStatus {
  project_root: string;
  marker_type: string;
  current_stage: string | null;
  run_status: string | null;
  final_stage: string | null;
  completed_at: string | null;
  run_id: string | null;
  save_allowed: boolean;
  history_count: number;
  variable_keys: string[];
  retry_count: Record<string, number>;
  iterations: Record<string, number>;
  state_path: string;
  config_path: string;
}

export interface SaveResult {
  saved: boolean;
  config_path: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export async function fetchProjectConfig(): Promise<ProjectConfig> {
  const res = await fetch("/api/project/config");
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, (body as { detail?: string }).detail || res.statusText);
  }
  return body as ProjectConfig;
}

export async function saveProjectConfig(yaml: string): Promise<SaveResult> {
  const res = await fetch("/api/project/save-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, (body as { detail?: string }).detail || res.statusText);
  }
  return body as SaveResult;
}
