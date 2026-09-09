// WEB-032 — "masquer les soldes par défaut". Ré-utilisé par l'en-tête (WEB-006).
import { create } from 'zustand';

const KEY = 'flash.hideBalances';

const read = () => {
  try {
    return localStorage.getItem(KEY) === '1';
  } catch {
    return false;
  }
};

type PrivacyState = { hidden: boolean; toggle: () => void };

export const usePrivacy = create<PrivacyState>((set, get) => ({
  hidden: read(),
  toggle: () => {
    const next = !get().hidden;
    try {
      localStorage.setItem(KEY, next ? '1' : '0');
    } catch {
      /* ignore */
    }
    set({ hidden: next });
  },
}));
