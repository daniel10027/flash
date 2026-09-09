// WEB-017 — demander de l'argent : créer, lister (reçues/émises), accepter/refuser.
import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  ListRow,
  Money,
  Sheet,
  Skeleton,
  Tabs,
} from '@shared/ui';
import { AmountField, PageHeader } from '@features/common/kit';
import { usePaymentRequestActions, usePaymentRequests, usePrimaryWallet } from '@shared/api/hooks';
import { toast } from '@shared/ui';
import { formatRelative } from '@shared/i18n/format';

export function PaymentRequestsPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const list = usePaymentRequests();
  const actions = usePaymentRequestActions();
  const [tab, setTab] = useState('incoming');
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState('');
  const [amount, setAmount] = useState(0);

  const items = (list.data ?? []).filter((r) => r.direction === tab);

  async function create() {
    try {
      await actions.create.mutateAsync({ payer_phone_number: phone.trim(), amount_minor: amount });
      setOpen(false);
      setPhone('');
      setAmount(0);
      toast.success('Demande envoyée.');
    } catch (e) {
      toast.error(e);
    }
  }

  return (
    <div>
      <PageHeader
        title="Demandes de paiement"
        action={
          <Button size="sm" onClick={() => setOpen(true)}>
            Nouvelle
          </Button>
        }
      />
      <Tabs
        ariaLabel="Sens"
        value={tab}
        onChange={setTab}
        items={[
          { id: 'incoming', label: 'Reçues' },
          { id: 'outgoing', label: 'Émises' },
        ]}
      />
      <div style={{ marginTop: 'var(--space-3)' }}>
        {list.isLoading ? (
          <Card>
            <Skeleton height={56} />
          </Card>
        ) : items.length === 0 ? (
          <Card>
            <EmptyState title="Aucune demande" />
          </Card>
        ) : (
          <Card style={{ padding: 0 }}>
            {items.map((r) => (
              <ListRow
                key={r.request_id}
                title={r.counterparty_masked ?? '—'}
                subtitle={`${formatRelative(r.created_at)} · ${r.status}`}
                trailing={
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                    <Money amountMinor={r.amount_minor} currency={r.currency} />
                    {r.status === 'PENDING' && r.direction === 'incoming' && (
                      <>
                        <Button size="sm" onClick={() => actions.accept.mutate(r.request_id)}>
                          Payer
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => actions.decline.mutate(r.request_id)}
                        >
                          Refuser
                        </Button>
                      </>
                    )}
                    {r.status === 'PENDING' && r.direction === 'outgoing' && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => actions.cancel.mutate(r.request_id)}
                      >
                        Annuler
                      </Button>
                    )}
                    {r.status !== 'PENDING' && <Badge>{r.status}</Badge>}
                  </div>
                }
              />
            ))}
          </Card>
        )}
      </div>

      <Sheet open={open} onClose={() => setOpen(false)} title="Demander de l’argent">
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <Input
            label="Numéro du payeur"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          <AmountField currency={currency} value={amount} onChange={setAmount} />
          <Button
            block
            loading={actions.create.isPending}
            disabled={!phone || amount <= 0}
            onClick={create}
          >
            Envoyer la demande
          </Button>
        </div>
      </Sheet>
    </div>
  );
}
