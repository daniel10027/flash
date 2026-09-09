// Assemble les fournisseurs transverses : React Query, i18n, ErrorBoundary, toasts.
import { useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { i18n } from '@shared/i18n';
import { ApiError } from '@shared/api/errors';
import { ErrorBoundary } from './ErrorBoundary';
import { Toaster } from '@shared/ui';

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: (count, error) => {
              if (error instanceof ApiError && error.status < 500) return false;
              return count < 2;
            },
            refetchOnWindowFocus: false,
          },
          mutations: { retry: false },
        },
      }),
  );

  return (
    <ErrorBoundary>
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={client}>
          {children}
          <Toaster />
        </QueryClientProvider>
      </I18nextProvider>
    </ErrorBoundary>
  );
}
