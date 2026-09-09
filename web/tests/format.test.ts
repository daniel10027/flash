import { describe, expect, it } from 'vitest';
import { formatMoney, minorToMajor } from '@shared/i18n/format';

describe('formatage monétaire', () => {
  it('XOF est sans décimale (unité mineure = unité)', () => {
    expect(minorToMajor(1500, 'XOF')).toBe(1500);
    const s = formatMoney(1_250_000, 'XOF');
    expect(s.replace(/\D/g, '')).toBe('1250000');
    expect(s).not.toMatch(/[.,]00/);
  });

  it('EUR a deux décimales (centimes)', () => {
    expect(minorToMajor(1500, 'EUR')).toBe(15);
    expect(formatMoney(1500, 'EUR')).toMatch(/15[.,]00/);
  });

  it('signe optionnel', () => {
    expect(formatMoney(80, 'XOF', { sign: true })).toMatch(/^\+/);
  });
});
