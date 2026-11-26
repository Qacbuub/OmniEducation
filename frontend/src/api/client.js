import { mockRequest } from "./mock";

const API_URL = import.meta.env.VITE_API_URL || "/api";
const USE_MOCK = String(import.meta.env.VITE_USE_MOCK) === "true";

/*
 * Sign-in is kept per browser tab (sessionStorage), so one browser can have a principal in one tab and a
 * teacher in another. localStorage only remembers the most recent sign-in, so that a brand-new tab opens
 * already signed in, plus each account's latest token pair (to recover if two tabs share one session).
 */
const TOKEN_KEY = "omniedu.tokens";
const userKey = (uid) => `${TOKEN_KEY}.u${uid}`;

function userIdOf(pair) {
  try {
    const part = pair.refresh.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(part)).user_id;
  } catch { return null; }
}
const read = (store, key) => { try { return JSON.parse(store.getItem(key)) || null; } catch { return null; } };
const write = (store, key, value) => { try { store.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ } };
const remove = (store, key) => { try { store.removeItem(key); } catch { /* storage unavailable */ } };

export const tokens = {
  get() {
    return read(sessionStorage, TOKEN_KEY);
  },
  /** The most recent sign-in in this browser (what a new tab can start from). */
  lastSignIn() {
    return read(localStorage, TOKEN_KEY);
  },
  set(value) {
    write(sessionStorage, TOKEN_KEY, value);
    write(localStorage, TOKEN_KEY, value);
    const uid = userIdOf(value);
    if (uid != null) write(localStorage, userKey(uid), value);
  },
  clear() {
    const mine = read(sessionStorage, TOKEN_KEY);
    remove(sessionStorage, TOKEN_KEY);
    const uid = mine && userIdOf(mine);
    if (uid != null) remove(localStorage, userKey(uid));
    // Forget the "most recent sign-in" only if it is this account, so other tabs' accounts are untouched.
    const last = read(localStorage, TOKEN_KEY);
    if (last && (!mine || userIdOf(last) === uid)) remove(localStorage, TOKEN_KEY);
  },
  /** Another tab of the same account may hold a newer token pair after rotating it. */
  latestFor(pair) {
    const uid = pair && userIdOf(pair);
    return uid == null ? null : read(localStorage, userKey(uid));
  },
};

/**
 * A new tab starts as the account that signed in most recently in this browser, but with its own session
 * (forked on the server), so signing out or signing in as someone else here leaves the other tabs alone.
 */
export async function adoptSession() {
  if (USE_MOCK || tokens.get()) return Boolean(tokens.get() || USE_MOCK);
  const last = tokens.lastSignIn();
  if (!last?.refresh) return false;
  try {
    const res = await fetch(`${API_URL}/auth/token/fork/`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh: last.refresh }),
    });
    if (!res.ok) return false;
    const pair = await res.json();
    write(sessionStorage, TOKEN_KEY, pair);
    return true;
  } catch { return false; }
}

/** Structured error matching the backend's error envelope: { code, message, fields }. */
export class ApiError extends Error {
  constructor(status, body) {
    super(body?.message || body?.detail || `Request failed (${status})`);
    this.status = status;
    this.code = body?.code || "error";
    this.fields = body?.fields || {};
  }
}

let refreshing = null;

async function refreshAccess() {
  const current = tokens.get();
  if (!current?.refresh) return false;
  refreshing ??= fetch(`${API_URL}/auth/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: current.refresh }),
  })
    .then(async (res) => {
      if (!res.ok) {
        // Two tabs of one account share a session; if the other tab already rotated the refresh token,
        // take over its newer pair instead of signing this tab out.
        const newer = tokens.latestFor(current);
        if (newer?.refresh && newer.refresh !== current.refresh) { tokens.set(newer); return true; }
        return false;
      }
      const data = await res.json();
      tokens.set({ ...current, access: data.access, refresh: data.refresh || current.refresh });
      return true;
    })
    .finally(() => { refreshing = null; });
  return refreshing;
}

async function request(method, path, { body, params, retry = true } = {}) {
  const query = params
    ? "?" + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "")).toString()
    : "";

  if (USE_MOCK) return mockRequest(method, path + query, body);

  const headers = {};
  const isForm = body instanceof FormData;
  if (body && !isForm) headers["Content-Type"] = "application/json";
  const access = tokens.get()?.access;
  if (access) headers.Authorization = `Bearer ${access}`;

  const res = await fetch(`${API_URL}${path}${query}`, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });

  if (res.status === 401 && retry && (await refreshAccess())) {
    return request(method, path, { body, params, retry: false });
  }
  if (res.status === 204) return null;

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401) {
      tokens.clear();
      window.dispatchEvent(new Event("omniedu:logout"));
    }
    throw new ApiError(res.status, data);
  }
  return data;
}

/** Fetch a protected file (PDF, CSV, upload) with the user's token and open or save it. */
async function download(path, { filename, open = true } = {}) {
  const doFetch = () => fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${tokens.get()?.access || ""}` } });
  let res = await doFetch();
  if (res.status === 401 && (await refreshAccess())) res = await doFetch();
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, data);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const name = filename || (res.headers.get("Content-Disposition") || "").match(/filename="?([^";]+)"?/)?.[1] || "download";
  if (open && blob.type === "application/pdf") {
    window.open(url, "_blank", "noopener");
  } else {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Fetch a protected file with the user's token and return it as a Blob (e.g. a student photo). */
async function blob(path) {
  const doFetch = () => fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${tokens.get()?.access || ""}` } });
  let res = await doFetch();
  if (res.status === 401 && (await refreshAccess())) res = await doFetch();
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
  return res.blob();
}

export const api = {
  download,
  blob,
  get: (path, params) => request("GET", path, { params }),
  post: (path, body) => request("POST", path, { body }),
  put: (path, body) => request("PUT", path, { body }),
  patch: (path, body) => request("PATCH", path, { body }),
  delete: (path, body) => request("DELETE", path, { body }),
  isMock: USE_MOCK,
};
