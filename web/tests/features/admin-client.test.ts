import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { adminFetch, adminFetchBlob, useAdminAuth } from '@features/admin/client';
import { ApiError } from '@shared/api/errors';

const calls: Array<{ url: string; init: RequestInit }> = [];
let next: { status?: number; body?: unknown; contentType?: string } = { body: {} };

beforeEach(() => {
  calls.length = 0;
  next = { body: {} };
  useAdminAuth.getState().setKey('secret-key');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      calls.push({ url: input.toString(), init });
      const status = next.status ?? 200;
      return {
        ok: status < 400,
        status,
        text: async () => (next.body === undefined ? '' : JSON.stringify(next.body)),
        json: async () => next.body ?? {},
        blob: async () =>
          new Blob([String(next.body ?? '')], { type: next.contentType ?? 'image/png' }),
      } as Response;
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  useAdminAuth.getState().setKey(null);
});

describe('adminFetch', () => {
  it('joint la clé X-Admin-Key', async () => {
    await adminFetch('/v1/admin/accounts', { query: { q: 'x' } });
    const headers = calls[0]!.init.headers as Record<string, string>;
    expect(headers['X-Admin-Key']).toBe('secret-key');
    expect(calls[0]!.url).toContain('q=x');
  });

  it('lève ApiError sur réponse non-ok', async () => {
    next = { status: 403, body: { code: 'FORBIDDEN', message: 'non' } };
    await expect(adminFetch('/v1/admin/accounts')).rejects.toBeInstanceOf(ApiError);
  });

  it('renvoie undefined sur 204', async () => {
    next = { status: 204, body: undefined };
    await expect(adminFetch('/v1/admin/x', { method: 'POST' })).resolves.toBeUndefined();
  });

  it('raw:true renvoie le texte brut', async () => {
    next = { body: 'a;b;c' };
    const csv = await adminFetch<string>('/v1/admin/reports/str', { raw: true });
    expect(csv).toBe('"a;b;c"');
  });
});

describe('adminFetchBlob', () => {
  it('renvoie un Blob et envoie la clé', async () => {
    next = { body: 'PNGDATA', contentType: 'image/png' };
    const blob = await adminFetchBlob('/v1/admin/kyc/submissions/c1/documents/ID_FRONT');
    expect(blob).toBeInstanceOf(Blob);
    const headers = calls[0]!.init.headers as Record<string, string>;
    expect(headers['X-Admin-Key']).toBe('secret-key');
  });

  it('lève ApiError si la réponse échoue', async () => {
    next = { status: 404, body: {} };
    await expect(adminFetchBlob('/v1/admin/kyc/x/documents/y')).rejects.toBeInstanceOf(ApiError);
  });
});
