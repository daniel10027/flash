// WEB-014 — connexion : numéro + code secret, OTP si demandé, code secret oublié
// (réinitialisation par OTP).
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, PinInput, toast } from '@shared/ui';
import { useSession } from '@shared/auth/session';
import { confirmPinReset, login, requestPinReset, resendOtp, verifyOtp } from '@features/auth/api';

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const setSession = useSession((s) => s.setSession);

  const [phone, setPhone] = useState('');
  const [country, setCountry] = useState('CI');
  const [pin, setPin] = useState('');
  const [code, setCode] = useState('');
  const [newPin, setNewPin] = useState('');
  const [step, setStep] = useState<'credentials' | 'otp' | 'reset_request' | 'reset_confirm'>(
    'credentials',
  );
  const [busy, setBusy] = useState(false);

  const goHome = () => navigate(location.state?.from ?? '/', { replace: true });

  async function submitCredentials(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await login({ phone_number: phone, country, pin });
      if (res.kind === 'authenticated') {
        setSession(res.tokens);
        goHome();
      } else {
        setStep('otp');
        toast.info('Un code de vérification vous a été envoyé.');
      }
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function submitOtp(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const tokens = await verifyOtp({ phone_number: phone, country, code });
      setSession(tokens);
      goHome();
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function submitResetRequest(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await requestPinReset({ phone_number: phone, country });
      setStep('reset_confirm');
      toast.info('Si ce numéro a un compte, un code vient d’être envoyé.');
    } catch (err) {
      toast.error(err);
    } finally {
      setBusy(false);
    }
  }

  async function submitResetConfirm(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await confirmPinReset({ phone_number: phone, country, code, new_pin: newPin });
      setStep('credentials');
      setPin('');
      setCode('');
      setNewPin('');
      toast.success('Code secret réinitialisé. Connectez-vous.');
    } catch (err) {
      toast.error(err);
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
        <h1 style={{ fontSize: 'var(--text-2xl)' }}>{t('auth.signIn')}</h1>

        {step === 'credentials' && (
          <form onSubmit={submitCredentials} style={{ display: 'grid', gap: 'var(--space-3)' }}>
            <Input
              label={t('auth.phone')}
              inputMode="tel"
              autoComplete="tel"
              placeholder="+225…"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
            />
            <Input
              label="Pays"
              value={country}
              maxLength={2}
              onChange={(e) => setCountry(e.target.value.toUpperCase())}
              required
            />
            <PinInput label={t('auth.pin')} value={pin} onChange={setPin} />
            <Button type="submit" block loading={busy} disabled={pin.length < 4 || !phone}>
              {t('common.continue')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={!phone}
              onClick={() => setStep('reset_request')}
            >
              {t('auth.forgotPin')}
            </Button>
          </form>
        )}

        {step === 'otp' && (
          <form onSubmit={submitOtp} style={{ display: 'grid', gap: 'var(--space-3)' }}>
            <PinInput label={t('auth.otp')} length={6} value={code} onChange={setCode} />
            <Button type="submit" block loading={busy} disabled={code.length < 6}>
              {t('auth.signIn')}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                void resendOtp({ phone_number: phone, country }).then(
                  () => toast.info('Nouveau code envoyé.'),
                  (e) => toast.error(e),
                );
              }}
            >
              Renvoyer le code
            </Button>
            <Button type="button" variant="ghost" onClick={() => setStep('credentials')}>
              {t('common.back')}
            </Button>
          </form>
        )}

        {step === 'reset_request' && (
          <form onSubmit={submitResetRequest} style={{ display: 'grid', gap: 'var(--space-3)' }}>
            <p className="ui-hint">
              Nous enverrons un code de vérification au {phone || 'numéro saisi'}.
            </p>
            <Button type="submit" block loading={busy} disabled={!phone}>
              Envoyer le code
            </Button>
            <Button type="button" variant="ghost" onClick={() => setStep('credentials')}>
              {t('common.back')}
            </Button>
          </form>
        )}

        {step === 'reset_confirm' && (
          <form onSubmit={submitResetConfirm} style={{ display: 'grid', gap: 'var(--space-3)' }}>
            <PinInput label={t('auth.otp')} length={6} value={code} onChange={setCode} />
            <PinInput label="Nouveau code secret" value={newPin} onChange={setNewPin} />
            <Button
              type="submit"
              block
              loading={busy}
              disabled={code.length < 6 || newPin.length < 4}
            >
              Réinitialiser
            </Button>
            <Button type="button" variant="ghost" onClick={() => setStep('reset_request')}>
              {t('common.back')}
            </Button>
          </form>
        )}

        {step === 'credentials' && (
          <p className="ui-hint" style={{ textAlign: 'center' }}>
            Pas de compte ? <Link to="/register">Créer un compte</Link>
          </p>
        )}
      </Card>
    </main>
  );
}
