// Espace agent — hooks React Query. L'agent est un utilisateur authentifié dont
// `GET /v1/agent` répond ; les écrans sont accessibles depuis la nav si c'est le cas.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@shared/api/client';

export const agentQk = {
  me: ['agent'] as const,
  customers: (q: string) => ['agent', 'customers', q] as const,
  operations: ['agent', 'operations'] as const,
};

export type AgentProfile = {
  agent_id: string;
  status: string;
  float_available_minor: number;
  currency: string;
  commission_earned_minor: number;
  commission_paid_minor: number;
  commission_owed_minor: number;
  parent_agent_id?: string | null;
  sub_agents?: Array<{ agent_id: string; label?: string; float_available_minor?: number }>;
  [k: string]: unknown;
};

export function useAgent() {
  return useQuery({
    queryKey: agentQk.me,
    queryFn: () => api.get<AgentProfile>('/v1/agent'),
    retry: false,
  });
}

/** Vrai si le compte courant a un espace agent (utilisé pour afficher l'onglet). */
export function useIsAgent() {
  const q = useAgent();
  return q.isSuccess;
}

export function useAgentCustomers(query: string) {
  return useQuery({
    queryKey: agentQk.customers(query),
    enabled: query.trim().length >= 3,
    queryFn: () =>
      api.get<{ customers: Array<Record<string, unknown>> }>('/v1/agent/customers', {
        q: query.trim(),
      }),
    select: (d) => d.customers ?? [],
  });
}

export function useAgentOperations() {
  return useQuery({
    queryKey: agentQk.operations,
    queryFn: () => api.get<{ operations: Array<Record<string, unknown>> }>('/v1/agent/operations'),
    select: (d) => d.operations ?? [],
  });
}

export function useAgentActions() {
  const qc = useQueryClient();
  const inv = () => {
    void qc.invalidateQueries({ queryKey: agentQk.me });
    void qc.invalidateQueries({ queryKey: agentQk.operations });
  };
  return {
    deposit: useMutation({
      mutationFn: (b: { client_phone_number: string; amount_minor: number }) =>
        api.post('/v1/agent/deposits', b),
      onSuccess: inv,
    }),
    confirmWithdrawal: useMutation({
      mutationFn: (b: { code: string; amount_minor?: number }) =>
        api.post('/v1/agent/withdrawals/confirm', b),
      onSuccess: inv,
    }),
    topupFloat: useMutation({
      mutationFn: (amount_minor: number) => api.post('/v1/agent/float/topup', { amount_minor }),
      onSuccess: inv,
    }),
    withdrawFloat: useMutation({
      mutationFn: (amount_minor: number) => api.post('/v1/agent/float/withdraw', { amount_minor }),
      onSuccess: inv,
    }),
    payoutCommission: useMutation({
      mutationFn: () => api.post('/v1/agent/commission/payout'),
      onSuccess: inv,
    }),
  };
}
