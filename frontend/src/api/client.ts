/**
 * The HTTP layer.
 *
 * One place that knows about URLs, one place that turns a non-2xx response into
 * an `ApiError` carrying FastAPI's `detail` string. Components call the named
 * functions and never touch `fetch` — which is what keeps error handling
 * consistent across the six call sites.
 */

import type {
  HealthPayload,
  OnboardingRequest,
  RequestSummary,
  TemplateEntry,
} from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // A network-level failure has no status and no detail body; the UI still
    // needs something readable to show.
    throw new ApiError("Could not reach the API", 0);
  }

  if (!response.ok) {
    let detail = response.statusText || `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail)) {
        // Pydantic validation errors arrive as a list of objects.
        detail = body.detail
          .map((item) =>
            typeof item === "object" && item !== null && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : String(item),
          )
          .join("; ");
      }
    } catch {
      /* keep statusText */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthPayload>("/api/health"),

  listRequests: () =>
    request<{ requests: RequestSummary[] }>("/api/requests").then(
      (body) => body.requests,
    ),

  getRequest: (id: string) =>
    request<OnboardingRequest>(`/api/requests/${encodeURIComponent(id)}`),

  createRequest: (prompt: string) =>
    request<OnboardingRequest>("/api/requests", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),

  deleteRequest: (id: string) =>
    request<{ status: string; id: string }>(
      `/api/requests/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),

  submitAnswers: (id: string, answers: Record<string, string>) =>
    request<OnboardingRequest>(
      `/api/requests/${encodeURIComponent(id)}/answers`,
      { method: "POST", body: JSON.stringify({ answers }) },
    ),

  generate: (id: string) =>
    request<OnboardingRequest>(
      `/api/requests/${encodeURIComponent(id)}/generate`,
      { method: "POST" },
    ),

  testConnection: (id: string, credentials: Record<string, string>) =>
    request<OnboardingRequest>(`/api/requests/${encodeURIComponent(id)}/test`, {
      method: "POST",
      body: JSON.stringify({ credentials }),
    }),

  templates: () =>
    request<{ templates: TemplateEntry[] }>("/api/templates").then(
      (body) => body.templates,
    ),

  downloadUrl: (id: string) =>
    `/api/requests/${encodeURIComponent(id)}/download`,
};
