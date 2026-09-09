import { beforeEach, describe, expect, it } from 'vitest';
import { act } from '@testing-library/react';
import { usePrivacy } from '@features/layout/privacy';

beforeEach(() => {
  window.localStorage.clear();
  // remet le store dans son état initial (module singleton)
  if (usePrivacy.getState().hidden) act(() => usePrivacy.getState().toggle());
});

describe('usePrivacy', () => {
  it('bascule et persiste dans localStorage', () => {
    expect(usePrivacy.getState().hidden).toBe(false);
    act(() => usePrivacy.getState().toggle());
    expect(usePrivacy.getState().hidden).toBe(true);
    expect(window.localStorage.getItem('flash.hideBalances')).toBe('1');
    act(() => usePrivacy.getState().toggle());
    expect(usePrivacy.getState().hidden).toBe(false);
    expect(window.localStorage.getItem('flash.hideBalances')).toBe('0');
  });
});
