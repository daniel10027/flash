// WEB-040 — connexion staff (clé partagée) + layout back-office dédié.
import type { ReactNode } from 'react';
import { NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { Button, Card, Input } from '@shared/ui';
import { useAdminAuth } from '@features/admin/client';

const NAV = [
  { to: '/admin', label: 'Comptes', end: true },
  { to: '/admin/kyc', label: 'KYC' },
  { to: '/admin/aml', label: 'AML' },
  { to: '/admin/reference', label: 'Référentiel' },
  { to: '/admin/finance', label: 'Finance' },
  { to: '/admin/audit', label: 'Audit' },
];

export function RequireAdmin({ children }: { children: ReactNode }) {
  const key = useAdminAuth((s) => s.key);
  if (!key) return <Navigate to="/admin/login" replace />;
  return <>{children}</>;
}

export function AdminLoginPage() {
  const setKey = useAdminAuth((s) => s.setKey);
  const navigate = useNavigate();
  const [value, setValue] = useState('');
  return (
    <main
      style={{
        minHeight: '100dvh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--space-4)',
      }}
    >
      <Card style={{ width: 'min(380px, 100%)', display: 'grid', gap: 'var(--space-3)' }}>
        <h1 style={{ fontSize: 'var(--text-xl)' }}>Back-office Flash</h1>
        <p className="ui-hint">
          Saisissez votre clé d’accès (<code>X-Admin-Key</code>). Le rôle (support, compliance,
          finance, admin) est déterminé par le serveur.
        </p>
        <Input
          label="Clé d’accès"
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button
          block
          disabled={value.trim().length < 4}
          onClick={() => {
            setKey(value.trim());
            navigate('/admin', { replace: true });
          }}
        >
          Entrer
        </Button>
      </Card>
    </main>
  );
}

export function AdminLayout() {
  const setKey = useAdminAuth((s) => s.setKey);
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: '100dvh', display: 'grid', gridTemplateRows: 'auto 1fr' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--border)',
          background: 'var(--bg-elevated)',
          flexWrap: 'wrap',
        }}
      >
        <strong>Flash · Back-office</strong>
        <nav
          style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap' }}
          aria-label="Sections"
        >
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              style={({ isActive }) => ({
                padding: 'var(--space-2) var(--space-3)',
                borderRadius: 'var(--radius-md)',
                textDecoration: 'none',
                color: isActive ? 'var(--primary)' : 'var(--fg-muted)',
                background: isActive ? 'var(--bg-sunken)' : 'transparent',
              })}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <Button
          size="sm"
          variant="ghost"
          style={{ marginLeft: 'auto' }}
          onClick={() => {
            setKey(null);
            navigate('/admin/login', { replace: true });
          }}
        >
          Quitter
        </Button>
      </header>
      <main style={{ padding: 'var(--space-4)', maxWidth: 1100, width: '100%', margin: '0 auto' }}>
        <Outlet />
      </main>
    </div>
  );
}
