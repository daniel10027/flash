// WEB-028 — mes numéros. WEB-029 — profil & KYC. WEB-031 — sécurité. WEB-032 — paramètres.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Badge, Button, Card, Input, ListRow, PinInput, Sheet, Skeleton, Tabs } from '@shared/ui';
import { PageHeader } from '@features/common/kit';
import { toast } from '@shared/ui';
import { api } from '@shared/api/client';
import { useKycStatus, usePhoneActions, usePhones } from '@shared/api/hooks';
import { useSession } from '@shared/auth/session';
import { useTheme } from '@app/theme';
import { usePrivacy } from '@features/layout/privacy';

const TABS = [
  { id: 'kyc', label: 'Identité' },
  { id: 'phones', label: 'Numéros' },
  { id: 'security', label: 'Sécurité' },
  { id: 'settings', label: 'Paramètres' },
];

export function ProfilePage() {
  const [tab, setTab] = useState('kyc');
  return (
    <div>
      <PageHeader title="Profil" back={false} />
      <Tabs ariaLabel="Sections du profil" items={TABS} value={tab} onChange={setTab} />
      <div style={{ marginTop: 'var(--space-4)' }}>
        {tab === 'kyc' && <KycSection />}
        {tab === 'phones' && <PhonesSection />}
        {tab === 'security' && <SecuritySection />}
        {tab === 'settings' && <SettingsSection />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ WEB-029 */
function KycSection() {
  const kyc = useKycStatus();
  const [busy, setBusy] = useState(false);

  async function submit(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      const documents = await Promise.all(
        [...files].slice(0, 6).map(
          (f) =>
            new Promise<{ kind: string; content_base64: string; content_type: string }>(
              (resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () =>
                  resolve({
                    kind: 'ID_DOCUMENT',
                    content_base64: String(reader.result).split(',')[1] ?? '',
                    content_type: f.type || 'image/jpeg',
                  });
                reader.onerror = reject;
                reader.readAsDataURL(f);
              },
            ),
        ),
      );
      await api.post('/v1/kyc/submissions', { target_tier: (kyc.data?.tier ?? 0) + 1, documents });
      toast.success('Dossier envoyé. Vérification en cours.');
      void kyc.refetch();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  }

  if (kyc.isLoading) return <Skeleton height={120} />;

  return (
    <Card style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong>Palier de vérification : {kyc.data?.tier ?? 0}</strong>
        <Badge tone={kyc.data?.status === 'APPROVED' ? 'success' : 'warning'}>
          {kyc.data?.status ?? 'NON VÉRIFIÉ'}
        </Badge>
      </div>
      <p className="ui-hint">
        Un palier supérieur augmente vos plafonds de transfert, de solde et de retrait.
      </p>
      {kyc.data?.pending_case_id ? (
        <p>Dossier en cours d’examen ({String(kyc.data.pending_case_id).slice(0, 8)}…).</p>
      ) : (
        <label className="ui-btn ui-btn--primary" style={{ cursor: 'pointer' }}>
          {busy ? '…' : 'Envoyer pièce d’identité + selfie'}
          <input
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => submit(e.target.files)}
          />
        </label>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ WEB-028 */
function PhonesSection() {
  const phones = usePhones();
  const a = usePhoneActions();
  const [adding, setAdding] = useState(false);
  const [phone, setPhone] = useState('');
  const [country, setCountry] = useState('CI');
  const [code, setCode] = useState('');
  const [pendingVerify, setPendingVerify] = useState<string | null>(null);

  return (
    <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <Button onClick={() => setAdding(true)}>Ajouter un numéro</Button>
      {phones.isLoading ? (
        <Skeleton height={64} />
      ) : (
        <Card style={{ padding: 0 }}>
          {(phones.data ?? []).map((p) => (
            <ListRow
              key={p.phone_number}
              title={p.masked ?? p.phone_number}
              subtitle={p.verified ? 'Vérifié' : 'Non vérifié'}
              trailing={
                <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                  {p.is_primary ? (
                    <Badge tone="success">Principal</Badge>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => a.setPrimary.mutate(p.phone_number)}
                    >
                      Définir principal
                    </Button>
                  )}
                  {!p.is_primary && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => a.remove.mutate(p.phone_number)}
                    >
                      Retirer
                    </Button>
                  )}
                </div>
              }
            />
          ))}
        </Card>
      )}
      <p className="ui-hint">5 numéros maximum par compte.</p>

      <Sheet open={adding} onClose={() => setAdding(false)} title="Ajouter un numéro">
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          {!pendingVerify ? (
            <>
              <Input label="Numéro" value={phone} onChange={(e) => setPhone(e.target.value)} />
              <Input
                label="Pays"
                maxLength={2}
                value={country}
                onChange={(e) => setCountry(e.target.value.toUpperCase())}
              />
              <Button
                block
                loading={a.add.isPending}
                disabled={!phone}
                onClick={async () => {
                  try {
                    await a.add.mutateAsync({ phone_number: phone.trim(), country });
                    setPendingVerify(phone.trim());
                    toast.info('Un code de vérification a été envoyé.');
                  } catch (e) {
                    toast.error(e);
                  }
                }}
              >
                Envoyer le code
              </Button>
            </>
          ) : (
            <>
              <PinInput label="Code reçu" length={6} value={code} onChange={setCode} />
              <Button
                block
                loading={a.verify.isPending}
                disabled={code.length < 6}
                onClick={async () => {
                  try {
                    await a.verify.mutateAsync({ phone_number: pendingVerify, code });
                    setAdding(false);
                    setPendingVerify(null);
                    setPhone('');
                    setCode('');
                    toast.success('Numéro ajouté.');
                  } catch (e) {
                    toast.error(e);
                  }
                }}
              >
                Vérifier
              </Button>
            </>
          )}
        </div>
      </Sheet>
    </div>
  );
}

/* ------------------------------------------------------------------ WEB-031 */
function SecuritySection() {
  const clear = useSession((s) => s.clear);
  return (
    <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <Card>
        <strong>Session</strong>
        <p className="ui-hint">
          Le changement de code secret et la liste des appareils connectés seront branchés quand
          l’API exposera ces endpoints (hors périmètre actuel).
        </p>
      </Card>
      <Button
        variant="danger"
        onClick={async () => {
          try {
            await api.post('/v1/auth/logout');
          } catch {
            /* on déconnecte localement quoi qu'il arrive */
          }
          clear();
        }}
      >
        Se déconnecter de cet appareil
      </Button>
    </div>
  );
}

/* ------------------------------------------------------------------ WEB-032 */
function SettingsSection() {
  const { t } = useTranslation();
  const theme = useTheme();
  const { hidden, toggle } = usePrivacy();
  return (
    <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <Card>
        <label className="ui-field">
          <span className="ui-label">{t('a11y.theme')}</span>
          <select
            className="ui-input"
            value={theme.mode}
            onChange={(e) => theme.setMode(e.target.value as 'light' | 'dark' | 'system')}
          >
            <option value="system">Système</option>
            <option value="light">Clair</option>
            <option value="dark">Sombre</option>
          </select>
        </label>
      </Card>
      <Card style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>Masquer les soldes par défaut</span>
        <Button
          size="sm"
          variant={hidden ? 'primary' : 'secondary'}
          onClick={toggle}
          aria-pressed={hidden}
        >
          {hidden ? 'Activé' : 'Désactivé'}
        </Button>
      </Card>
      <Card>
        <strong>À propos</strong>
        <p className="ui-hint">Flash — version {import.meta.env.MODE}. Mentions légales à venir.</p>
      </Card>
    </div>
  );
}
