// WEB-003 — composants de base. Une API minimale, accessibles par défaut.
import {
  forwardRef,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';
import { formatMoney } from '@shared/i18n/format';
import './ui.css';

const cx = (...c: Array<string | false | undefined>) => c.filter(Boolean).join(' ');

/* ------------------------------------------------------------------ Button */
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'md' | 'sm';
  block?: boolean;
  loading?: boolean;
};
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', block, loading, disabled, children, className, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(
        'ui-btn',
        `ui-btn--${variant}`,
        size === 'sm' && 'ui-btn--sm',
        block && 'ui-btn--block',
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? '…' : children}
    </button>
  );
});

/* ------------------------------------------------------------------ Input */
type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
  suffix?: string;
};
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, id, className, suffix, ...rest },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-err` : hint ? `${inputId}-hint` : undefined;
  return (
    <div className={cx('ui-field', className)}>
      {label && (
        <label className="ui-label" htmlFor={inputId}>
          {label}
        </label>
      )}
      <div className={suffix ? 'ui-input-wrap' : undefined}>
        <input
          ref={ref}
          id={inputId}
          className="ui-input"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...rest}
        />
        {suffix && (
          <span className="ui-input-suffix" aria-hidden>
            {suffix}
          </span>
        )}
      </div>
      {error ? (
        <span id={`${inputId}-err`} className="ui-hint ui-hint--error">
          {error}
        </span>
      ) : hint ? (
        <span id={`${inputId}-hint`} className="ui-hint">
          {hint}
        </span>
      ) : null}
    </div>
  );
});

/* ------------------------------------------------------------------ PinInput */
export function PinInput({
  length = 4,
  value,
  onChange,
  label,
  ariaLabel,
}: {
  length?: number;
  value: string;
  onChange: (v: string) => void;
  label?: string;
  ariaLabel?: string;
}) {
  const refs = useRef<Array<HTMLInputElement | null>>([]);
  const digits = Array.from({ length }, (_, i) => value[i] ?? '');

  function setAt(i: number, d: string) {
    const next = (value.slice(0, i) + d + value.slice(i + 1)).slice(0, length);
    onChange(next.replace(/\D/g, ''));
    if (d && i < length - 1) refs.current[i + 1]?.focus();
  }

  return (
    <div className="ui-field">
      {label && <span className="ui-label">{label}</span>}
      <div className="ui-pin" role="group" aria-label={ariaLabel ?? label ?? 'Code secret'}>
        {digits.map((d, i) => (
          <input
            key={i}
            ref={(el) => (refs.current[i] = el)}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={1}
            value={d}
            aria-label={`Chiffre ${i + 1}`}
            onChange={(e) => setAt(i, e.target.value.replace(/\D/g, '').slice(-1))}
            onKeyDown={(e) => {
              if (e.key === 'Backspace' && !d && i > 0) refs.current[i - 1]?.focus();
            }}
          />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Money / Amount */
export function Money({
  amountMinor,
  currency,
  direction,
  sign,
}: {
  amountMinor: number;
  currency: string;
  direction?: 'in' | 'out';
  sign?: boolean;
}) {
  return (
    <span className={cx('ui-money', direction && `ui-money--${direction}`)}>
      {formatMoney(amountMinor, currency, { sign })}
    </span>
  );
}

export function Amount({ amountMinor, currency }: { amountMinor: number; currency: string }) {
  return (
    <strong style={{ fontSize: 'var(--text-3xl)', fontVariantNumeric: 'tabular-nums' }}>
      {formatMoney(amountMinor, currency)}
    </strong>
  );
}

/* ------------------------------------------------------------------ Badge / Avatar */
export function Badge({
  children,
  tone = 'neutral',
}: {
  children: ReactNode;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
}) {
  return (
    <span className={cx('ui-badge', tone !== 'neutral' && `ui-badge--${tone}`)}>{children}</span>
  );
}

export function Avatar({ name, label }: { name: string; label?: string }) {
  const initials = name
    .split(/\s+/)
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <span className="ui-avatar" aria-label={label ?? name} role="img">
      {initials || '?'}
    </span>
  );
}

/* ------------------------------------------------------------------ Skeleton / EmptyState */
export function Skeleton({ width, height = 16 }: { width?: number | string; height?: number }) {
  return (
    <span
      className="ui-skeleton"
      style={{ display: 'block', width: width ?? '100%', height }}
      aria-hidden
    />
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="ui-empty">
      <strong>{title}</strong>
      {description && <span>{description}</span>}
      {action}
    </div>
  );
}

/* ------------------------------------------------------------------ ListRow */
type ListRowProps = {
  leading?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  trailing?: ReactNode;
  onClick?: () => void;
};
export function ListRow({ leading, title, subtitle, trailing, onClick }: ListRowProps) {
  const Comp = onClick ? 'button' : 'div';
  return (
    <Comp
      className={cx('ui-row', onClick && 'ui-row--button')}
      {...(onClick ? { type: 'button', onClick } : {})}
    >
      {leading}
      <span className="ui-row__body">
        <span className="ui-row__title">{title}</span>
        {subtitle && <span className="ui-row__sub">{subtitle}</span>}
      </span>
      {trailing}
    </Comp>
  );
}

/* ------------------------------------------------------------------ Card */
export function Card(props: HTMLAttributes<HTMLDivElement>) {
  const { className, ...rest } = props;
  return <div className={cx('ui-card', className)} {...rest} />;
}
