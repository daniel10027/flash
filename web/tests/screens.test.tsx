import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DashboardPage } from '@pages/DashboardPage';
import { SendMoneyPage } from '@pages/SendMoneyPage';

function mockFetch(map: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    const key = Object.keys(map).find((k) => url.includes(k));
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify(key ? map[key] : {}),
      json: async () => (key ? map[key] : {}),
    } as Response;
  });
}

function wrap(ui: React.ReactNode, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    mockFetch({
      '/v1/wallets': {
        wallets: [
          {
            id: 'w1',
            currency: 'XOF',
            available_minor: 125_000,
            reserved_minor: 0,
            balance_minor: 125_000,
            status: 'ACTIVE',
          },
        ],
      },
      '/v1/kyc/status': { tier: 0, status: 'UNVERIFIED' },
      '/v1/statement': { lines: [], next_cursor: null },
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe('DashboardPage', () => {
  it('affiche le solde du portefeuille principal', async () => {
    wrap(<DashboardPage />);
    const el = await screen.findByText((tx) => tx.replace(/\D/g, '') === '125000');
    expect(el).toBeInTheDocument();
    // bandeau KYC tier 0
    expect(screen.getByText(/Vérifiez votre identité/)).toBeInTheDocument();
  });
});

describe('SendMoneyPage', () => {
  it('désactive Continuer tant que le formulaire est vide', async () => {
    wrap(<SendMoneyPage />);
    expect(await screen.findByRole('button', { name: 'Continuer' })).toBeDisabled();
  });
});
