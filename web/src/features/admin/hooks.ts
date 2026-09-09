// Back-office — hooks React Query sur l'API `/v1/admin/*` (clé `X-Admin-Key`).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminFetch } from './client';

export const adminQk = {
  accounts: (q: string) => ['admin', 'accounts', q] as const,
  account: (id: string) => ['admin', 'account', id] as const,
  alerts: (status: string) => ['admin', 'alerts', status] as const,
  pricing: ['admin', 'pricing'] as const,
  limits: ['admin', 'limits'] as const,
  audit: (params: string) => ['admin', 'audit', params] as const,
};

/* ------------------------------------------------------------------ WEB-041 */
export function useAdminAccounts(query: string) {
  return useQuery({
    queryKey: adminQk.accounts(query),
    enabled: query.trim().length >= 2,
    queryFn: () =>
      adminFetch<{ accounts: Array<Record<string, unknown>> }>('/v1/admin/accounts', {
        query: { q: query.trim() },
      }),
    select: (d) => d.accounts ?? [],
  });
}

export function useAdminAccount(id: string | null) {
  return useQuery({
    queryKey: adminQk.account(id ?? ''),
    enabled: !!id,
    queryFn: () => adminFetch<Record<string, unknown>>(`/v1/admin/accounts/${id}`),
  });
}

export function useAccountActions(id: string) {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: ['admin', 'account', id] });
  return {
    freeze: useMutation({
      mutationFn: (b: { freeze: boolean; reason: string }) =>
        adminFetch(`/v1/admin/accounts/${id}/freeze`, { method: 'POST', body: b }),
      onSuccess: inv,
    }),
    addNote: useMutation({
      mutationFn: (note: string) =>
        adminFetch(`/v1/admin/accounts/${id}/notes`, { method: 'POST', body: { note } }),
      onSuccess: inv,
    }),
    forceReversal: useMutation({
      mutationFn: (b: { reference: string; reason: string }) =>
        adminFetch('/v1/admin/transactions/force-reversal', { method: 'POST', body: b }),
      onSuccess: inv,
    }),
  };
}

export function useAccountNotes(id: string | null) {
  return useQuery({
    queryKey: ['admin', 'notes', id],
    enabled: !!id,
    queryFn: () =>
      adminFetch<{ notes: Array<Record<string, unknown>> }>(`/v1/admin/accounts/${id}/notes`),
    select: (d) => d.notes ?? [],
  });
}

/* ------------------------------------------------------------------ WEB-042 */
export function useKycReview() {
  return useMutation({
    mutationFn: (b: { case_id: string; approve: boolean; reason?: string }) =>
      adminFetch(`/v1/admin/kyc/submissions/${b.case_id}/review`, {
        method: 'POST',
        body: { approve: b.approve, reason: b.reason },
      }),
  });
}

/* ------------------------------------------------------------------ WEB-043 */
export function useAmlAlerts(status: string) {
  return useQuery({
    queryKey: adminQk.alerts(status),
    queryFn: () =>
      adminFetch<{ alerts: Array<Record<string, unknown>> }>('/v1/admin/compliance/alerts', {
        query: { status: status === 'all' ? undefined : status },
      }),
    select: (d) => d.alerts ?? [],
  });
}

export function useReviewAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { alert_id: string; decision: 'clear' | 'escalate'; note: string }) =>
      adminFetch(`/v1/admin/compliance/alerts/${b.alert_id}/review`, {
        method: 'POST',
        body: { decision: b.decision, note: b.note },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'alerts'] }),
  });
}

/* ------------------------------------------------------------------ WEB-044 */
export function usePricingRules() {
  return useQuery({
    queryKey: adminQk.pricing,
    queryFn: () =>
      adminFetch<{ rules: Array<Record<string, unknown>> }>('/v1/admin/reference/pricing'),
    select: (d) => d.rules ?? [],
  });
}
export function useLimitRules() {
  return useQuery({
    queryKey: adminQk.limits,
    queryFn: () =>
      adminFetch<{ rules: Array<Record<string, unknown>> }>('/v1/admin/reference/limits'),
    select: (d) => d.rules ?? [],
  });
}
export function useReferenceActions() {
  const qc = useQueryClient();
  const inv = () => {
    void qc.invalidateQueries({ queryKey: adminQk.pricing });
    void qc.invalidateQueries({ queryKey: adminQk.limits });
  };
  return {
    setPricing: useMutation({
      mutationFn: (b: { code: string; operation: string; percent_bps: number; currency: string }) =>
        adminFetch(`/v1/admin/reference/pricing/${b.code}/${b.operation}`, {
          method: 'PUT',
          body: { percent_bps: b.percent_bps, currency: b.currency },
        }),
      onSuccess: inv,
    }),
    setLimit: useMutation({
      mutationFn: (b: {
        code: string;
        tier: number;
        operation: string;
        currency: string;
        per_tx_minor?: number;
        daily_minor?: number;
      }) =>
        adminFetch(`/v1/admin/reference/limits/${b.code}/${b.tier}/${b.operation}`, {
          method: 'PUT',
          body: { currency: b.currency, per_tx_minor: b.per_tx_minor, daily_minor: b.daily_minor },
        }),
      onSuccess: inv,
    }),
    reload: useMutation({
      mutationFn: () => adminFetch('/v1/admin/reference/reload', { method: 'POST' }),
    }),
  };
}

/* ------------------------------------------------------------------ WEB-045 */
export function useTrialBalance(asOf: string) {
  return useQuery({
    queryKey: ['admin', 'trial-balance', asOf],
    enabled: !!asOf,
    queryFn: () =>
      adminFetch<Record<string, unknown>>('/v1/admin/reports/trial-balance', {
        query: { as_of: asOf },
      }),
  });
}
export function useJournal(start: string, end: string) {
  return useQuery({
    queryKey: ['admin', 'journal', start, end],
    enabled: !!start && !!end,
    queryFn: () =>
      adminFetch<{ entries: Array<Record<string, unknown>> }>('/v1/admin/reports/journal', {
        query: { start, end },
      }),
    select: (d) => d.entries ?? [],
  });
}

/* ------------------------------------------------------------------ WEB-046 */
export function useAudit(params: { actor?: string; action?: string; verify?: boolean }) {
  const key = JSON.stringify(params);
  return useQuery({
    queryKey: adminQk.audit(key),
    queryFn: () =>
      adminFetch<{ entries: Array<Record<string, unknown>>; chain?: Record<string, unknown> }>(
        '/v1/admin/audit',
        {
          query: {
            actor: params.actor || undefined,
            action: params.action || undefined,
            verify: params.verify ? '1' : undefined,
          },
        },
      ),
  });
}
export function useVerifyChain() {
  return useMutation({
    mutationFn: () => adminFetch<Record<string, unknown>>('/v1/admin/audit/verify'),
  });
}
