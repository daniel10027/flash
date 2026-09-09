// WEB-016 — envoyer de l'argent : destinataire, montant, aperçu frais 0,8 %, reçu.
import { useState } from 'react';
import { Button, Card, Input, toast } from '@shared/ui';
import { AmountField, ConfirmSheet, PageHeader, Receipt } from '@features/common/kit';
import { usePrimaryWallet, useSendTransfer } from '@shared/api/hooks';
import { formatMoney } from '@shared/i18n/format';
import type { TransferReceipt } from '@shared/api/types';

export function SendMoneyPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const send = useSendTransfer();

  const [phone, setPhone] = useState('');
  const [amount, setAmount] = useState(0);
  const [note, setNote] = useState('');
  const [confirm, setConfirm] = useState(false);
  const [receipt, setReceipt] = useState<TransferReceipt | null>(null);

  async function doSend() {
    try {
      const r = await send.mutateAsync({
        recipient_phone_number: phone.trim(),
        amount_minor: amount,
        note: note.trim() || undefined,
      });
      setReceipt(r);
      setConfirm(false);
      toast.success('Transfert effectué.');
    } catch (e) {
      toast.error(e);
    }
  }

  if (receipt) {
    return (
      <div>
        <PageHeader title="Reçu" back={false} />
        <Receipt data={receipt} />
        <Button
          block
          style={{ marginTop: 'var(--space-4)' }}
          onClick={() => {
            setReceipt(null);
            setPhone('');
            setAmount(0);
            setNote('');
          }}
        >
          Nouveau transfert
        </Button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Envoyer de l’argent" />
      <Card style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <Input
          label="Numéro du destinataire"
          inputMode="tel"
          placeholder="+225…"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />
        <AmountField currency={currency} value={amount} onChange={setAmount} showFee />
        <Input label="Note (facultatif)" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button block disabled={!phone || amount <= 0} onClick={() => setConfirm(true)}>
          Continuer
        </Button>
      </Card>

      <ConfirmSheet
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={doSend}
        busy={send.isPending}
        title="Confirmer le transfert"
        summary={
          <Card style={{ background: 'var(--bg-sunken)' }}>
            <p>
              À <strong>{phone}</strong>
            </p>
            <p style={{ fontSize: 'var(--text-xl)', fontWeight: 'var(--weight-semibold)' }}>
              {formatMoney(amount, currency)}
            </p>
          </Card>
        }
      />
    </div>
  );
}
