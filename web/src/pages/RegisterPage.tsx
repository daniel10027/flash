// WEB-013 — inscription : numéro + pays, création du code secret, OTP, succès.
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Input, PinInput, toast } from '@shared/ui';
import { useSession } from '@shared/auth/session';
import { register, verifyOtp } from '@features/auth/api';

type Step = 'form' | 'confirm-pin' | 'otp' | 'done';

export function RegisterPage() {
  const navigate = useNavigate();
  const setSession = useSession((s) => s.setSession);

  const [step, setStep] = useState<Step>('form');
  const [phone, setPhone] = useState('');
  const [country, setCountry] = useState('CI');
  const [pin, setPin] = useState('');
  const [pin2, setPin2] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);

  async function create() {
    setBusy(true);
    try {
      await register({ phone_number: phone.trim(), country, pin });
      setStep('otp');
      toast.info('Un code de vérification vous a été envoyé.');
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      const tokens = await verifyOtp({ phone_number: phone.trim(), country, code });
      setSession(tokens);
      setStep('done');
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        minHeight: '100dvh',
        display: 'grid',
        placeItems: 'center',
        padding: 'var(--space-4)',
      }}
    >
      <Card style={{ width: 'min(380px, 100%)', display: 'grid', gap: 'var(--space-4)' }}>
        <h1 style={{ fontSize: 'var(--text-2xl)' }}>Créer un compte</h1>

        {step === 'form' && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setStep('confirm-pin');
            }}
            style={{ display: 'grid', gap: 'var(--space-3)' }}
          >
            <Input
              label="Numéro de téléphone"
              inputMode="tel"
              placeholder="+225…"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
            <Input
              label="Pays"
              maxLength={2}
              value={country}
              onChange={(e) => setCountry(e.target.value.toUpperCase())}
              required
            />
            <PinInput label="Choisir un code secret" value={pin} onChange={setPin} />
            <Button type="submit" block disabled={pin.length < 4 || !phone}>
              Continuer
            </Button>
          </form>
        )}

        {step === 'confirm-pin' && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (pin2 !== pin) {
                toast.error(new Error('Les codes ne correspondent pas.'));
                return;
              }
              void create();
            }}
            style={{ display: 'grid', gap: 'var(--space-3)' }}
          >
            <PinInput label="Confirmez le code secret" value={pin2} onChange={setPin2} />
            <Button type="submit" block loading={busy} disabled={pin2.length < 4}>
              Créer le compte
            </Button>
            <Button type="button" variant="ghost" onClick={() => setStep('form')}>
              Retour
            </Button>
          </form>
        )}

        {step === 'otp' && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void confirm();
            }}
            style={{ display: 'grid', gap: 'var(--space-3)' }}
          >
            <PinInput label="Code de vérification" length={6} value={code} onChange={setCode} />
            <Button type="submit" block loading={busy} disabled={code.length < 6}>
              Valider
            </Button>
          </form>
        )}

        {step === 'done' && (
          <div style={{ display: 'grid', gap: 'var(--space-3)', textAlign: 'center' }}>
            <p style={{ fontSize: 'var(--text-2xl)' }}>🎉</p>
            <p>Votre compte est prêt.</p>
            <Button block onClick={() => navigate('/', { replace: true })}>
              Commencer
            </Button>
          </div>
        )}

        {step !== 'done' && (
          <p className="ui-hint" style={{ textAlign: 'center' }}>
            Déjà un compte ? <Link to="/login">Se connecter</Link>
          </p>
        )}
      </Card>
    </main>
  );
}
