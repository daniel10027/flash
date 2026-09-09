// WEB-018 — payer un marchand : scan QR (BarcodeDetector) ou saisie du code, confirmation.
import { useEffect, useRef, useState } from 'react';
import { Button, Card, Input, toast } from '@shared/ui';
import { AmountField, ConfirmSheet, PageHeader, Receipt } from '@features/common/kit';
import { usePayMerchant, usePrimaryWallet } from '@shared/api/hooks';
import type { TransferReceipt } from '@shared/api/types';

type Target = { merchantId: string; chargeId?: string };

function parsePayload(text: string): Target | null {
  // flash://pay?m=<merchant>&c=<charge>
  const m = text.match(/[?&]m=([^&\s]+)/);
  if (!m) return null;
  const c = text.match(/[?&]c=([^&\s]+)/);
  return {
    merchantId: decodeURIComponent(m[1]!),
    chargeId: c ? decodeURIComponent(c[1]!) : undefined,
  };
}

export function PayMerchantPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const pay = usePayMerchant();

  const [target, setTarget] = useState<Target | null>(null);
  const [manual, setManual] = useState('');
  const [amount, setAmount] = useState(0);
  const [confirm, setConfirm] = useState(false);
  const [receipt, setReceipt] = useState<TransferReceipt | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (target || receipt) return;
    const BD = (
      window as unknown as {
        BarcodeDetector?: new (o: object) => {
          detect: (s: unknown) => Promise<{ rawValue: string }[]>;
        };
      }
    ).BarcodeDetector;
    if (!BD) {
      setScanError('Scanner indisponible sur ce navigateur — saisissez le code.');
      return;
    }
    let stream: MediaStream | null = null;
    let raf = 0;
    const detector = new BD({ formats: ['qr_code'] });
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        const tick = async () => {
          if (!videoRef.current) return;
          try {
            const codes = await detector.detect(videoRef.current);
            const found = codes[0] && parsePayload(codes[0].rawValue);
            if (found) {
              setTarget(found);
              return;
            }
          } catch {
            /* frame sans code */
          }
          raf = requestAnimationFrame(() => void tick());
        };
        raf = requestAnimationFrame(() => void tick());
      } catch {
        setScanError('Caméra inaccessible — saisissez le code.');
      }
    })();
    return () => {
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((tr) => tr.stop());
    };
  }, [target, receipt]);

  async function doPay() {
    if (!target) return;
    try {
      const r = await pay.mutateAsync({
        merchant_id: target.merchantId,
        charge_id: target.chargeId,
        amount_minor: target.chargeId ? undefined : amount,
      });
      setReceipt(r);
      setConfirm(false);
      toast.success('Paiement effectué.');
    } catch (e) {
      toast.error(e);
    }
  }

  if (receipt) {
    return (
      <div>
        <PageHeader title="Reçu" back={false} />
        <Receipt data={receipt} />
        <Button block style={{ marginTop: 'var(--space-4)' }} onClick={() => window.history.back()}>
          Terminer
        </Button>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Payer un marchand" />
      {!target ? (
        <Card style={{ display: 'grid', gap: 'var(--space-3)' }}>
          {!scanError ? (
            <video
              ref={videoRef}
              muted
              playsInline
              style={{
                width: '100%',
                borderRadius: 'var(--radius-md)',
                background: '#000',
                aspectRatio: '1',
              }}
            />
          ) : (
            <p className="ui-hint">{scanError}</p>
          )}
          <Input
            label="Code marchand"
            placeholder="flash://pay?m=…"
            value={manual}
            onChange={(e) => setManual(e.target.value)}
          />
          <Button
            variant="secondary"
            disabled={!parsePayload(manual)}
            onClick={() => setTarget(parsePayload(manual))}
          >
            Utiliser ce code
          </Button>
        </Card>
      ) : (
        <Card style={{ display: 'grid', gap: 'var(--space-4)' }}>
          <p className="ui-hint">Marchand : {target.merchantId}</p>
          {target.chargeId ? (
            <p>Montant pré-rempli par le marchand.</p>
          ) : (
            <AmountField currency={currency} value={amount} onChange={setAmount} />
          )}
          <Button block disabled={!target.chargeId && amount <= 0} onClick={() => setConfirm(true)}>
            Payer
          </Button>
        </Card>
      )}

      <ConfirmSheet
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={doPay}
        busy={pay.isPending}
        title="Confirmer le paiement"
        summary={<p>Paiement au marchand {target?.merchantId}.</p>}
      />
    </div>
  );
}
