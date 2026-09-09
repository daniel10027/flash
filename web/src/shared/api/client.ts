// WEB-004 — client HTTP typé : base URL runtime, Idempotency-Key, X-Request-ID,
// rafraîchissement automatique du jeton, erreurs normalisées (ApiError / NetworkError).

import { config } from '@shared/config/runtime';
import { ApiError, NetworkError, type ApiErrorBody } from './errors';
import { getAccessToken, onSessionExpired, refreshTokens } from '@shared/auth/session';

type Query = Record<string, string | number | boolean | undefined | null>;

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Query;
  idempotencyKey?: string;
  signal?: AbortSignal;
  auth?: boolean; // défaut true
  retryOn401?: boolean; // usage interne
};

const uuid = () =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;

function buildUrl(path: string, query?: Query): string {
  const base = config.API_BASE_URL.replace(/\/$/, '');
  const url = new URL(base + path, base || window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }
  return base ? url.toString() : url.pathname + url.search;
}

async function parseError(res: Response): Promise<ApiError> {
  let body: ApiErrorBody = { code: 'INTERNAL_ERROR', message: res.statusText };
  try {
    const json = (await res.json()) as Partial<ApiErrorBody>;
    if (json && typeof json.code === 'string') {
      body = { code: json.code, message: json.message ?? '', details: json.details };
    }
  } catch {
    /* réponse non-JSON */
  }
  return new ApiError(res.status, body);
}

export async function apiFetch<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, idempotencyKey, signal, auth = true } = opts;

  const headers: Record<string, string> = { 'X-Request-ID': uuid() };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  else if (method !== 'GET') headers['Idempotency-Key'] = uuid();

  if (auth) {
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
      credentials: 'include',
    });
  } catch {
    throw new NetworkError();
  }

  if (res.status === 401 && auth && opts.retryOn401 !== false) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      return apiFetch<T>(path, { ...opts, retryOn401: false });
    }
    onSessionExpired();
    throw await parseError(res);
  }

  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;

  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) =>
    apiFetch<T>(path, { method: 'GET', query, signal }),
  post: <T>(path: string, body?: unknown, idempotencyKey?: string) =>
    apiFetch<T>(path, { method: 'POST', body, idempotencyKey }),
  put: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: 'PATCH', body }),
  del: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
};
