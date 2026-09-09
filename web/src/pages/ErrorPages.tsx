// WEB-008 — pages 404 / 500.
import { Link, useRouteError } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

function Shell({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  return (
    <main
      style={{
        minHeight: '100dvh',
        display: 'grid',
        placeItems: 'center',
        textAlign: 'center',
        gap: 'var(--space-3)',
        padding: 'var(--space-6)',
      }}
    >
      <h1 style={{ fontSize: 'var(--text-3xl)' }}>{title}</h1>
      <p style={{ color: 'var(--fg-muted)' }}>{body}</p>
      {children}
      <Link className="ui-btn ui-btn--secondary" to="/">
        Accueil
      </Link>
    </main>
  );
}

export function NotFoundPage() {
  const { t } = useTranslation();
  return <Shell title="404" body={t('errors.notFoundBody')} />;
}

export function RouteErrorPage() {
  const { t } = useTranslation();
  const error = useRouteError();
  return (
    <Shell title="Oups" body={t('errors.server')}>
      {import.meta.env.DEV && error instanceof Error && (
        <pre style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-muted)' }}>{error.message}</pre>
      )}
    </Shell>
  );
}
