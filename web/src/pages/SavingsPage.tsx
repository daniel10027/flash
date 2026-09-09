// WEB-026 — épargne : ouvrir un plan, progression, intérêts, versement, clôture.
import { useState } from 'react';
import { Badge, Button, Card, EmptyState, Input, Money, Sheet, Skeleton } from '@shared/ui';
import { AmountField, PageHeader } from '@features/common/kit';
import { usePrimaryWallet, useSavingsActions, useSavingsPlans } from '@shared/api/hooks';
import { toast } from '@shared/ui';
import type { SavingsPlan } from '@shared/api/types';

const FREQ = ['NONE', 'WEEKLY', 'MONTHLY'];

export function SavingsPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const plans = useSavingsPlans();
  const a = useSavingsActions();

  const [opening, setOpening] = useState(false);
  const [form, setForm] = useState({ name: '', target: 0, frequency: 'NONE', contribution: 0 });
  const [move, setMove] = useState<{ plan: SavingsPlan; dir: 'deposit' | 'withdraw' } | null>(null);
  const [amount, setAmount] = useState(0);

  async function open() {
    try {
      await a.open.mutateAsync({
        name: form.name.trim(),
        target_minor: form.target || undefined,
        frequency: form.frequency,
        contribution_minor: form.contribution || undefined,
      });
      setOpening(false);
      setForm({ name: '', target: 0, frequency: 'NONE', contribution: 0 });
    } catch (e) {
      toast.error(e);
    }
  }

  async function applyMove() {
    if (!move) return;
    try {
      await (move.dir === 'deposit' ? a.deposit : a.withdraw).mutateAsync({
        id: move.plan.plan_id,
        amount_minor: amount,
      });
      setMove(null);
      setAmount(0);
    } catch (e) {
      toast.error(e);
    }
  }

  return (
    <div>
      <PageHeader
        title="Épargne"
        action={
          <Button size="sm" onClick={() => setOpening(true)}>
            Nouveau plan
          </Button>
        }
      />
      {plans.isLoading ? (
        <Card>
          <Skeleton height={64} />
        </Card>
      ) : (plans.data ?? []).length === 0 ? (
        <Card>
          <EmptyState title="Aucun plan d’épargne" description="Fixez-vous un objectif." />
        </Card>
      ) : (
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          {plans.data!.map((p) => (
            <Card key={p.plan_id}>
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              >
                <strong>{p.name}</strong>
                <Badge tone={p.status === 'ACTIVE' ? 'success' : 'neutral'}>{p.status}</Badge>
              </div>
              <p style={{ fontSize: 'var(--text-xl)', fontWeight: 'var(--weight-semibold)' }}>
                <Money amountMinor={p.balance_minor} currency={p.currency ?? currency} />
              </p>
              {p.target_minor ? (
                <div
                  style={{
                    height: 8,
                    background: 'var(--bg-sunken)',
                    borderRadius: 'var(--radius-full)',
                    overflow: 'hidden',
                    margin: 'var(--space-2) 0',
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(100, Math.round((p.balance_minor / p.target_minor) * 100))}%`,
                      height: '100%',
                      background: 'var(--primary)',
                    }}
                  />
                </div>
              ) : null}
              {typeof p.accrued_interest_minor === 'number' && p.accrued_interest_minor > 0 && (
                <p className="ui-hint">
                  Intérêts cumulés :{' '}
                  <Money amountMinor={p.accrued_interest_minor} currency={currency} />
                </p>
              )}
              <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
                <Button size="sm" onClick={() => setMove({ plan: p, dir: 'deposit' })}>
                  Verser
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setMove({ plan: p, dir: 'withdraw' })}
                >
                  Retirer
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => a.close.mutate(p.plan_id)}
                  disabled={p.status !== 'ACTIVE'}
                >
                  Clôturer
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Sheet open={opening} onClose={() => setOpening(false)} title="Nouveau plan d’épargne">
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <Input
            label="Nom"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <AmountField
            currency={currency}
            value={form.target}
            onChange={(v) => setForm({ ...form, target: v })}
            label="Objectif (facultatif)"
          />
          <label className="ui-field">
            <span className="ui-label">Versement automatique</span>
            <select
              className="ui-input"
              value={form.frequency}
              onChange={(e) => setForm({ ...form, frequency: e.target.value })}
            >
              {FREQ.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </label>
          {form.frequency !== 'NONE' && (
            <AmountField
              currency={currency}
              value={form.contribution}
              onChange={(v) => setForm({ ...form, contribution: v })}
              label="Montant du versement"
            />
          )}
          <Button block loading={a.open.isPending} disabled={!form.name.trim()} onClick={open}>
            Ouvrir le plan
          </Button>
        </div>
      </Sheet>

      <Sheet
        open={!!move}
        onClose={() => setMove(null)}
        title={move?.dir === 'deposit' ? 'Verser' : 'Retirer'}
      >
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <AmountField currency={currency} value={amount} onChange={setAmount} />
          <Button
            block
            loading={a.deposit.isPending || a.withdraw.isPending}
            disabled={amount <= 0}
            onClick={applyMove}
          >
            Valider
          </Button>
        </div>
      </Sheet>
    </div>
  );
}
