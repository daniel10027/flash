// WEB-003 — Tabs contrôlés, navigables au clavier (flèches).
import { useRef, type KeyboardEvent } from 'react';
import './ui.css';

export type TabItem = { id: string; label: string };

export function Tabs({
  items,
  value,
  onChange,
  ariaLabel,
}: {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  function onKey(e: KeyboardEvent<HTMLButtonElement>) {
    const idx = items.findIndex((t) => t.id === value);
    const at = (i: number) => items[((i % items.length) + items.length) % items.length]?.id;
    if (e.key === 'ArrowRight') {
      const id = at(idx + 1);
      if (id) onChange(id);
    }
    if (e.key === 'ArrowLeft') {
      const id = at(idx - 1);
      if (id) onChange(id);
    }
  }

  return (
    <div ref={listRef} className="ui-tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          className="ui-tab"
          aria-selected={t.id === value}
          tabIndex={t.id === value ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={onKey}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
