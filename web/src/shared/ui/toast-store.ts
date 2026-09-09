// WEB-003 / WEB-008 — store des toasts + API impérative. Le rendu est dans toast.tsx.
import { create } from 'zustand';
import { friendlyMessage } from '@shared/api/errors';

export type Tone = 'info' | 'success' | 'error';
export type ToastItem = { id: number; tone: Tone; message: string };

type ToastState = {
  toasts: ToastItem[];
  push: (tone: Tone, message: string) => void;
  dismiss: (id: number) => void;
};

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (tone, message) =>
    set((s) => ({ toasts: [...s.toasts, { id: Date.now() + Math.random(), tone, message }] })),
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export const toast = {
  info: (m: string) => useToastStore.getState().push('info', m),
  success: (m: string) => useToastStore.getState().push('success', m),
  error: (e: unknown) => useToastStore.getState().push('error', friendlyMessage(e)),
};
