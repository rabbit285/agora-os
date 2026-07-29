export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  requestId?: string;

  constructor(status: number, message: string, requestId?: string) {
    super(message);
    this.status = status;
    this.requestId = requestId;
  }
}

type FetchOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  organizationId?: string;
};

/**
 * Thin fetch wrapper for the FastAPI backend. Always sends the session
 * cookie (credentials: "include") and unwraps the API's error envelope
 * (see apps/api/app/main.py) into an ApiError.
 */
export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.organizationId) {
    headers["X-Organization-Id"] = options.organizationId;
  }

  const response = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    credentials: "include",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    let requestId: string | undefined;
    try {
      const payload = await response.json();
      message = payload?.error?.message ?? message;
      requestId = payload?.error?.request_id;
    } catch {
      // response body wasn't JSON — keep the generic message
    }
    throw new ApiError(response.status, message, requestId);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
