// WEB-006 — coquille applicative : en-tête (solde masquable, menu profil),
// navigation latérale (desktop) / barre du bas (mobile), zone de contenu.
import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@app/theme';
import { useSession } from '@shared/auth/session';
import { usePrivacy } from './privacy';
import './layout.css';

const NAV = [
  { to: '/', key: 'home', icon: '⌂', end: true },
  { to: '/send', key: 'send', icon: '↗' },
  { to: '/pay', key: 'pay', icon: '⤓' },
  { to: '/history', key: 'history', icon: '≣' },
  { to: '/profile', key: 'profile', icon: '☺' },
] as const;

export function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const { hidden, toggle } = usePrivacy();
  const theme = useTheme();
  const clear = useSession((s) => s.clear);

  return (
    <div className="layout">
      <a className="skip-link" href="#main">
        {t('a11y.skipToContent')}
      </a>

      <header className="layout__header">
        <span className="layout__brand">
          <img src="/favicon.svg" alt="" width={24} height={24} /> {t('common.appName')}
        </span>

        <span className="layout__balance" aria-live="polite">
          <span className="ui-hint">{t('balance.title')}</span>
          <strong>{hidden ? t('balance.hidden') : '—'}</strong>
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
            <button role="menuitem" onClick={() => theme.cycle()}>
              {t('a11y.theme')} : {theme.mode}
            </button>
            <button
              role="menuitem"
              onClick={() => {
                setMenuOpen(false);
                navigate('/profile');
              }}
            >
              {t('nav.profile')}
            </button>
            <button
              role="menuitem"
              onClick={() => {
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
        {NAV.map((item) => (
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
