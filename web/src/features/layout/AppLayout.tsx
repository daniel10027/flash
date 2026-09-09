// WEB-006 — coquille applicative : en-tête (solde masquable, cloche, menu profil),
// navigation latérale (desktop) / barre du bas (mobile), zone de contenu.
import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@app/theme';
import { useSession } from '@shared/auth/session';
import { usePrimaryWallet, useNotifications } from '@shared/api/hooks';
import { useIsAgent } from '@features/agent/hooks';
import { formatMoney } from '@shared/i18n/format';
import { usePrivacy } from './privacy';
import './layout.css';

const PRIMARY = [
  { to: '/', key: 'home', icon: '⌂', end: true },
  { to: '/send', key: 'send', icon: '↗' },
  { to: '/pay', key: 'pay', icon: '⤓' },
  { to: '/history', key: 'history', icon: '≣' },
  { to: '/profile', key: 'profile', icon: '☺' },
] as const;

const SECONDARY = [
  { to: '/request', label: 'Demander' },
  { to: '/receive', label: 'Recevoir' },
  { to: '/cash/withdraw', label: 'Retrait cash' },
  { to: '/cash/deposit', label: 'Dépôt cash' },
  { to: '/operators', label: 'Compte opérateur' },
  { to: '/vault', label: 'Coffre' },
  { to: '/savings', label: 'Épargne' },
  { to: '/card', label: 'Carte' },
];

export function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const { hidden, toggle } = usePrivacy();
  const theme = useTheme();
  const clear = useSession((s) => s.clear);
  const { wallet } = usePrimaryWallet();
  const notifs = useNotifications();
  const unread = (notifs.data?.notifications ?? []).filter((n) => !n.read_at).length;
  const isAgent = useIsAgent();

  return (
    <div className="layout">
      <a className="skip-link" href="#main">
        {t('a11y.skipToContent')}
      </a>

      <header className="layout__header">
        <Link to="/" className="layout__brand" style={{ textDecoration: 'none', color: 'inherit' }}>
          <img src="/favicon.svg" alt="" width={24} height={24} /> {t('common.appName')}
        </Link>

        <span className="layout__balance" aria-live="polite">
          <span className="ui-hint">{t('balance.title')}</span>
          <strong>
            {hidden || !wallet
              ? t('balance.hidden')
              : formatMoney(wallet.available_minor, wallet.currency)}
          </strong>
          <button
            type="button"
            className="layout__icon-btn"
            onClick={toggle}
            aria-pressed={hidden}
            aria-label={hidden ? t('balance.show') : t('balance.hide')}
          >
            {hidden ? '🙈' : '👁'}
          </button>
        </span>

        <Link
          to="/notifications"
          className="layout__icon-btn"
          aria-label={t('nav.notifications')}
          style={{ position: 'relative' }}
        >
          🔔
          {unread > 0 && (
            <span
              aria-hidden
              style={{
                position: 'absolute',
                top: -2,
                right: -2,
                minWidth: 16,
                height: 16,
                borderRadius: 8,
                background: 'var(--color-danger-fg)',
                color: '#fff',
                fontSize: 10,
                display: 'grid',
                placeItems: 'center',
              }}
            >
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </Link>

        <button
          type="button"
          className="layout__icon-btn"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label={t('a11y.openMenu')}
          onClick={() => setMenuOpen((v) => !v)}
        >
          ⋮
        </button>

        {menuOpen && (
          <div className="menu" role="menu">
            {[...SECONDARY, ...(isAgent ? [{ to: '/agent', label: 'Espace agent' }] : [])].map(
              (s) => (
                <button
                  key={s.to}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    navigate(s.to);
                  }}
                >
                  {s.label}
                </button>
              ),
            )}
            <hr style={{ border: 0, borderTop: '1px solid var(--border)', margin: '4px 0' }} />
            <button type="button" role="menuitem" onClick={() => theme.cycle()}>
              {t('a11y.theme')} : {theme.mode}
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                clear();
                navigate('/login', { replace: true });
              }}
            >
              {t('nav.logout')}
            </button>
          </div>
        )}
      </header>

      <nav className="layout__nav" aria-label="Navigation principale">
        {PRIMARY.map((item) => (
          <NavLink key={item.to} to={item.to} end={'end' in item ? item.end : undefined}>
            <span aria-hidden>{item.icon}</span>
            <span>{t(`nav.${item.key}`)}</span>
          </NavLink>
        ))}
      </nav>

      <main id="main" className="layout__main">
        <Outlet />
      </main>
    </div>
  );
}
