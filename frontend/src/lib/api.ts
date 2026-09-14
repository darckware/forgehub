/**
 * Shared fetch wrapper for all backend calls.
 *
 * Convention: every backend resource is mounted at
 *   /api/v1/<resource>   (hyphenated, plural, matching the FastAPI router prefix)
 *
 * Example: GET /api/v1/product-versions, POST /api/v1/planning-items
 *
 * Domain hooks (src/hooks/use<Domain>.ts) should call apiClient.get/post/etc.
 * with that exact path -- do not hardcode the base URL or prepend extra
 * segments elsewhere.
 */

// Falls back to the page's own origin (not a hardcoded localhost:8000) so
// the same build works whether it's loaded from localhost, a LAN IP, or a
// Cloudflare tunnel hostname -- nginx (frontend/nginx.conf) proxies /api on
// that same origin to the backend, so there's no cross-origin call to make.
const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  /** Override or add query params: { page: 1, search: "x" } */
  params?: Record<string, string | number | boolean | undefined>;
};

function buildUrl(path: string, params?: RequestOptions["params"]) {
  const url = new URL(path.replace(/^\//, ""), BASE_URL.endsWith("/") ? BASE_URL : `${BASE_URL}/`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

export function getToken(): string | null {
  try {
    const raw = localStorage.getItem("forgehub-auth");
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.state?.token ?? null;
  } catch {
    return null;
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, params, headers, ...rest } = options;

  const token = getToken();
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

  const res = await fetch(buildUrl(path, params), {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    // Token expired or invalid — clear stored auth and redirect to login
    try {
      const raw = localStorage.getItem("forgehub-auth");
      if (raw) {
        const parsed = JSON.parse(raw);
        parsed.state.token = null;
        parsed.state.user = null;
        localStorage.setItem("forgehub-auth", JSON.stringify(parsed));
      }
    } catch {
      // ignore
    }
    window.location.href = "/login";
  }

  if (!res.ok) {
    let parsedBody: unknown = undefined;
    try {
      parsedBody = await res.json();
    } catch {
      // response had no JSON body
    }
    throw new ApiError(`Request to ${path} failed with status ${res.status}`, res.status, parsedBody);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

/** POST multipart/form-data (file uploads) -- bypasses the JSON request()
 * helper since fetch must set its own multipart boundary header. */
async function postForm<T>(path: string, formData: FormData, params?: RequestOptions["params"]): Promise<T> {
  const token = getToken();
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(buildUrl(path, params), { method: "POST", body: formData, headers: authHeader });

  if (!res.ok) {
    let parsedBody: unknown = undefined;
    try {
      parsedBody = await res.json();
    } catch {
      // response had no JSON body
    }
    throw new ApiError(`Request to ${path} failed with status ${res.status}`, res.status, parsedBody);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

/** GET a file response (Content-Disposition: attachment) as a Blob + the
 * server-provided filename -- a plain <a href> download can't carry the
 * Bearer auth header this API requires, so callers must fetch the blob
 * here and trigger the save themselves via URL.createObjectURL. */
async function downloadFile(path: string): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(buildUrl(path), { headers: authHeader });

  if (!res.ok) {
    throw await apiErrorFromResponse(path, res);
  }

  return downloadFromResponse(path, res);
}

async function apiErrorFromResponse(path: string, response: Response): Promise<ApiError> {
  let parsedBody: unknown = undefined;
  try {
    parsedBody = await response.json();
  } catch {
    // response had no JSON body
  }
  return new ApiError(
    `Request to ${path} failed with status ${response.status}`,
    response.status,
    parsedBody,
  );
}

function filenameFromDisposition(path: string, response: Response): string {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const candidate = match?.[1] ?? path;
  const withoutQuery = candidate.split(/[?#]/, 1)[0].replace(/\\/g, "/");
  const basename = withoutQuery.split("/").pop()?.replace(/[\u0000-\u001f\u007f]/g, "").trim();
  return basename && basename !== "." && basename !== ".." ? basename : "download";
}

async function downloadFromResponse(path: string, response: Response) {
  return { blob: await response.blob(), filename: filenameFromDisposition(path, response) };
}

async function postDownload(path: string, body?: unknown): Promise<{ blob: Blob; filename: string }> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(buildUrl(path), {
    method: "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await apiErrorFromResponse(path, response);
  return downloadFromResponse(path, response);
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  postForm,
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
  downloadFile,
  postDownload,
};
