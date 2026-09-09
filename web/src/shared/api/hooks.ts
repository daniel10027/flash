// Couche données : hooks React Query par ressource. Clés centralisées.
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  Card,
  CashOrder,
  Country,
  KycStatus,
  Notification,
  PaymentRequest,
  PhoneNumber,
  SavingsPlan,
  StatementPage,
  TransferReceipt,
  Vault,
  Wallet,
} from './types';

export const qk = {
  wallets: ['wallets'] as const,
  statement: ['statement'] as const,
  kyc: ['kyc', 'status'] as const,
  paymentRequests: ['payment-requests'] as const,
  vault: ['vault'] as const,
  savings: ['savings', 'plans'] as const,
  cards: ['cards'] as const,
  card: (id: string) => ['cards', id] as const,
  phones: ['phones'] as const,
  notifications: ['notifications'] as const,
  operatorTransfers: ['operators', 'transfers'] as const,
  countries: ['reference', 'countries'] as const,
  merchantQr: ['merchant', 'qr'] as const,
};

/* ------------------------------------------------------------------ wallets */
export function useWallets() {
  return useQuery({
    queryKey: qk.wallets,
    queryFn: () => api.get<{ wallets: Wallet[] }>('/v1/wallets'),
    select: (d) => d.wallets,
  });
}

export function usePrimaryWallet() {
  const q = useWallets();
  return { ...q, wallet: q.data?.[0] };
}

/* ------------------------------------------------------------------ statement */
export function useStatement(params?: { limit?: number }) {
  return useInfiniteQuery({
    queryKey: [...qk.statement, params?.limit ?? 25],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.get<StatementPage>('/v1/statement', {
        limit: params?.limit ?? 25,
        cursor: pageParam,
      }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useReceipt(reference: string | null) {
  return useQuery({
    queryKey: ['receipts', reference],
    enabled: !!reference,
    queryFn: () => api.get<Record<string, unknown>>(`/v1/receipts/${reference}`),
  });
}

/* ------------------------------------------------------------------ kyc */
export function useKycStatus() {
  return useQuery({
    queryKey: qk.kyc,
    queryFn: () => api.get<KycStatus>('/v1/kyc/status'),
  });
}

/* ------------------------------------------------------------------ transfers */
export function useSendTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      recipient_phone_number: string;
      amount_minor: number;
      note?: string;
      country?: string;
    }) => api.post<TransferReceipt>('/v1/transfers', body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.wallets });
      void qc.invalidateQueries({ queryKey: qk.statement });
    },
  });
}

export function useCancelTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/v1/transfers/${id}/cancel`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.wallets });
      void qc.invalidateQueries({ queryKey: qk.statement });
    },
  });
}

/* ------------------------------------------------------------------ payment requests */
export function usePaymentRequests() {
  return useQuery({
    queryKey: qk.paymentRequests,
    queryFn: () => api.get<{ requests: PaymentRequest[] }>('/v1/payment-requests'),
    select: (d) => d.requests ?? [],
  });
}

export function usePaymentRequestActions() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: qk.paymentRequests });
  return {
    create: useMutation({
      mutationFn: (b: { payer_phone_number: string; amount_minor: number; note?: string }) =>
        api.post<PaymentRequest>('/v1/payment-requests', b),
      onSuccess: invalidate,
    }),
    accept: useMutation({
      mutationFn: (id: string) => api.post(`/v1/payment-requests/${id}/accept`),
      onSuccess: () => {
        void invalidate();
        void qc.invalidateQueries({ queryKey: qk.wallets });
      },
    }),
    decline: useMutation({
      mutationFn: (id: string) => api.post(`/v1/payment-requests/${id}/decline`),
      onSuccess: invalidate,
    }),
    cancel: useMutation({
      mutationFn: (id: string) => api.post(`/v1/payment-requests/${id}/cancel`),
      onSuccess: invalidate,
    }),
  };
}

/* ------------------------------------------------------------------ merchant pay */
export function useMerchantQr() {
  return useQuery({
    queryKey: qk.merchantQr,
    queryFn: () => api.get<{ static_qr_payload: string }>('/v1/merchant/qr'),
    retry: false,
  });
}

export function usePayMerchant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { merchant_id: string; amount_minor?: number; charge_id?: string }) =>
      api.post<TransferReceipt>('/v1/merchant-payments', b),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.wallets });
      void qc.invalidateQueries({ queryKey: qk.statement });
    },
  });
}

/* ------------------------------------------------------------------ cash */
export function useCreateWithdrawal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (amount_minor: number) => api.post<CashOrder>('/v1/withdrawals', { amount_minor }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.wallets }),
  });
}
export function useCancelWithdrawal() {
  return useMutation({ mutationFn: (id: string) => api.post(`/v1/withdrawals/${id}/cancel`) });
}

/* ------------------------------------------------------------------ operators */
export function useOperatorTransfers() {
  return useQuery({
    queryKey: qk.operatorTransfers,
    queryFn: () => api.get<{ transfers: unknown[] }>('/v1/operators/transfers'),
    select: (d) => d.transfers ?? [],
  });
}
export function useOperatorPayout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { operator: string; msisdn: string; amount_minor: number }) =>
      api.post('/v1/operators/payouts', b),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.wallets });
      void qc.invalidateQueries({ queryKey: qk.operatorTransfers });
    },
  });
}
export function useOperatorTopup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { operator: string; msisdn: string; amount_minor: number }) =>
      api.post('/v1/operators/topups', b),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.operatorTransfers }),
  });
}

/* ------------------------------------------------------------------ vault */
export function useVault() {
  return useQuery({ queryKey: qk.vault, queryFn: () => api.get<Vault>('/v1/vault') });
}
export function useVaultActions() {
  const qc = useQueryClient();
  const inv = () => {
    void qc.invalidateQueries({ queryKey: qk.vault });
    void qc.invalidateQueries({ queryKey: qk.wallets });
  };
  return {
    create: useMutation({
      mutationFn: (b: { name: string; goal_minor?: number; locked_until?: string }) =>
        api.post('/v1/vault/pockets', b),
      onSuccess: inv,
    }),
    update: useMutation({
      mutationFn: ({ id, ...b }: { id: string; name?: string; goal_minor?: number }) =>
        api.patch(`/v1/vault/pockets/${id}`, b),
      onSuccess: inv,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api.del(`/v1/vault/pockets/${id}`),
      onSuccess: inv,
    }),
    deposit: useMutation({
      mutationFn: ({ id, amount_minor }: { id: string; amount_minor: number }) =>
        api.post(`/v1/vault/pockets/${id}/deposit`, { amount_minor }),
      onSuccess: inv,
    }),
    withdraw: useMutation({
      mutationFn: ({ id, amount_minor }: { id: string; amount_minor: number }) =>
        api.post(`/v1/vault/pockets/${id}/withdraw`, { amount_minor }),
      onSuccess: inv,
    }),
  };
}

/* ------------------------------------------------------------------ savings */
export function useSavingsPlans() {
  return useQuery({
    queryKey: qk.savings,
    queryFn: () => api.get<{ plans: SavingsPlan[] }>('/v1/savings/plans'),
    select: (d) => d.plans ?? [],
  });
}
export function useSavingsActions() {
  const qc = useQueryClient();
  const inv = () => {
    void qc.invalidateQueries({ queryKey: qk.savings });
    void qc.invalidateQueries({ queryKey: qk.wallets });
  };
  return {
    open: useMutation({
      mutationFn: (b: Record<string, unknown>) => api.post('/v1/savings/plans', b),
      onSuccess: inv,
    }),
    deposit: useMutation({
      mutationFn: ({ id, amount_minor }: { id: string; amount_minor: number }) =>
        api.post(`/v1/savings/plans/${id}/deposit`, { amount_minor }),
      onSuccess: inv,
    }),
    withdraw: useMutation({
      mutationFn: ({ id, amount_minor }: { id: string; amount_minor: number }) =>
        api.post(`/v1/savings/plans/${id}/withdraw`, { amount_minor }),
      onSuccess: inv,
    }),
    close: useMutation({
      mutationFn: (id: string) => api.post(`/v1/savings/plans/${id}/close`),
      onSuccess: inv,
    }),
  };
}

/* ------------------------------------------------------------------ cards */
export function useCards() {
  return useQuery({
    queryKey: qk.cards,
    queryFn: () => api.get<{ cards: Card[] }>('/v1/cards'),
    select: (d) => d.cards ?? [],
  });
}
export function useCardActions() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: qk.cards });
  return {
    issue: useMutation({
      mutationFn: (b: Record<string, unknown>) => api.post<Card>('/v1/cards', b),
      onSuccess: inv,
    }),
    freeze: useMutation({
      mutationFn: (id: string) => api.post(`/v1/cards/${id}/freeze`),
      onSuccess: inv,
    }),
    unfreeze: useMutation({
      mutationFn: (id: string) => api.post(`/v1/cards/${id}/unfreeze`),
      onSuccess: inv,
    }),
    close: useMutation({
      mutationFn: (id: string) => api.post(`/v1/cards/${id}/close`),
      onSuccess: inv,
    }),
    limits: useMutation({
      mutationFn: ({
        id,
        ...b
      }: {
        id: string;
        daily_limit_minor?: number;
        monthly_limit_minor?: number;
      }) => api.patch(`/v1/cards/${id}/limits`, b),
      onSuccess: inv,
    }),
    reveal: useMutation({
      mutationFn: (id: string) =>
        api.post<{ pan: string; cvv: string; expiry: string }>(`/v1/cards/${id}/reveal`),
    }),
  };
}

/* ------------------------------------------------------------------ phones */
export function usePhones() {
  return useQuery({
    queryKey: qk.phones,
    queryFn: () => api.get<{ phone_numbers: PhoneNumber[] }>('/v1/phones'),
    select: (d) => d.phone_numbers ?? [],
  });
}
export function usePhoneActions() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: qk.phones });
  return {
    add: useMutation({
      mutationFn: (b: { phone_number: string; country: string }) => api.post('/v1/phones', b),
      onSuccess: inv,
    }),
    verify: useMutation({
      mutationFn: (b: { phone_number: string; code: string }) => api.post('/v1/phones/verify', b),
      onSuccess: inv,
    }),
    setPrimary: useMutation({
      mutationFn: (phone_number: string) => api.post('/v1/phones/primary', { phone_number }),
      onSuccess: inv,
    }),
    remove: useMutation({
      mutationFn: (phone_number: string) =>
        api.del(`/v1/phones?phone_number=${encodeURIComponent(phone_number)}`),
      onSuccess: inv,
    }),
  };
}

/* ------------------------------------------------------------------ notifications */
export function useNotifications() {
  return useQuery({
    queryKey: qk.notifications,
    queryFn: () => api.get<{ notifications: Notification[]; unread?: number }>('/v1/notifications'),
  });
}
export function useNotificationActions() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: qk.notifications });
  return {
    markRead: useMutation({
      mutationFn: (id: string) => api.post(`/v1/notifications/${id}/read`),
      onSuccess: inv,
    }),
    markAll: useMutation({
      mutationFn: () => api.post('/v1/notifications/read-all'),
      onSuccess: inv,
    }),
  };
}

/* ------------------------------------------------------------------ reference */
export function useCountries() {
  return useQuery({
    queryKey: qk.countries,
    queryFn: () => api.get<{ countries: Country[] }>('/v1/reference/countries'),
    staleTime: 60 * 60 * 1000,
    select: (d) => d.countries ?? [],
  });
}
