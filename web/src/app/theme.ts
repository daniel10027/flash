// WEB-002 / WEB-010 — thème clair / sombre / système, persisté, appliqué sur <html>.
import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark' | 'system';
const KEY = 'flash.theme';

function read(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY) as ThemeMode | null;
    if (v === 'light' || v === 'dark' || v === 'system') return v;
  } catch {
    /* ignore */
  }
  return 'system';
}

function apply(mode: ThemeMode): void {
  document.documentElement.setAttribute('data-theme', mode);
}

type ThemeState = { mode: ThemeMode; setMode: (m: ThemeMode) => void; cycle: () => void };

export const useTheme = create<ThemeState>((set, get) => ({
  mode: read(),
  setMode: (mode) => {
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* ignore */
    }
    apply(mode);
    set({ mode });
  },
  cycle: () => {
    const order: ThemeMode[] = ['system', 'light', 'dark'];
    const next = order[(order.indexOf(get().mode) + 1) % order.length] ?? 'system';
    get().setMode(next);
  },
}));

// Applique le thème lu au chargement du module (avant le premier rendu).
apply(read());
