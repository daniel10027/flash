import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import {
  useAgent,
  useAgentActions,
  useAgentCustomers,
  useAgentOperations,
  useIsAgent,
} from '@features/agent/hooks';
import { useDeviceActions, useDevices } from '@features/auth/hooks';
import {
  confirmPinReset,
  changePin,
  listDevices,
  login,
  register,
  requestPinReset,
  resendOtp,
  revokeDevice,
  verifyOtp,
} from '@features/auth/api';

/* ------------------------------------------------------------------ fetch mock */
type Handler = (url: string, init: RequestInit) => { status?: number; body?: unknown } | undefined;
let handler: Handler = () => ({ body: {} });
const calls: Array<{ url: string; init: RequestInit }> = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = typeof input === 'string' ? input : input.toString();
      calls.push({ url, init });
      const res = handler(url, init) ?? { body: {} };
      const status = res.status ?? 200;
      return {
        ok: status < 400,
        status,
        text: async () => (res.body === undefined ? '' : JSON.stringify(res.body)),
        json: async () => res.body ?? {},
        blob: async () => new Blob([JSON.stringify(res.body ?? {})], { type: 'image/png' }),
      } as Response;
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  handler = () => ({ body: {} });
});

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

/* ------------------------------------------------------------------ agent */
describe('agent/hooks', () => {
  it('useAgent charge le profil et useIsAgent devient vrai', async () => {
    handler = (url) =>
      url.includes('/v1/agent')
        ? {
            body: {
              agent_id: 'a1',
              status: 'ACTIVE',
              float_available_minor: 5000,
              currency: 'XOF',
            },
          }
        : undefined;
    const { result } = renderHook(() => ({ agent: useAgent(), isAgent: useIsAgent() }), {
      wrapper: wrapper(),
    });
    await waitFor(() => expect(result.current.agent.isSuccess).toBe(true));
    expect(result.current.agent.data?.agent_id).toBe('a1');
    expect(result.current.isAgent).toBe(true);
  });

  it('useAgentCustomers est désactivé sous 3 caractères', async () => {
    const { result, rerender } = renderHook(({ q }) => useAgentCustomers(q), {
      wrapper: wrapper(),
      initialProps: { q: 'ab' },
    });
    expect(result.current.fetchStatus).toBe('idle');
    handler = () => ({ body: { customers: [{ id: 'c1' }] } });
    rerender({ q: 'abc' });
    await waitFor(() => expect(result.current.data).toEqual([{ id: 'c1' }]));
  });

  it('useAgentOperations liste les opérations', async () => {
    handler = () => ({ body: { operations: [{ id: 'o1' }] } });
    const { result } = renderHook(() => useAgentOperations(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data).toEqual([{ id: 'o1' }]));
  });

  it('useAgentActions cible toutes les routes agent', async () => {
    const { result } = renderHook(() => useAgentActions(), { wrapper: wrapper() });
    await result.current.deposit.mutateAsync({
      client_phone_number: '+225070',
      amount_minor: 1000,
    });
    expect(calls.at(-1)!.url).toContain('/v1/agent/deposits');
    expect(calls.at(-1)!.init.method).toBe('POST');
    await result.current.confirmWithdrawal.mutateAsync({ code: 'ABC123' });
    expect(calls.at(-1)!.url).toContain('/v1/agent/withdrawals/confirm');
    await result.current.topupFloat.mutateAsync(5000);
    expect(calls.at(-1)!.url).toContain('/v1/agent/float/topup');
    await result.current.withdrawFloat.mutateAsync(2000);
    expect(calls.at(-1)!.url).toContain('/v1/agent/float/withdraw');
    await result.current.payoutCommission.mutateAsync();
    expect(calls.at(-1)!.url).toContain('/v1/agent/commission/payout');
  });
});

/* ------------------------------------------------------------------ auth/api */
describe('auth/api', () => {
  it('login renvoie authenticated quand un access_token est présent', async () => {
    handler = () => ({ body: { access_token: 'at', refresh_token: 'rt' } });
    const res = await login({ phone_number: '+225', country: 'CI', pin: '1397' });
    expect(res.kind).toBe('authenticated');
  });

  it('login renvoie otp_required sinon', async () => {
    handler = () => ({ body: {} });
    const res = await login({ phone_number: '+225', country: 'CI', pin: '1397' });
    expect(res.kind).toBe('otp_required');
  });

  it('register / verifyOtp / resendOtp ciblent les bons endpoints', async () => {
    handler = () => ({ body: { access_token: 'at', refresh_token: 'rt' } });
    await register({ phone_number: '+225', country: 'CI', pin: '1397' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/register');
    const tokens = await verifyOtp({ phone_number: '+225', country: 'CI', code: '000000' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/verify-otp');
    expect(JSON.parse(String(calls.at(-1)!.init.body))).toHaveProperty('device_id');
    expect(tokens.access_token).toBe('at');
    await resendOtp({ phone_number: '+225', country: 'CI' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/resend-otp');
  });

  it('requestPinReset / confirmPinReset / changePin ciblent les bons endpoints', async () => {
    await requestPinReset({ phone_number: '+225', country: 'CI' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/reset-pin/request');
    await confirmPinReset({ phone_number: '+225', country: 'CI', code: '000000', new_pin: '2468' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/reset-pin/confirm');
    await changePin({ current_pin: '1397', new_pin: '2468' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/change-pin');
  });

  it('listDevices déballe { devices } et revokeDevice fait un DELETE', async () => {
    handler = (url) =>
      url.includes('/v1/auth/devices')
        ? {
            body: {
              devices: [{ device_id: 'd1', current: true, first_seen: null, last_seen: null }],
            },
          }
        : undefined;
    expect(await listDevices()).toHaveLength(1);
    await revokeDevice('d2');
    expect(calls.at(-1)!.url).toContain('/v1/auth/devices/d2');
    expect(calls.at(-1)!.init.method).toBe('DELETE');
  });
});

/* ------------------------------------------------------------------ auth/hooks */
describe('auth/hooks', () => {
  it('useDevices récupère la liste', async () => {
    handler = () => ({
      body: { devices: [{ device_id: 'd1', current: true, first_seen: null, last_seen: null }] },
    });
    const { result } = renderHook(() => useDevices(), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.data).toHaveLength(1));
  });

  it('useDeviceActions.changePin et revoke appellent l’API', async () => {
    const { result } = renderHook(() => useDeviceActions(), { wrapper: wrapper() });
    await result.current.changePin.mutateAsync({ current_pin: '1397', new_pin: '2468' });
    expect(calls.at(-1)!.url).toContain('/v1/auth/change-pin');
    await result.current.revoke.mutateAsync('d9');
    expect(calls.at(-1)!.url).toContain('/v1/auth/devices/d9');
  });
});
