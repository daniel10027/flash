// WEB-020 — retrait cash (code + compte à rebours + annulation).
// WEB-021 — dépôt cash (identifiant / QR à présenter à l'agent).
import { useEffect, useState } from 'react';
import { Button, Card, EmptyState, toast } from '@shared/ui';
import { Qr } from '@shared/ui/Qr';
import { AmountField, PageHeader } from '@features/common/kit';
import { useCancelWithdrawal, useCreateWithdrawal, usePrimaryWallet } from '@shared/api/hooks';
import { formatMoney } from '@shared/i18n/format';
import type { CashOrder } from '@shared/api/types';

function useCountdown(iso?: string) {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (!iso) return;
    const tick = () =>
      setLeft(Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [iso]);
  return left;
}

export function WithdrawCashPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const create = useCreateWithdrawal();
  const cancel = useCancelWithdrawal();
  const [amount, setAmount] = useState(0);
  const [order, setOrder] = useState<CashOrder | null>(null);
  const left = useCountdown(order?.expires_at);

  async function generate() {
    try {
      setOrder(await create.mutateAsync(amount));
    } catch (e) {
      toast.error(e);
    }
  }

  if (order) {
    return (
      <div>
        <PageHeader title="Code de retrait" back={false} />
        <Card
          style={{
            display: 'grid',
            gap: 'var(--space-3)',
            justifyItems: 'center',
            textAlign: 'center',
          }}
        >
          <span className="ui-hint">Montrez ce code à l’agent</span>
          <strong style={{ fontSize: 'var(--text-3xl)', letterSpacing: '0.15em' }}>
            {order.code ?? '——————'}
          </strong>
          <p>
            {formatMoney(order.amount_minor, order.currency)} · frais{' '}
            {formatMoney(order.fee_minor, order.currency)}
          </p>
          {order.expires_at && (
            <p className="ui-hint">
              Expire dans {Math.floor(left / 60)}:{String(left % 60).padStart(2, '0')}
            </p>
          )}
          <Button
            variant="ghost"
            loading={cancel.isPending}
            onClick={async () => {
              try {
                await cancel.mutateAsync(order.order_id);
                setOrder(null);
                toast.info('Code annulé.');
              } catch (e) {
                toast.error(e);
              }
            }}
          >
            Annuler le code
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Retirer de l’argent"
        subtitle="Générez un code à présenter chez un agent"
      />
      <Card style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <AmountField currency={currency} value={amount} onChange={setAmount} showFee />
        <Button block loading={create.isPending} disabled={amount <= 0} onClick={generate}>
          Générer le code
        </Button>
      </Card>
    </div>
  );
}

export function DepositCashPage() {
  const { wallet } = usePrimaryWallet();
  return (
    <div>
      <PageHeader title="Ajouter de l’argent" subtitle="Dépôt d’espèces chez un agent" />
      <Card
        style={{
          display: 'grid',
          gap: 'var(--space-4)',
          justifyItems: 'center',
          textAlign: 'center',
        }}
      >
        <p>
          Présentez ce code à l’agent, remettez les espèces : votre solde est crédité immédiatement
          et vous recevez une notification.
        </p>
        {wallet ? (
          <Qr value={`flash://deposit?w=${wallet.id}`} />
        ) : (
          <EmptyState title="Portefeuille indisponible" />
        )}
        <p className="ui-hint">Identifiant : {wallet?.id}</p>
      </Card>
    </div>
  );
}
