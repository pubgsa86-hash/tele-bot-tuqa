import { telegram } from "./telegram";

const API_BASE = "";

export interface SessionInfo {
  token: string;
  kind: string;
  duration: number;
  width: number;
  height: number;
  extension: string;
}

export interface JobInfo {
  job_id: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  error: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...((init?.headers as Record<string, string> | undefined) || {}),
  };
  const initData = telegram.initData;
  if (initData) headers["X-Init-Data"] = initData;
  if (init?.body) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error");
  }

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }

  if (!res.ok) {
    const code =
      body && typeof body === "object" && typeof (body as { error?: unknown }).error === "string"
        ? ((body as { error: string }).error as string)
        : "http_error";
    throw new ApiError(res.status, code);
  }
  if (body === null || typeof body !== "object") throw new ApiError(res.status, "invalid_response");
  return body as T;
}

export function videoUrl(token: string): string {
  return `${API_BASE}/api/video/${encodeURIComponent(token)}`;
}

export function getSession(token: string): Promise<SessionInfo> {
  return request<SessionInfo>(`/api/session/${encodeURIComponent(token)}`);
}

export function startProcess(token: string, settings: unknown): Promise<{ job_id: string; status: string }> {
  return request(`/api/process`, {
    method: "POST",
    body: JSON.stringify({ token, settings }),
  });
}

export function getJob(jobId: string): Promise<JobInfo> {
  return request<JobInfo>(`/api/job/${encodeURIComponent(jobId)}`);
}

export function cleanup(token: string): Promise<{ cleaned: boolean }> {
  return request(`/api/cleanup`, {
    method: "POST",
    body: JSON.stringify({ token }),
  });
}