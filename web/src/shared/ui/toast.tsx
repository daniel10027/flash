// WEB-003 / WEB-008 — rendu des toasts.
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useToastStore } from './toast-store';
import './ui.css';

export function Toaster() {
  const { toasts, dismiss } = useToastStore();

  useEffect(() => {
    if (!toasts.length) return;
    const timers = toasts.map((t) => setTimeout(() => dismiss(t.id), 5000));
    return () => timers.forEach(clearTimeout);
  }, [toasts, dismiss]);

  if (!toasts.length) return null;
  return createPortal(
    <div className="ui-toaster" role="region" aria-live="polite" aria-label="Notifications">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`ui-toast ui-toast--${t.tone}`}
          role={t.tone === 'error' ? 'alert' : 'status'}
        >
          <span>{t.message}</span>
          <button
            type="button"
            className="ui-btn ui-btn--ghost ui-btn--sm"
            aria-label="Fermer la notification"
            onClick={() => dismiss(t.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>,
    document.body,
  );
}
