// WEB-027 — carte virtuelle : demander, afficher, révéler PAN/CVV, geler, plafonds.
import { useState } from 'react';
import { Badge, Button, Card, EmptyState, Skeleton } from '@shared/ui';
import { AmountField, PageHeader } from '@features/common/kit';
import { useCardActions, useCards, usePrimaryWallet } from '@shared/api/hooks';
import { toast } from '@shared/ui';
import { formatMoney } from '@shared/i18n/format';

export function CardPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const cards = useCards();
  const a = useCardActions();
  const card = cards.data?.[0];

  const [revealed, setRevealed] = useState<{ pan: string; cvv: string; expiry: string } | null>(
    null,
  );
  const [editLimits, setEditLimits] = useState(false);
  const [daily, setDaily] = useState(0);
  const [monthly, setMonthly] = useState(0);

  if (cards.isLoading) return <Skeleton height={180} />;

  if (!card) {
    return (
      <div>
        <PageHeader title="Carte" />
        <Card>
          <EmptyState
            title="Aucune carte"
            description="Demandez une carte virtuelle pour payer en ligne."
            action={
              <Button
                loading={a.issue.isPending}
                onClick={() => a.issue.mutate({ network: 'VISA' })}
              >
                Demander une carte
              </Button>
            }
          />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Carte" />
      <Card
        style={{
          background: 'linear-gradient(135deg, var(--color-brand-600), var(--color-brand-800))',
          color: '#fff',
          display: 'grid',
          gap: 'var(--space-4)',
          minHeight: 180,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>{card.network}</span>
          <Badge tone={card.status === 'ACTIVE' ? 'success' : 'warning'}>{card.status}</Badge>
        </div>
        <strong
          style={{
            fontSize: 'var(--text-xl)',
            letterSpacing: '0.12em',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {revealed
            ? revealed.pan.replace(/(.{4})/g, '$1 ').trim()
            : `•••• •••• •••• ${card.last4}`}
        </strong>
        <div style={{ display: 'flex', gap: 'var(--space-5)' }}>
          <span>
            EXP{' '}
            {revealed
              ? revealed.expiry
              : `${String(card.expiry_month).padStart(2, '0')}/${String(card.expiry_year).slice(-2)}`}
          </span>
          <span>CVV {revealed ? revealed.cvv : '•••'}</span>
        </div>
      </Card>

      <div
        style={{
          display: 'flex',
          gap: 'var(--space-2)',
          margin: 'var(--space-3) 0',
          flexWrap: 'wrap',
        }}
      >
        <Button
          size="sm"
          onClick={async () => {
            try {
              setRevealed(await a.reveal.mutateAsync(card.card_id));
              setTimeout(() => setRevealed(null), 30_000);
            } catch (e) {
              toast.error(e);
            }
          }}
        >
          {revealed ? 'Masquer' : 'Révéler PAN / CVV'}
        </Button>
        {card.status === 'ACTIVE' ? (
          <Button size="sm" variant="secondary" onClick={() => a.freeze.mutate(card.card_id)}>
            Geler
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => a.unfreeze.mutate(card.card_id)}>
            Dégeler
          </Button>
        )}
        <Button
          size="sm"
          variant="secondary"
          onClick={() => {
            setDaily(card.daily_limit_minor);
            setMonthly(card.monthly_limit_minor);
            setEditLimits((v) => !v);
          }}
        >
          Plafonds
        </Button>
        <Button size="sm" variant="ghost" onClick={() => a.close.mutate(card.card_id)}>
          Résilier
        </Button>
      </div>

      <Card>
        <p className="ui-hint">
          Plafond quotidien : {formatMoney(card.daily_limit_minor, currency)}
        </p>
        <p className="ui-hint">
          Plafond mensuel : {formatMoney(card.monthly_limit_minor, currency)}
        </p>
        <p className="ui-hint">Canaux : {card.channels?.join(', ') || '—'}</p>
      </Card>

      {editLimits && (
        <Card style={{ marginTop: 'var(--space-3)', display: 'grid', gap: 'var(--space-3)' }}>
          <AmountField
            currency={currency}
            value={daily}
            onChange={setDaily}
            label="Plafond quotidien"
          />
          <AmountField
            currency={currency}
            value={monthly}
            onChange={setMonthly}
            label="Plafond mensuel"
          />
          <Button
            block
            loading={a.limits.isPending}
            onClick={async () => {
              try {
                await a.limits.mutateAsync({
                  id: card.card_id,
                  daily_limit_minor: daily,
                  monthly_limit_minor: monthly,
                });
                setEditLimits(false);
                toast.success('Plafonds mis à jour.');
              } catch (e) {
                toast.error(e);
              }
            }}
          >
            Enregistrer
          </Button>
        </Card>
      )}
    </div>
  );
}
