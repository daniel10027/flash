import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import {
  useAdminAccount,
  useAdminAccounts,
  useAmlAlerts,
  useAudit,
  useJournal,
  useKycCase,
  useKycDocumentUrl,
  useKycQueue,
  useKycReview,
  useLimitRules,
  usePricingRules,
  useReferenceActions,
  useReviewAlert,
  useTrialBalance,
  useVerifyChain,
} from '@features/admin/hooks';
import { useAdminAuth } from '@features/admin/client';

const calls: string[] = [];
let body: unknown = {};

beforeEach(() => {
  calls.length = 0;
  body = {};
  useAdminAuth.getState().setKey('k');
  // jsdom n'implémente pas createObjectURL ; on garde `new URL()` intact.
  URL.createObjectURL = vi.fn(() => 'blob:mock') as typeof URL.createObjectURL;
  URL.revokeObjectURL = vi.fn() as typeof URL.revokeObjectURL;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      calls.push(input.toString());
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(body),
        json: async () => body,
        blob: async () => new Blob(['x'], { type: 'image/png' }),
      } as Response;
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  useAdminAuth.getState().setKey(null);
});

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const lastCall = () => calls.at(-1) ?? '';

describe('admin/hooks — requêtes', () => {
  it('useAdminAccounts : désactivé sous 2 caractères, actif au-delà', async () => {
    body = { accounts: [{ user_id: 'u1' }] };
    const { result, rerender } = renderHook(({ q }) => useAdminAccounts(q), {
      wrapper: wrapper(),
      initialProps: { q: 'a' },
    });
    expect(result.current.fetchStatus).toBe('idle');
    rerender({ q: 'abcd' });
    await waitFor(() => expect(result.current.data).toEqual([{ user_id: 'u1' }]));
    expect(lastCall()).toContain('/v1/admin/accounts');
  });

  const cases: Array<[string, () => { isFetched: boolean }, string]> = [
    ['useAdminAccount', () => useAdminAccount('u1'), '/v1/admin/accounts/u1'],
    ['useKycQueue', () => useKycQueue('PENDING'), '/v1/admin/kyc/submissions'],
    ['useKycCase', () => useKycCase('c1'), '/v1/admin/kyc/submissions/c1'],
    ['useAmlAlerts', () => useAmlAlerts('OPEN'), '/v1/admin/compliance/alerts'],
    ['usePricingRules', () => usePricingRules(), '/v1/admin/reference/pricing'],
    ['useLimitRules', () => useLimitRules(), '/v1/admin/reference/limits'],
    ['useTrialBalance', () => useTrialBalance('2026-01-01'), '/v1/admin/reports/trial-balance'],
    ['useJournal', () => useJournal('2026-01-01', '2026-02-01'), '/v1/admin/reports/journal'],
    ['useAudit', () => useAudit({ actor: 'x' }), '/v1/admin/audit'],
  ];
  it.each(cases)('%s appelle son endpoint', async (_name, hook, path) => {
    const { result } = renderHook(hook, { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isFetched).toBe(true));
    expect(lastCall()).toContain(path);
  });

  it('useKycQueue et useAmlAlerts passent le filtre de statut', async () => {
    renderHook(() => useKycQueue('APPROVED'), { wrapper: wrapper() });
    await waitFor(() => expect(lastCall()).toContain('status=APPROVED'));
    renderHook(() => useAmlAlerts('all'), { wrapper: wrapper() });
    await waitFor(() => expect(lastCall()).toContain('/v1/admin/compliance/alerts'));
  });
});

describe('admin/hooks — mutations', () => {
  it('useKycReview POST review', async () => {
    const { result } = renderHook(() => useKycReview(), { wrapper: wrapper() });
    await result.current.mutateAsync({ case_id: 'c1', approve: true });
    expect(lastCall()).toContain('/v1/admin/kyc/submissions/c1/review');
  });

  it('useReviewAlert POST review d’alerte', async () => {
    const { result } = renderHook(() => useReviewAlert(), { wrapper: wrapper() });
    await result.current.mutateAsync({ alert_id: 'a1', decision: 'clear', note: 'ok' });
    expect(lastCall()).toContain('/v1/admin/compliance/alerts/a1/review');
  });

  it('useReferenceActions : setPricing / setLimit / reload', async () => {
    const { result } = renderHook(() => useReferenceActions(), { wrapper: wrapper() });
    await result.current.setPricing.mutateAsync({
      code: 'CI',
      operation: 'P2P',
      percent_bps: 80,
      currency: 'XOF',
    });
    expect(lastCall()).toContain('/v1/admin/reference/pricing/CI/P2P');
    await result.current.setLimit.mutateAsync({
      code: 'CI',
      tier: 1,
      operation: 'P2P',
      currency: 'XOF',
      daily_minor: 100,
    });
    expect(lastCall()).toContain('/v1/admin/reference/limits/CI/1/P2P');
    await result.current.reload.mutateAsync();
    expect(lastCall()).toContain('/v1/admin/reference/reload');
  });

  it('useVerifyChain GET verify', async () => {
    const { result } = renderHook(() => useVerifyChain(), { wrapper: wrapper() });
    await result.current.mutateAsync();
    expect(lastCall()).toContain('/v1/admin/audit/verify');
  });
});

describe('useKycDocumentUrl', () => {
  it('inactif sans caseId/kind, actif ensuite', async () => {
    const { result, rerender } = renderHook(
      ({ c, k }: { c: string | null; k: string | null }) => useKycDocumentUrl(c, k),
      {
        wrapper: wrapper(),
        initialProps: { c: null, k: null } as { c: string | null; k: string | null },
      },
    );
    expect(result.current.url).toBeNull();
    rerender({ c: 'c1', k: 'ID_FRONT' });
    await waitFor(() => expect(result.current.url).toBe('blob:mock'));
    expect(lastCall()).toContain('/v1/admin/kyc/submissions/c1/documents/ID_FRONT');
  });
});
