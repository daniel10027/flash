// WEB-025 — coffre : poches, créer / renommer / supprimer, déplacer, verrou.
import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  ListRow,
  Money,
  Sheet,
  Skeleton,
} from '@shared/ui';
import { AmountField, PageHeader } from '@features/common/kit';
import { usePrimaryWallet, useVault, useVaultActions } from '@shared/api/hooks';
import { toast } from '@shared/ui';
import { formatDate } from '@shared/i18n/format';
import type { VaultPocket } from '@shared/api/types';

export function VaultPage() {
  const { wallet } = usePrimaryWallet();
  const currency = wallet?.currency ?? 'XOF';
  const vault = useVault();
  const a = useVaultActions();

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [move, setMove] = useState<{ pocket: VaultPocket; dir: 'deposit' | 'withdraw' } | null>(
    null,
  );
  const [amount, setAmount] = useState(0);

  async function create() {
    try {
      await a.create.mutateAsync({ name: name.trim() });
      setCreating(false);
      setName('');
    } catch (e) {
      toast.error(e);
    }
  }

  async function applyMove() {
    if (!move) return;
    try {
      await (move.dir === 'deposit' ? a.deposit : a.withdraw).mutateAsync({
        id: move.pocket.pocket_id,
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
        title="Coffre"
        subtitle={wallet ? `Réservé : ${''}` : undefined}
        action={
          <Button size="sm" onClick={() => setCreating(true)}>
            Nouvelle poche
          </Button>
        }
      />
      {wallet && wallet.reserved_minor > 0 && (
        <p className="ui-hint" style={{ marginBottom: 'var(--space-3)' }}>
          Part du solde réservée : <Money amountMinor={wallet.reserved_minor} currency={currency} />
        </p>
      )}

      {vault.isLoading ? (
        <Card>
          <Skeleton height={64} />
        </Card>
      ) : (vault.data?.pockets ?? []).length === 0 ? (
        <Card>
          <EmptyState title="Aucune poche" description="Mettez de l’argent de côté par objectif." />
        </Card>
      ) : (
        <Card style={{ padding: 0 }}>
          {vault.data!.pockets.map((p) => {
            const locked = p.locked_until && new Date(p.locked_until) > new Date();
            return (
              <ListRow
                key={p.pocket_id}
                title={
                  <span
                    style={{ display: 'inline-flex', gap: 'var(--space-2)', alignItems: 'center' }}
                  >
                    {p.name}
                    {locked && <Badge tone="warning">🔒 {formatDate(p.locked_until!)}</Badge>}
                  </span>
                }
                subtitle={
                  p.goal_minor
                    ? `Objectif ${Math.round((p.balance_minor / p.goal_minor) * 100)}%`
                    : undefined
                }
                trailing={
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                    <Money amountMinor={p.balance_minor} currency={p.currency ?? currency} />
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setMove({ pocket: p, dir: 'deposit' })}
                    >
                      +
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={!!locked}
                      onClick={() => setMove({ pocket: p, dir: 'withdraw' })}
                    >
                      −
                    </Button>
                  </div>
                }
              />
            );
          })}
        </Card>
      )}

      <Sheet open={creating} onClose={() => setCreating(false)} title="Nouvelle poche">
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <Input label="Nom" value={name} onChange={(e) => setName(e.target.value)} />
          <Button block loading={a.create.isPending} disabled={!name.trim()} onClick={create}>
            Créer
          </Button>
        </div>
      </Sheet>

      <Sheet
        open={!!move}
        onClose={() => setMove(null)}
        title={move?.dir === 'deposit' ? 'Alimenter la poche' : 'Retirer de la poche'}
      >
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <p className="ui-hint">{move?.pocket.name}</p>
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
