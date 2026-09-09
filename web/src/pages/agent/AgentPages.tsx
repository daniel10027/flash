// WEB-033..039 — espace agent.
import { useMemo, useState } from 'react';
import { Badge, Button, Card, EmptyState, Input, ListRow, Money, Skeleton, Tabs } from '@shared/ui';
import { AmountField, PageHeader, Receipt } from '@features/common/kit';
import { toast } from '@shared/ui';
import { formatDate, formatMoney } from '@shared/i18n/format';
import {
  useAgent,
  useAgentActions,
  useAgentCustomers,
  useAgentOperations,
} from '@features/agent/hooks';

/* ------------------------------------------------------------- WEB-033 */
export function AgentDashboardPage() {
  const { data, isLoading } = useAgent();
  const a = useAgentActions();
  const cur = data?.currency ?? 'XOF';

  if (isLoading) return <Skeleton height={160} />;
  if (!data)
    return (
      <div>
        <PageHeader title="Espace agent" back={false} />
        <Card>
          <EmptyState title="Compte agent non activé" />
        </Card>
      </div>
    );

  return (
    <div>
      <PageHeader title="Espace agent" back={false} />
      <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
        <Card>
          <span className="ui-hint">Liquidité disponible (float)</span>
          <p style={{ fontSize: 'var(--text-3xl)', fontWeight: 'var(--weight-semibold)' }}>
            {formatMoney(data.float_available_minor, cur)}
          </p>
          <Badge tone={data.status === 'ACTIVE' ? 'success' : 'warning'}>{data.status}</Badge>
        </Card>
        <Card style={{ display: 'grid', gap: 'var(--space-2)' }}>
          <Row k="Commissions gagnées" v={formatMoney(data.commission_earned_minor, cur)} />
          <Row k="Commissions versées" v={formatMoney(data.commission_paid_minor, cur)} />
          <Row k="Reste à percevoir" v={formatMoney(data.commission_owed_minor, cur)} strong />
          <Button
            size="sm"
            disabled={data.commission_owed_minor <= 0}
            loading={a.payoutCommission.isPending}
            onClick={() => a.payoutCommission.mutate()}
          >
            Percevoir mes commissions
          </Button>
        </Card>
        {data.sub_agents && data.sub_agents.length > 0 && (
          <Card style={{ padding: 0 }}>
            {data.sub_agents.map((s) => (
              <ListRow
                key={s.agent_id}
                title={s.label ?? s.agent_id}
                subtitle="Sous-agent"
                trailing={
                  typeof s.float_available_minor === 'number' ? (
                    <Money amountMinor={s.float_available_minor} currency={cur} />
                  ) : null
                }
              />
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span className="ui-hint">{k}</span>
      <span style={{ fontWeight: strong ? 'var(--weight-semibold)' : undefined }}>{v}</span>
    </div>
  );
}

/* ------------------------------------------------------------- WEB-034 */
export function AgentDepositPage() {
  const { data } = useAgent();
  const cur = data?.currency ?? 'XOF';
  const a = useAgentActions();
  const [query, setQuery] = useState('');
  const [phone, setPhone] = useState('');
  const [amount, setAmount] = useState(0);
  const [receipt, setReceipt] = useState<Record<string, unknown> | null>(null);
  const customers = useAgentCustomers(query);

  async function submit() {
    try {
      const r = (await a.deposit.mutateAsync({
        client_phone_number: phone.trim(),
        amount_minor: amount,
      })) as Record<string, unknown>;
      setReceipt(r ?? { statut: 'ok' });
      toast.success('Dépôt effectué.');
    } catch (e) {
      toast.error(e);
    }
  }

  if (receipt)
    return (
      <div>
        <PageHeader title="Reçu de dépôt" back={false} />
        <Receipt data={receipt} />
        <Button block style={{ marginTop: 'var(--space-4)' }} onClick={() => setReceipt(null)}>
          Nouveau dépôt
        </Button>
      </div>
    );

  return (
    <div>
      <PageHeader title="Dépôt client" />
      <Card style={{ display: 'grid', gap: 'var(--space-3)' }}>
        <Input
          label="Rechercher un client (nom / numéro)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {customers.data && customers.data.length > 0 && (
          <div style={{ display: 'grid', gap: 4 }}>
            {customers.data.slice(0, 5).map((c, i) => (
              <Button
                key={String(c.phone_number ?? i)}
                size="sm"
                variant="secondary"
                onClick={() => {
                  setPhone(String(c.phone_number ?? ''));
                  setQuery(String(c.phone_number ?? c.masked ?? ''));
                }}
              >
                {String(c.masked ?? c.phone_number ?? c.name ?? '—')}
              </Button>
            ))}
          </div>
        )}
        <Input label="Numéro du client" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <AmountField currency={cur} value={amount} onChange={setAmount} />
        <Button
          block
          loading={a.deposit.isPending}
          disabled={!phone || amount <= 0}
          onClick={submit}
        >
          Encaisser et créditer
        </Button>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------- WEB-035 */
export function AgentWithdrawPage() {
  const { data } = useAgent();
  const cur = data?.currency ?? 'XOF';
  const a = useAgentActions();
  const [code, setCode] = useState('');
  const [amount, setAmount] = useState(0);
  const [receipt, setReceipt] = useState<Record<string, unknown> | null>(null);

  async function submit() {
    try {
      const r = (await a.confirmWithdrawal.mutateAsync({
        code: code.trim(),
        amount_minor: amount || undefined,
      })) as Record<string, unknown>;
      setReceipt(r ?? { statut: 'ok' });
      toast.success('Retrait confirmé — remettez le cash au client.');
    } catch (e) {
      toast.error(e);
    }
  }

  if (receipt)
    return (
      <div>
        <PageHeader title="Reçu de retrait" back={false} />
        <Receipt data={receipt} />
        <Button block style={{ marginTop: 'var(--space-4)' }} onClick={() => setReceipt(null)}>
          Nouveau retrait
        </Button>
      </div>
    );

  return (
    <div>
      <PageHeader title="Retrait client" />
      <Card style={{ display: 'grid', gap: 'var(--space-3)' }}>
        <Input
          label="Code de retrait (fourni par le client)"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
        />
        <AmountField
          currency={cur}
          value={amount}
          onChange={setAmount}
          label="Montant annoncé (contrôle)"
        />
        <Button
          block
          loading={a.confirmWithdrawal.isPending}
          disabled={code.length < 4}
          onClick={submit}
        >
          Confirmer et remettre le cash
        </Button>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------- WEB-036 */
export function AgentOperationsPage() {
  const ops = useAgentOperations();
  const [filter, setFilter] = useState('all');

  const rows = useMemo(
    () =>
      (ops.data ?? []).filter(
        (o) =>
          filter === 'all' ||
          String(o.kind ?? o.type ?? '')
            .toLowerCase()
            .includes(filter),
      ),
    [ops.data, filter],
  );

  function exportCsv() {
    const cols = Object.keys(rows[0] ?? {});
    const csv = [
      cols.join(','),
      ...rows.map((r) => cols.map((c) => JSON.stringify(r[c] ?? '')).join(',')),
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `operations-agent-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <PageHeader
        title="Journal des opérations"
        action={
          <Button size="sm" variant="secondary" disabled={rows.length === 0} onClick={exportCsv}>
            Export CSV
          </Button>
        }
      />
      <Tabs
        ariaLabel="Filtre"
        value={filter}
        onChange={setFilter}
        items={[
          { id: 'all', label: 'Tout' },
          { id: 'deposit', label: 'Dépôts' },
          { id: 'withdraw', label: 'Retraits' },
          { id: 'float', label: 'Float' },
        ]}
      />
      <div style={{ marginTop: 'var(--space-3)' }}>
        {ops.isLoading ? (
          <Card>
            <Skeleton height={56} />
          </Card>
        ) : rows.length === 0 ? (
          <Card>
            <EmptyState title="Aucune opération" />
          </Card>
        ) : (
          <Card style={{ padding: 0 }}>
            {rows.map((o, i) => (
              <ListRow
                key={String(o.id ?? i)}
                title={String(o.kind ?? o.type ?? '—')}
                subtitle={o.created_at ? formatDate(String(o.created_at), 'long') : undefined}
                trailing={
                  typeof o.amount_minor === 'number' ? (
                    <Money amountMinor={o.amount_minor} currency={String(o.currency ?? 'XOF')} />
                  ) : (
                    <Badge>{String(o.status ?? '')}</Badge>
                  )
                }
              />
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------- WEB-037 + WEB-038 */
export function AgentFloatPage() {
  const { data } = useAgent();
  const cur = data?.currency ?? 'XOF';
  const a = useAgentActions();
  const [dir, setDir] = useState<'topup' | 'withdraw'>('topup');
  const [amount, setAmount] = useState(0);

  async function submit() {
    try {
      await (dir === 'topup' ? a.topupFloat : a.withdrawFloat).mutateAsync(amount);
      toast.success('Mouvement de float enregistré.');
      setAmount(0);
    } catch (e) {
      toast.error(e);
    }
  }

  return (
    <div>
      <PageHeader title="Gérer ma liquidité" />
      <Card style={{ display: 'grid', gap: 'var(--space-3)' }}>
        {data && (
          <p className="ui-hint">
            Float actuel : <Money amountMinor={data.float_available_minor} currency={cur} />
          </p>
        )}
        <Tabs
          ariaLabel="Sens"
          value={dir}
          onChange={(v) => setDir(v as 'topup' | 'withdraw')}
          items={[
            { id: 'topup', label: 'Réapprovisionner' },
            { id: 'withdraw', label: 'Retirer du float' },
          ]}
        />
        <AmountField currency={cur} value={amount} onChange={setAmount} />
        <Button
          block
          loading={a.topupFloat.isPending || a.withdrawFloat.isPending}
          disabled={amount <= 0}
          onClick={submit}
        >
          Valider
        </Button>
      </Card>
    </div>
  );
}
