// WEB-007 — formatage monétaire / date par pays. Les montants de l'API sont en
// **unité mineure** ; XOF / XAF n'ont pas de décimale.

import { i18n } from './index';

const ZERO_DECIMAL = new Set(['XOF', 'XAF', 'JPY', 'KRW']);

export function minorToMajor(amountMinor: number, currency: string): number {
  return ZERO_DECIMAL.has(currency) ? amountMinor : amountMinor / 100;
}

export function formatMoney(
  amountMinor: number,
  currency: string,
  opts: { sign?: boolean } = {},
): string {
  const value = minorToMajor(amountMinor, currency);
  const fractionDigits = ZERO_DECIMAL.has(currency) ? 0 : 2;
  const formatted = new Intl.NumberFormat(i18n.language || 'fr', {
    style: 'currency',
    currency,
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay: opts.sign ? 'always' : 'auto',
  }).format(value);
  return formatted;
}

export function formatDate(iso: string, style: 'short' | 'long' = 'short'): string {
  const d = new Date(iso);
  return new Intl.DateTimeFormat(i18n.language || 'fr', {
    dateStyle: style === 'long' ? 'long' : 'medium',
    timeStyle: style === 'long' ? 'short' : undefined,
  }).format(d);
}

export function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const rtf = new Intl.RelativeTimeFormat(i18n.language || 'fr', { numeric: 'auto' });
  const min = Math.round(diffMs / 60000);
  if (Math.abs(min) < 60) return rtf.format(-min, 'minute');
  const hours = Math.round(min / 60);
  if (Math.abs(hours) < 24) return rtf.format(-hours, 'hour');
  return rtf.format(-Math.round(hours / 24), 'day');
}
