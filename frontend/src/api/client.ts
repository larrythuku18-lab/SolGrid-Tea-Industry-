const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:5000";

const ACCESS_TOKEN_KEY = "solgrid_access_token";
const REFRESH_TOKEN_KEY = "solgrid_refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// Set by AuthContext so a session that dies mid-app (refresh token expired
// or revoked) drops the user back to /login instead of every screen having
// to handle "the API just started 401-ing" on its own.
let onSessionExpired: (() => void) | null = null;
export function setSessionExpiredHandler(handler: () => void): void {
  onSessionExpired = handler;
}

async function refreshAccessToken(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;

  const res = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { Authorization: `Bearer ${refresh}` },
  });
  if (!res.ok) return false;

  const data = (await res.json()) as { access_token: string };
  localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
  return true;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | undefined>;
}

interface EventStreamOptions {
  query?: Record<string, string | undefined>;
  signal?: AbortSignal;
  onOpen?: () => void;
  onEvent: (event: string, data: unknown) => void;
}

/** Splits one `event:`/`data:` frame. Returns null for anything without a
 * data line (a bare `:keepalive` comment, a retry hint, or a malformed
 * payload) — dropping a frame we can't read is better than tearing down a
 * live view over it. */
function parseEventFrame(frame: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue;
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) as unknown };
  } catch {
    return null;
  }
}

/** Server-sent events over fetch rather than EventSource: EventSource can't
 * send an Authorization header, and this API authenticates with a bearer
 * token (see the auth note in frontend/README.md). Same one-shot 401
 * refresh as apiRequest, for the same reason.
 *
 * Resolves when the server closes the stream, and rejects on transport
 * failure. Reconnecting is left to the caller — only it knows whether a
 * given failure is worth retrying and how long to wait. */
export async function openEventStream(
  path: string,
  options: EventStreamOptions,
  allowRetry = true,
): Promise<void> {
  const url = new URL(path, API_BASE_URL);
  if (options.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }

  const access = getAccessToken();
  const res = await fetch(url.toString(), {
    headers: {
      Accept: "text/event-stream",
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
    },
    signal: options.signal,
  });

  if (res.status === 401 && allowRetry && access) {
    if (await refreshAccessToken()) {
      return openEventStream(path, options, false);
    }
    clearTokens();
    onSessionExpired?.();
    throw new ApiError(401, "session expired", null);
  }
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText, null);
  }
  if (!res.body) {
    throw new ApiError(0, "this browser can't stream responses", null);
  }

  options.onOpen?.();

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });

    // Frames are separated by a blank line; keep the remainder buffered, a
    // chunk can (and regularly does) land mid-frame.
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = parseEventFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (frame) options.onEvent(frame.event, frame.data);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
  allowRetry = true,
): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  if (options.query) {
    for (const [key, value] of Object.entries(options.query)) {
      if (value !== undefined) url.searchParams.set(key, value);
    }
  }

  const access = getAccessToken();
  const res = await fetch(url.toString(), {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(access ? { Authorization: `Bearer ${access}` } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  // A 401 on a request that carried no token at all means "not logged in"
  // (there is no token to refresh) rather than "session expired" — only
  // retry-via-refresh when we actually sent one.
  if (res.status === 401 && allowRetry && access) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiRequest<T>(path, options, false);
    }
    clearTokens();
    onSessionExpired?.();
    throw new ApiError(401, "session expired", null);
  }

  const contentType = res.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json") ? await res.json() : null;

  if (!res.ok) {
    const message =
      (payload && typeof payload === "object" && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : undefined) ?? res.statusText;
    throw new ApiError(res.status, message, payload);
  }

  return payload as T;
}
