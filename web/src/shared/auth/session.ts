// WEB-005 — session : jeton d'accès en mémoire, refresh persisté (localStorage),
// rafraîchissement automatique, expiration → redirection login.

import { create } from 'zustand';
import { config } from '@shared/config/runtime';

const REFRESH_KEY = 'flash.refresh';
const DEVICE_KEY = 'flash.device';

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  access_expires_in: number;
  refresh_expires_in: number;
};

type SessionState = {
  accessToken: string | null;
  status: 'anonymous' | 'authenticated';
  setSession: (tokens: TokenPair) => void;
  clear: () => void;
};

function readRefresh(): string | null {
  try {
    return localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function deviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = globalThis.crypto?.randomUUID?.() ?? String(Date.now());
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return 'web';
  }
}

export const useSession = create<SessionState>((set) => ({
  accessToken: null,
  status: readRefresh() ? 'authenticated' : 'anonymous',
  setSession: (tokens) => {
    try {
      localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
    } catch {
      /* stockage indisponible */
    }
    set({ accessToken: tokens.access_token, status: 'authenticated' });
  },
  clear: () => {
    try {
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      /* ignore */
    }
    set({ accessToken: null, status: 'anonymous' });
  },
}));

export const getAccessToken = () => useSession.getState().accessToken;

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshTokens(): Promise<boolean> {
  const refresh = readRefresh();
  if (!refresh) return false;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const base = config.API_BASE_URL.replace(/\/$/, '');
      const res = await fetch(`${base}/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
        credentials: 'include',
      });
      if (!res.ok) return false;
      const tokens = (await res.json()) as TokenPair;
      useSession.getState().setSession(tokens);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

// Branché par le routeur pour rediriger proprement vers /login.
let expiredHandler: () => void = () => {};
export const setSessionExpiredHandler = (fn: () => void) => {
  expiredHandler = fn;
};
export function onSessionExpired(): void {
  useSession.getState().clear();
  expiredHandler();
}
