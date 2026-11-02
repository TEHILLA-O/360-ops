export class ApiError extends Error {
  status: number;
  body: { error_code?: string; message?: string };

  constructor(status: number, body: { error_code?: string; message?: string }) {
    super(body.message || "Request failed");
    this.status = status;
    this.body = body;
  }
}

export async function api<T>(path: string, persona: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-OpsPilot-Actor", persona);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  const text = await response.text();
  const body = text ? (JSON.parse(text) as { error_code?: string; message?: string }) : {};
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
