// WEB-006 (socle) — coquille du tableau de bord. Le contenu réel (soldes, raccourcis,
// dernières opérations, bandeau KYC) arrive en WEB-015.
import { useTranslation } from 'react-i18next';
import { Card, EmptyState, Skeleton } from '@shared/ui';

export function DashboardPage() {
  const { t } = useTranslation();
  return (
    <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
      <Card>
        <span className="ui-hint">{t('balance.title')}</span>
        <div style={{ marginTop: 'var(--space-2)' }}>
          <Skeleton width={180} height={36} />
        </div>
      </Card>

      <section aria-label={t('nav.history')}>
        <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: 'var(--space-2)' }}>
          {t('nav.history')}
        </h2>
        <Card>
          <EmptyState title="Rien pour l’instant" description="Vos opérations apparaîtront ici." />
        </Card>
      </section>
    </div>
  );
}
