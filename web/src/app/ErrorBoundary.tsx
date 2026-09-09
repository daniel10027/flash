// WEB-008 — capture des erreurs de rendu ; page de repli neutre.
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { config } from '@shared/config/runtime';

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (config.ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.error('ErrorBoundary', error, info.componentStack);
    }
    // TODO: brancher Sentry (config.SENTRY_DSN) — hors périmètre socle.
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <main
            style={{
              minHeight: '100dvh',
              display: 'grid',
              placeItems: 'center',
              padding: 'var(--space-6)',
              textAlign: 'center',
              gap: 'var(--space-3)',
            }}
          >
            <h1>Oups.</h1>
            <p>L’application a rencontré un problème.</p>
            <button className="ui-btn ui-btn--primary" onClick={() => window.location.reload()}>
              Recharger
            </button>
          </main>
        )
      );
    }
    return this.props.children;
  }
}
