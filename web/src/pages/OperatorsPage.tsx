// WEB-022 — retrait / dépôt vers un compte opérateur (Orange / MTN / Moov).
import { useState } from 'react';
import { Badge, Button, Card, EmptyState, Input, ListRow, Skeleton, Tabs } from '@shared/ui';
import { AmountField, PageHeader } from '@features/common/kit';
import {
  useOperatorPayout,
  useOperatorTopup,
  useOperatorTransfers,
  usePrimaryWallet,
} from '@shared/api/hooks';
import { toast } from '@shared/ui';

const OPERATORS = ['ORANGE_CI', 'MTN_CI', 'MOOV_CI', 'WAVE_CI'];

export function OperatorsPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const list = useOperatorTransfers();
  const payout = useOperatorPayout();
  const topup = useOperatorTopup();

  const [dir, setDir] = useState<'payout' | 'topup'>('payout');
  const [operator, setOperator] = useState(OPERATORS[0]!);
  const [msisdn, setMsisdn] = useState('');
  const [amount, setAmount] = useState(0);

  async function submit() {
    const body = { operator, msisdn: msisdn.trim(), amount_minor: amount };
    try {
      await (dir === 'payout' ? payout : topup).mutateAsync(body);
      toast.success('Opération enregistrée — statut mis à jour à la confirmation opérateur.');
      setAmount(0);
      setMsisdn('');
    } catch (e) {
      toast.error(e);
    }
  }

  return (
    <div>
      <PageHeader title="Compte opérateur" subtitle="Orange, MTN, Moov, Wave…" />
      <Card style={{ display: 'grid', gap: 'var(--space-3)' }}>
        <Tabs
          ariaLabel="Sens"
          value={dir}
          onChange={(v) => setDir(v as 'payout' | 'topup')}
          items={[
            { id: 'payout', label: 'Envoyer vers l’opérateur' },
            { id: 'topup', label: 'Recharger depuis l’opérateur' },
          ]}
        />
        <label className="ui-field">
          <span className="ui-label">Opérateur</span>
          <select
            className="ui-input"
            value={operator}
            onChange={(e) => setOperator(e.target.value)}
          >
            {OPERATORS.map((o) => (
              <option key={o} value={o}>
                {o.replace('_CI', '')}
              </option>
            ))}
          </select>
        </label>
        <Input
          label="Numéro opérateur"
          inputMode="tel"
          value={msisdn}
          onChange={(e) => setMsisdn(e.target.value)}
        />
        <AmountField
          currency={currency}
          value={amount}
          onChange={setAmount}
          showFee={dir === 'payout'}
        />
        <Button
          block
          loading={payout.isPending || topup.isPending}
          disabled={!msisdn || amount <= 0}
          onClick={submit}
        >
          {dir === 'payout' ? 'Envoyer' : 'Recharger'}
        </Button>
      </Card>

      <h2 style={{ fontSize: 'var(--text-lg)', margin: 'var(--space-4) 0 var(--space-2)' }}>
        Opérations récentes
      </h2>
      {list.isLoading ? (
        <Card>
          <Skeleton height={48} />
        </Card>
      ) : (list.data ?? []).length === 0 ? (
        <Card>
          <EmptyState title="Aucune opération opérateur" />
        </Card>
      ) : (
        <Card style={{ padding: 0 }}>
          {(list.data as Array<Record<string, unknown>>).map((tItem, i) => (
            <ListRow
              key={String(tItem.id ?? i)}
              title={String(tItem.operator ?? '—')}
              subtitle={String(tItem.msisdn ?? '')}
              trailing={<Badge>{String(tItem.status ?? '—')}</Badge>}
            />
          ))}
        </Card>
      )}
    </div>
  );
}
