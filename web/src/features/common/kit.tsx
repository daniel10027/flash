// Briques réutilisées par les écrans du parcours client.
import { useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, Input, PinInput, Sheet } from '@shared/ui';
import { formatMoney } from '@shared/i18n/format';

/* -------------------------------------------------- en-tête d'écran */
export function PageHeader({
  title,
  subtitle,
  action,
  back = true,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  back?: boolean;
}) {
  const navigate = useNavigate();
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
        marginBottom: 'var(--space-4)',
      }}
    >
      {back && (
        <button
          type="button"
          className="layout__icon-btn"
          onClick={() => navigate(-1)}
          aria-label="Retour"
        >
          ←
        </button>
      )}
      <div style={{ flex: 1 }}>
        <h1 style={{ fontSize: 'var(--text-xl)' }}>{title}</h1>
        {subtitle && <p className="ui-hint">{subtitle}</p>}
      </div>
      {action}
    </header>
  );
}

/* -------------------------------------------------- saisie de montant + frais 0,8 % */
const P2P_FEE_BPS = 80;

export function AmountField({
  currency,
  value,
  onChange,
  showFee = false,
  label = 'Montant',
}: {
  currency: string;
  value: number;
  onChange: (minor: number) => void;
  showFee?: boolean;
  label?: string;
}) {
  const zeroDecimal = currency === 'XOF' || currency === 'XAF';
  const display = value === 0 ? '' : zeroDecimal ? String(value) : (value / 100).toFixed(2);
  const fee = showFee ? Math.ceil((value * P2P_FEE_BPS) / 10_000) : 0;

  return (
    <div style={{ display: 'grid', gap: 'var(--space-2)' }}>
      <Input
        label={label}
        inputMode="decimal"
        value={display}
        onChange={(e) => {
          const raw = e.target.value.replace(/[^\d.,]/g, '').replace(',', '.');
          const num = Number(raw || 0);
          onChange(zeroDecimal ? Math.round(num) : Math.round(num * 100));
        }}
        suffix={currency}
      />
      {showFee && value > 0 && (
        <Card style={{ padding: 'var(--space-3)', background: 'var(--bg-sunken)' }}>
          <Row k="Frais (0,8 %)" v={formatMoney(fee, currency)} />
          <Row k="Total débité" v={formatMoney(value + fee, currency)} strong />
        </Card>
      )}
    </div>
  );
}

function Row({ k, v, strong }: { k: string; v: string; strong?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
      <span className="ui-hint">{k}</span>
      <span style={{ fontWeight: strong ? 'var(--weight-semibold)' : undefined }}>{v}</span>
    </div>
  );
}

/* -------------------------------------------------- confirmation par code secret
   Le backend n'exige pas le PIN sur ces routes (session = preuve) ; l'écran de
   confirmation reste une friction UX volontaire avant un débit. */
export function ConfirmSheet({
  open,
  onClose,
  onConfirm,
  title,
  summary,
  busy,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  summary: ReactNode;
  busy?: boolean;
}) {
  const [pin, setPin] = useState('');
  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
        {summary}
        <PinInput label="Confirmez avec votre code secret" value={pin} onChange={setPin} />
        <Button block loading={busy} disabled={pin.length < 4} onClick={onConfirm}>
          Confirmer
        </Button>
      </div>
    </Sheet>
  );
}

/* -------------------------------------------------- reçu générique */
export function Receipt({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && typeof v !== 'object');
  return (
    <Card style={{ display: 'grid', gap: 'var(--space-2)' }}>
      {entries.map(([k, v]) => (
        <div
          key={k}
          style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-4)' }}
        >
          <span className="ui-hint">{k.replace(/_/g, ' ')}</span>
          <span style={{ textAlign: 'right', wordBreak: 'break-all' }}>{String(v)}</span>
        </div>
      ))}
    </Card>
  );
}
