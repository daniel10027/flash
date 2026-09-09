// WEB-019 — présenter mon QR pour recevoir (personnel + montant optionnel).
import { useState } from 'react';
import { Card, Input } from '@shared/ui';
import { Qr } from '@shared/ui/Qr';
import { PageHeader } from '@features/common/kit';
import { useMerchantQr } from '@shared/api/hooks';
import { useSession } from '@shared/auth/session';

export function ReceivePage() {
  // Un particulier reçoit via son numéro ; s'il est aussi marchand, on affiche son QR statique.
  const merchant = useMerchantQr();
  const [amount, setAmount] = useState('');
  useSession(); // garde la page derrière l'auth

  const payload =
    merchant.data?.static_qr_payload ?? `flash://request${amount ? `?amount=${amount}` : ''}`;

  return (
    <div>
      <PageHeader title="Recevoir" subtitle="Faites scanner ce code" />
      <Card style={{ display: 'grid', gap: 'var(--space-4)', justifyItems: 'center' }}>
        <Qr value={payload} />
        <Input
          label="Montant demandé (facultatif)"
          inputMode="numeric"
          value={amount}
          onChange={(e) => setAmount(e.target.value.replace(/\D/g, ''))}
          suffix="XOF"
        />
        <p className="ui-hint" style={{ wordBreak: 'break-all', textAlign: 'center' }}>
          {payload}
        </p>
      </Card>
    </div>
  );
}
