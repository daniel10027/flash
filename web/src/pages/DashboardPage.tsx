// WEB-015 — tableau de bord : solde, raccourcis, dernières opérations, bandeau KYC.
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Amount, Badge, Card, EmptyState, ListRow, Money, Skeleton } from '@shared/ui';
import { useKycStatus, usePrimaryWallet, useStatement } from '@shared/api/hooks';
import { usePrivacy } from '@features/layout/privacy';
import { formatRelative } from '@shared/i18n/format';

const SHORTCUTS = [
  { to: '/send', label: 'Envoyer', icon: '↗' },
  { to: '/pay', label: 'Payer', icon: '⤓' },
  { to: '/cash/withdraw', label: 'Retirer', icon: '⇩' },
  { to: '/cash/deposit', label: 'Ajouter', icon: '⇧' },
];

export function DashboardPage() {
  const { t } = useTranslation();
  const { wallet, isLoading } = usePrimaryWallet();
  const { hidden } = usePrivacy();
  const kyc = useKycStatus();
  const statement = useStatement({ limit: 5 });
  const lines = statement.data?.pages[0]?.lines ?? [];

  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <Card>
        <span className="ui-hint">{t('balance.title')}</span>
        <div style={{ marginTop: 'var(--space-1)' }}>
          {isLoading ? (
            <Skeleton width={180} height={36} />
          ) : hidden ? (
            <strong style={{ fontSize: 'var(--text-3xl)' }}>{t('balance.hidden')}</strong>
          ) : wallet ? (
            <Amount amountMinor={wallet.available_minor} currency={wallet.currency} />
          ) : (
            <strong>—</strong>
          )}
        </div>
        {wallet && wallet.reserved_minor > 0 && !hidden && (
          <p className="ui-hint" style={{ marginTop: 'var(--space-1)' }}>
            dont <Money amountMinor={wallet.reserved_minor} currency={wallet.currency} /> réservés
          </p>
        )}
      </Card>

      {kyc.data && kyc.data.tier === 0 && (
        <Link to="/profile" style={{ textDecoration: 'none' }}>
          <Card style={{ background: 'var(--color-warning-bg)', color: 'var(--color-warning-fg)' }}>
            <strong>Vérifiez votre identité</strong>
            <p style={{ fontSize: 'var(--text-sm)' }}>
              Débloquez des plafonds plus élevés en quelques minutes.
            </p>
          </Card>
        </Link>
      )}

      <nav
        aria-label="Raccourcis"
        style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-2)' }}
      >
        {SHORTCUTS.map((s) => (
          <Link
            key={s.to}
            to={s.to}
            className="ui-card"
            style={{
              display: 'grid',
              justifyItems: 'center',
              gap: 4,
              textDecoration: 'none',
              padding: 'var(--space-3)',
            }}
          >
            <span aria-hidden style={{ fontSize: 'var(--text-xl)' }}>
              {s.icon}
            </span>
            <span style={{ fontSize: 'var(--text-xs)' }}>{s.label}</span>
          </Link>
        ))}
      </nav>

      <section aria-label={t('nav.history')}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: 'var(--space-2)',
          }}
        >
          <h2 style={{ fontSize: 'var(--text-lg)' }}>{t('nav.history')}</h2>
          <Link to="/history">Tout voir</Link>
        </div>
        <Card style={{ padding: 0 }}>
          {statement.isLoading ? (
            <div style={{ padding: 'var(--space-4)' }}>
              <Skeleton height={48} />
            </div>
          ) : lines.length === 0 ? (
            <EmptyState
              title="Rien pour l’instant"
              description="Vos opérations apparaîtront ici."
            />
          ) : (
            lines.map((l) => (
              <ListRow
                key={l.id}
                title={l.counterparty_masked ?? l.kind}
                subtitle={`${l.reference} · ${formatRelative(l.occurred_at)}`}
                trailing={
                  <span style={{ textAlign: 'right' }}>
                    <Money
                      amountMinor={l.amount_minor}
                      currency={l.currency}
                      direction={l.direction}
                      sign
                    />
                    {l.direction === 'out' && <Badge>{l.kind}</Badge>}
                  </span>
                }
              />
            ))
          )}
        </Card>
      </section>
    </div>
  );
}
