// WEB-040 — accès back-office par clé partagée (`X-Admin-Key`). Distinct de la session
// utilisateur (JWT). La clé est stockée localement ; le rôle effectif est déterminé par
// le backend à chaque appel (403 si insuffisant).
import { create } from 'zustand';
import { config } from '@shared/config/runtime';
import { ApiError, NetworkError, type ApiErrorBody } from '@shared/api/errors';

const KEY = 'flash.adminKey';

type AdminState = { key: string | null; setKey: (k: string | null) => void };
export const useAdminAuth = create<AdminState>((set) => ({
  key: (() => {
    try {
      return localStorage.getItem(KEY);
    } catch {
      return null;
    }
  })(),
  setKey: (k) => {
    try {
      if (k) localStorage.setItem(KEY, k);
      else localStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
    set({ key: k });
  },
}));

const uuid = () =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;

type Opts = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  raw?: boolean; // renvoyer le texte brut (CSV)
};

export async function adminFetch<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const { method = 'GET', body, query, raw } = opts;
  const key = useAdminAuth.getState().key;
  const base = config.API_BASE_URL.replace(/\/$/, '');
  const url = new URL(base + path, base || window.location.origin);
  for (const [k, v] of Object.entries(query ?? {}))
    if (v != null) url.searchParams.set(k, String(v));

  const headers: Record<string, string> = { 'X-Request-ID': uuid() };
  if (key) headers['X-Admin-Key'] = key;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(base ? url.toString() : url.pathname + url.search, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new NetworkError();
  }

  if (!res.ok) {
    let payload: ApiErrorBody = { code: 'INTERNAL_ERROR', message: res.statusText };
    try {
      const j = (await res.json()) as Partial<ApiErrorBody>;
      if (j?.code) payload = { code: j.code, message: j.message ?? '', details: j.details };
    } catch {
      /* non-JSON */
    }
    throw new ApiError(res.status, payload);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (raw) return text as unknown as T;
  return (text ? JSON.parse(text) : undefined) as T;
}
