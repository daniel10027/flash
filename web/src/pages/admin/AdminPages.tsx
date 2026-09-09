// WEB-041..046 — écrans back-office.
import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  ListRow,
  Sheet,
  Skeleton,
  Tabs,
  toast,
} from '@shared/ui';
import {
  useAccountActions,
  useAccountNotes,
  useAdminAccount,
  useAdminAccounts,
  useAmlAlerts,
  useAudit,
  useJournal,
  useKycCase,
  useKycDocumentUrl,
  useKycQueue,
  useKycReview,
  useLimitRules,
  usePricingRules,
  useReferenceActions,
  useReviewAlert,
  useTrialBalance,
  useVerifyChain,
} from '@features/admin/hooks';
import { adminFetch } from '@features/admin/client';

/* ------------------------------------------------------------ table générique */
function DataTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (rows.length === 0) return <EmptyState title="Aucune ligne" />;
  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 'var(--text-sm)' }}>
        <thead>
          <tr>
            {cols.map((c) => (
              <th
                key={c}
                style={{
                  textAlign: 'left',
                  padding: 'var(--space-2)',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td
                  key={c}
                  style={{ padding: 'var(--space-2)', borderBottom: '1px solid var(--bg-sunken)' }}
                >
                  {r[c] == null
                    ? ''
                    : typeof r[c] === 'object'
                      ? JSON.stringify(r[c])
                      : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------ WEB-041 */
export function AdminAccountsPage() {
  const [q, setQ] = useState('');
  const [openId, setOpenId] = useState<string | null>(null);
  const accounts = useAdminAccounts(q);

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-xl)', marginBottom: 'var(--space-3)' }}>
        Comptes clients
      </h1>
      <Input
        placeholder="Rechercher (numéro, id, nom)…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div style={{ marginTop: 'var(--space-3)' }}>
        {accounts.isLoading ? (
          <Card>
            <Skeleton height={56} />
          </Card>
        ) : (
          <Card style={{ padding: 0 }}>
            {(accounts.data ?? []).map((acc, i) => (
              <ListRow
                key={String(acc.user_id ?? acc.id ?? i)}
                title={String(acc.msisdn ?? acc.masked ?? acc.user_id ?? '—')}
                subtitle={`KYC ${acc.kyc_tier ?? '?'} · ${acc.status ?? ''}`}
                onClick={() => setOpenId(String(acc.user_id ?? acc.id))}
              />
            ))}
          </Card>
        )}
      </div>
      <AccountSheet id={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

function AccountSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const detail = useAdminAccount(id);
  const notes = useAccountNotes(id);
  const actions = useAccountActions(id ?? '');
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');
  const [ref, setRef] = useState('');

  return (
    <Sheet open={!!id} onClose={onClose} title="Fiche client" variant="center">
      {detail.isLoading ? (
        <Skeleton height={160} />
      ) : detail.data ? (
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <DataTable rows={[detail.data]} />

          <fieldset
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
            }}
          >
            <legend>Gel / dégel (motif obligatoire)</legend>
            <Input
              placeholder="Motif…"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
              <Button
                size="sm"
                variant="danger"
                disabled={!reason}
                loading={actions.freeze.isPending}
                onClick={() => actions.freeze.mutate({ freeze: true, reason })}
              >
                Geler
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={!reason}
                onClick={() => actions.freeze.mutate({ freeze: false, reason })}
              >
                Dégeler
              </Button>
            </div>
          </fieldset>

          <fieldset
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
            }}
          >
            <legend>Contre-passation forcée</legend>
            <Input
              placeholder="Référence de l’opération"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
            />
            <Input
              placeholder="Motif…"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <Button
              size="sm"
              variant="danger"
              style={{ marginTop: 'var(--space-2)' }}
              disabled={!ref || !reason}
              loading={actions.forceReversal.isPending}
              onClick={() =>
                actions.forceReversal.mutate(
                  { reference: ref, reason },
                  {
                    onSuccess: () => toast.success('Contre-passation enregistrée.'),
                    onError: (e) => toast.error(e),
                  },
                )
              }
            >
              Forcer
            </Button>
          </fieldset>

          <fieldset
            style={{
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
            }}
          >
            <legend>Notes internes</legend>
            <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
              <Input
                placeholder="Ajouter une note…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button
                size="sm"
                disabled={!note}
                onClick={() => actions.addNote.mutate(note, { onSuccess: () => setNote('') })}
              >
                Ajouter
              </Button>
            </div>
            <ul style={{ marginTop: 'var(--space-2)', paddingLeft: 'var(--space-4)' }}>
              {(notes.data ?? []).map((n, i) => (
                <li key={i} className="ui-hint">
                  {String(n.body ?? n.note ?? '')}
                </li>
              ))}
            </ul>
          </fieldset>
        </div>
      ) : (
        <EmptyState title="Introuvable" />
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------ WEB-042 */
const KYC_STATUSES = ['PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN'];

export function AdminKycPage() {
  const [status, setStatus] = useState('PENDING');
  const queue = useKycQueue(status);
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-xl)', marginBottom: 'var(--space-3)' }}>
        Vérifications KYC
      </h1>
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        {KYC_STATUSES.map((s) => (
          <Button key={s} variant={s === status ? 'primary' : 'ghost'} onClick={() => setStatus(s)}>
            {s}
          </Button>
        ))}
      </div>

      {queue.isLoading ? (
        <Skeleton height={160} />
      ) : queue.data && queue.data.length > 0 ? (
        <Card style={{ display: 'grid', gap: 'var(--space-1)' }}>
          {queue.data.map((c) => (
            <ListRow
              key={c.case_id}
              title={`Dossier ${c.case_id.slice(0, 8)}`}
              subtitle={String(c.target_tier ? `Palier visé ${c.target_tier}` : c.status)}
              trailing={
                <Button variant="ghost" onClick={() => setOpenId(c.case_id)}>
                  Ouvrir
                </Button>
              }
            />
          ))}
        </Card>
      ) : (
        <EmptyState title="Aucun dossier" description={`Rien avec le statut ${status}.`} />
      )}

      <KycCaseSheet caseId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}

function KycCaseSheet({ caseId, onClose }: { caseId: string | null; onClose: () => void }) {
  const detail = useKycCase(caseId);
  const review = useKycReview();
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<string | null>(null);
  const doc = useKycDocumentUrl(caseId, preview);

  return (
    <Sheet open={!!caseId} onClose={onClose} title="Dossier KYC" variant="center">
      {detail.isLoading || !detail.data ? (
        <Skeleton height={200} />
      ) : (
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <DataTable rows={[{ ...detail.data, documents: undefined }]} />

          <div style={{ display: 'grid', gap: 'var(--space-2)' }}>
            <strong>Pièces justificatives</strong>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
              {detail.data.documents.map((d) => (
                <Button
                  key={d.kind}
                  variant={preview === d.kind ? 'primary' : 'ghost'}
                  onClick={() => setPreview(d.kind)}
                >
                  {d.kind} · {(d.byte_size / 1024).toFixed(0)} Ko
                </Button>
              ))}
            </div>
            {preview &&
              (doc.error ? (
                <p className="ui-hint">Impossible de charger la pièce.</p>
              ) : doc.url ? (
                <img
                  src={doc.url}
                  alt={`Pièce ${preview}`}
                  style={{ maxWidth: '100%', borderRadius: 'var(--radius-md)' }}
                />
              ) : (
                <Skeleton height={180} />
              ))}
          </div>

          <Input
            label="Motif (requis pour un rejet)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button
              disabled={!caseId}
              loading={review.isPending}
              onClick={() =>
                review.mutate(
                  { case_id: caseId as string, approve: true },
                  {
                    onSuccess: () => {
                      toast.success('Dossier approuvé.');
                      onClose();
                    },
                    onError: (e) => toast.error(e),
                  },
                )
              }
            >
              Approuver
            </Button>
            <Button
              variant="danger"
              disabled={!caseId || !reason}
              onClick={() =>
                review.mutate(
                  { case_id: caseId as string, approve: false, reason },
                  {
                    onSuccess: () => {
                      toast.info('Dossier rejeté.');
                      onClose();
                    },
                    onError: (e) => toast.error(e),
                  },
                )
              }
            >
              Rejeter
            </Button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

/* ------------------------------------------------------------ WEB-043 */
export function AdminAmlPage() {
  const [status, setStatus] = useState('OPEN');
  const alerts = useAmlAlerts(status);
  const review = useReviewAlert();
  const [note, setNote] = useState('');
  const [active, setActive] = useState<string | null>(null);

  function exportStr() {
    const now = new Date();
    const start = new Date(now.getTime() - 30 * 864e5).toISOString().slice(0, 10);
    adminFetch<string>('/v1/admin/compliance/reports/str', {
      raw: true,
      query: { start, end: now.toISOString().slice(0, 10) },
    })
      .then((csv) => {
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = 'str.csv';
        link.click();
        URL.revokeObjectURL(url);
      })
      .catch((e) => toast.error(e));
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--space-3)',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-xl)' }}>Alertes AML</h1>
        <Button size="sm" variant="secondary" onClick={exportStr}>
          Export STR (CSV)
        </Button>
      </div>
      <Tabs
        ariaLabel="Statut"
        value={status}
        onChange={setStatus}
        items={[
          { id: 'OPEN', label: 'Ouvertes' },
          { id: 'REVIEWING', label: 'En revue' },
          { id: 'all', label: 'Toutes' },
        ]}
      />
      <div style={{ marginTop: 'var(--space-3)' }}>
        {alerts.isLoading ? (
          <Card>
            <Skeleton height={56} />
          </Card>
        ) : (
          <Card style={{ padding: 0 }}>
            {(alerts.data ?? []).map((al, i) => {
              const alertId = String(al.alert_id ?? al.id ?? i);
              return (
                <ListRow
                  key={alertId}
                  title={String(al.kind ?? '—')}
                  subtitle={`${al.user_id ?? ''} · score ${al.score ?? '?'}`}
                  trailing={
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                      <Badge tone={al.status === 'OPEN' ? 'warning' : 'neutral'}>
                        {String(al.status ?? '')}
                      </Badge>
                      <Button size="sm" onClick={() => setActive(alertId)}>
                        Statuer
                      </Button>
                    </div>
                  }
                />
              );
            })}
          </Card>
        )}
      </div>

      <Sheet open={!!active} onClose={() => setActive(null)} title="Statuer sur l’alerte">
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <Input label="Note (requise)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Button
              disabled={!note}
              loading={review.isPending}
              onClick={() =>
                review.mutate(
                  { alert_id: active!, decision: 'clear', note },
                  {
                    onSuccess: () => {
                      setActive(null);
                      setNote('');
                      toast.success('Alerte classée.');
                    },
                    onError: (e) => toast.error(e),
                  },
                )
              }
            >
              Classer (faux positif)
            </Button>
            <Button
              variant="danger"
              disabled={!note}
              onClick={() =>
                review.mutate(
                  { alert_id: active!, decision: 'escalate', note },
                  {
                    onSuccess: () => {
                      setActive(null);
                      setNote('');
                      toast.info('Alerte escaladée + gel préventif.');
                    },
                    onError: (e) => toast.error(e),
                  },
                )
              }
            >
              Escalader (STR + gel)
            </Button>
          </div>
        </div>
      </Sheet>
    </div>
  );
}

/* ------------------------------------------------------------ WEB-044 */
export function AdminReferencePage() {
  const pricing = usePricingRules();
  const limits = useLimitRules();
  const a = useReferenceActions();
  const [tab, setTab] = useState('pricing');

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--space-3)',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-xl)' }}>Référentiel</h1>
        <Button
          size="sm"
          variant="secondary"
          loading={a.reload.isPending}
          onClick={() => a.reload.mutate()}
        >
          Recharger le cache
        </Button>
      </div>
      <Tabs
        ariaLabel="Type"
        value={tab}
        onChange={setTab}
        items={[
          { id: 'pricing', label: 'Grille tarifaire' },
          { id: 'limits', label: 'Plafonds' },
        ]}
      />
      <Card style={{ marginTop: 'var(--space-3)' }}>
        {tab === 'pricing' ? (
          pricing.isLoading ? (
            <Skeleton height={80} />
          ) : (
            <DataTable rows={pricing.data ?? []} />
          )
        ) : limits.isLoading ? (
          <Skeleton height={80} />
        ) : (
          <DataTable rows={limits.data ?? []} />
        )}
      </Card>
      <p className="ui-hint" style={{ marginTop: 'var(--space-2)' }}>
        Édition ligne à ligne (frais 0,8 % par pays, plafonds par palier) via <code>PUT</code> /{' '}
        <code>DELETE</code> sur <code>/v1/admin/reference/pricing|limits/…</code> — chaque mutation
        est auditée.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------ WEB-045 */
export function AdminFinancePage() {
  const today = new Date().toISOString().slice(0, 10);
  const [asOf, setAsOf] = useState(today);
  const [start, setStart] = useState(today);
  const [end, setEnd] = useState(today);
  const tb = useTrialBalance(asOf);
  const journal = useJournal(start, end);

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-xl)', marginBottom: 'var(--space-3)' }}>Finance</h1>

      <Card style={{ marginBottom: 'var(--space-4)' }}>
        <h2 style={{ fontSize: 'var(--text-lg)' }}>Balance générale</h2>
        <Input
          type="date"
          label="À la date"
          value={asOf}
          onChange={(e) => setAsOf(e.target.value)}
        />
        {tb.isLoading ? (
          <Skeleton height={80} />
        ) : tb.data ? (
          <>
            <p style={{ margin: 'var(--space-2) 0' }}>
              Équilibrée :{' '}
              <Badge tone={tb.data.balanced ? 'success' : 'danger'}>
                {tb.data.balanced ? 'oui' : 'NON'}
              </Badge>
            </p>
            <DataTable rows={(tb.data.rows as Array<Record<string, unknown>>) ?? []} />
          </>
        ) : null}
      </Card>

      <Card>
        <h2 style={{ fontSize: 'var(--text-lg)' }}>Journal des écritures</h2>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Input type="date" label="Du" value={start} onChange={(e) => setStart(e.target.value)} />
          <Input type="date" label="Au" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        <a
          className="ui-btn ui-btn--secondary ui-btn--sm"
          style={{ marginTop: 'var(--space-2)' }}
          href={`/v1/admin/reports/monthly?year=${start.slice(0, 4)}&month=${start.slice(5, 7)}`}
        >
          Export mensuel (CSV)
        </a>
        {journal.isLoading ? (
          <Skeleton height={80} />
        ) : (
          <div style={{ marginTop: 'var(--space-2)' }}>
            <DataTable rows={journal.data ?? []} />
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------ WEB-046 */
export function AdminAuditPage() {
  const [actor, setActor] = useState('');
  const [action, setAction] = useState('');
  const audit = useAudit({ actor, action });
  const verify = useVerifyChain();
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--space-3)',
        }}
      >
        <h1 style={{ fontSize: 'var(--text-xl)' }}>Registre d’audit</h1>
        <Button
          size="sm"
          variant="secondary"
          loading={verify.isPending}
          onClick={() =>
            verify.mutate(undefined, { onSuccess: setReport, onError: (e) => toast.error(e) })
          }
        >
          Contrôler l’intégrité
        </Button>
      </div>
      {report && (
        <Card style={{ marginBottom: 'var(--space-3)' }}>
          Chaîne{' '}
          <Badge tone={report.intact ? 'success' : 'danger'}>
            {report.intact ? 'intègre' : `rompue @ ${report.broken_at}`}
          </Badge>{' '}
          — {String(report.checked)} entrées vérifiées
        </Card>
      )}
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
        <Input
          placeholder="Filtrer par acteur"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        />
        <Input
          placeholder="Filtrer par action"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        />
      </div>
      <Card>
        {audit.isLoading ? (
          <Skeleton height={120} />
        ) : (
          <DataTable rows={audit.data?.entries ?? []} />
        )}
      </Card>
    </div>
  );
}
