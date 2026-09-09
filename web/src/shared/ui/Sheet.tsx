// WEB-003 — Sheet / Modal accessible (focus trap léger, Échap, clic hors zone).
import { useEffect, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import './ui.css';

export function Sheet({
  open,
  onClose,
  title,
  children,
  variant = 'bottom',
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  variant?: 'bottom' | 'center';
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <>
      <div className="ui-scrim" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        className={`ui-sheet ui-sheet--${variant}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong>{title}</strong>
          <button className="ui-btn ui-btn--ghost ui-btn--sm" onClick={onClose} aria-label="Fermer">
            ✕
          </button>
        </header>
        {children}
      </div>
    </>,
    document.body,
  );
}
