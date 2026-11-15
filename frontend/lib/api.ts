import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type S = components["schemas"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const KEY = "docly.tokens";

type Tokens = { access: string; refresh: string };

// Tokens live in localStorage: simple SPA flow. Trade-off (documented): readable by XSS; mitigated by short
// access-token lifetime, refresh rotation with reuse detection, and no user-supplied HTML rendering.
export const tokens = {
  get(): Tokens | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? (JSON.parse(raw) as Tokens) : null;
    } catch {
      return null;
    }
  },
  set(t: Tokens) {
    localStorage.setItem(KEY, JSON.stringify(t));
  },
  clear() {
    localStorage.removeItem(KEY);
  },
};

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
  }
}

let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const t = tokens.get();
  if (!t) return false;
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ refresh_token: t.refresh }),
      });
      if (!r.ok) return false;
      const j = (await r.json()) as S["TokenOut"];
      tokens.set({ access: j.access_token, refresh: j.refresh_token });
      return true;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

// /auth/me needs the bearer token, so only the credential-less auth endpoints are "public".
const isPublicPath = (url: string) => /\/(auth\/(login|signup|refresh|logout)|public\/)/.test(url);

async function authFetch(request: Request): Promise<Response> {
  const retry = request.clone();
  const t = tokens.get();
  if (t && !isPublicPath(request.url)) request.headers.set("Authorization", `Bearer ${t.access}`);
  const res = await fetch(request);
  if (res.status === 401 && t && !isPublicPath(request.url) && (await refreshTokens())) {
    const fresh = tokens.get();
    if (fresh) retry.headers.set("Authorization", `Bearer ${fresh.access}`);
    return fetch(retry);
  }
  return res;
}

export const api = createClient<paths>({ baseUrl: API_URL, fetch: authFetch });

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Turns an openapi-fetch result into data or a typed ApiError (backend format {error:{code,message,details}}). */
export async function unwrap<T>(p: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await p;
  if (!response.ok) {
    const e = (error as { error?: { code?: string; message?: string; details?: unknown } } | undefined)?.error;
    throw new ApiError(e?.code ?? "UNKNOWN", e?.message ?? `Request failed (${response.status})`, response.status, e?.details);
  }
  return data as T;
}

export async function login(email: string, password: string, clinicSlug?: string): Promise<S["TokenOut"]> {
  const out = await unwrap(api.POST("/auth/login", { body: { email, password, clinic_slug: clinicSlug || null } }));
  tokens.set({ access: out.access_token, refresh: out.refresh_token });
  return out;
}

export async function logout() {
  const t = tokens.get();
  tokens.clear();
  if (t) await api.POST("/auth/logout", { body: { refresh_token: t.refresh } }).catch(() => undefined);
}

export function fmtTime(iso: string, tz: string) {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}
export function fmtDateTime(iso: string, tz: string) {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: tz }).format(new Date(iso));
}
/** YYYY-MM-DD of an instant in a timezone. */
export function ymd(d: Date, tz: string) {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: tz }).format(d);
}
export function money(minor: number, currency: string) {
  return `${new Intl.NumberFormat("en-US").format(minor / 100)} ${currency}`;
}

/** Interpret a `YYYY-MM-DDTHH:mm` wall-clock value in timezone `tz` and return the UTC ISO instant. */
export function zonedToIso(local: string, tz: string): string {
  const asUtc = new Date(`${local}:00Z`);
  const shown = new Intl.DateTimeFormat("sv-SE", { timeZone: tz, dateStyle: "short", timeStyle: "medium" }).format(asUtc);
  const offsetMs = new Date(`${shown.replace(" ", "T")}Z`).getTime() - asUtc.getTime();
  return new Date(asUtc.getTime() - offsetMs).toISOString();
}
export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
