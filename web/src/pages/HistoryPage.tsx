// WEB-023 / WEB-024 — historique paginé (scroll infini), filtres, groupement par jour ;
// détail via une feuille (reçu).
import { useEffect, useMemo, useRef, useState } from 'react';
import { Badge, Card, EmptyState, Input, ListRow, Money, Sheet, Skeleton, Tabs } from '@shared/ui';
import { PageHeader, Receipt } from '@features/common/kit';
import { useReceipt, useStatement } from '@shared/api/hooks';
import { formatDate } from '@shared/i18n/format';
import type { StatementLine } from '@shared/api/types';

const FILTERS = [
  { id: 'all', label: 'Tout' },
  { id: 'in', label: 'Reçus' },
  { id: 'out', label: 'Envoyés' },
];

export function HistoryPage() {
  const q = useStatement({ limit: 25 });
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<StatementLine | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && q.hasNextPage && !q.isFetchingNextPage) {
        void q.fetchNextPage();
      }
    });
    io.observe(el);
    return () => io.disconnect();
  }, [q]);

  const groups = useMemo(() => {
    const lines = (q.data?.pages ?? []).flatMap((p) => p.lines);
    const filtered = lines.filter((l) => {
      if (filter !== 'all' && l.direction !== filter) return false;
      if (
        search &&
        !`${l.counterparty_masked ?? ''} ${l.reference} ${l.kind}`
          .toLowerCase()
          .includes(search.toLowerCase())
      )
        return false;
      return true;
    });
    const byDay = new Map<string, StatementLine[]>();
    for (const l of filtered) {
      const day = l.occurred_at.slice(0, 10);
      byDay.set(day, [...(byDay.get(day) ?? []), l]);
    }
    return [...byDay.entries()];
  }, [q.data, filter, search]);

  return (
    <div>
      <PageHeader title="Historique" />
      <div style={{ display: 'grid', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <Input
          placeholder="Rechercher (référence, contrepartie)…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Tabs ariaLabel="Filtre" items={FILTERS} value={filter} onChange={setFilter} />
      </div>

      {q.isLoading ? (
        <Card>
          <Skeleton height={64} />
        </Card>
      ) : groups.length === 0 ? (
        <Card>
          <EmptyState title="Aucune opération" />
        </Card>
      ) : (
        groups.map(([day, items]) => (
          <section key={day} style={{ marginBottom: 'var(--space-4)' }}>
            <h2 className="ui-hint" style={{ marginBottom: 'var(--space-1)' }}>
              {formatDate(day, 'long')}
            </h2>
            <Card style={{ padding: 0 }}>
              {items.map((l) => (
                <ListRow
                  key={l.id}
                  title={l.counterparty_masked ?? l.kind}
                  subtitle={`${l.reference}`}
                  trailing={
                    <Money
                      amountMinor={l.amount_minor}
                      currency={l.currency}
                      direction={l.direction}
                      sign
                    />
                  }
                  onClick={() => setSelected(l)}
                />
              ))}
            </Card>
          </section>
        ))
      )}
      <div ref={sentinel} style={{ height: 1 }} />
      {q.isFetchingNextPage && <p className="ui-hint">Chargement…</p>}

      <OperationSheet line={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function OperationSheet({ line, onClose }: { line: StatementLine | null; onClose: () => void }) {
  const receipt = useReceipt(line?.reference ?? null);
  return (
    <Sheet open={!!line} onClose={onClose} title="Détail de l’opération">
      {line && (
        <div style={{ display: 'grid', gap: 'var(--space-3)' }}>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <Money
              amountMinor={line.amount_minor}
              currency={line.currency}
              direction={line.direction}
              sign
            />
            <Badge tone={line.direction === 'in' ? 'success' : 'neutral'}>{line.kind}</Badge>
          </div>
          {line.fee_minor > 0 && (
            <p className="ui-hint">
              Frais : <Money amountMinor={line.fee_minor} currency={line.currency} />
            </p>
          )}
          {receipt.isLoading ? (
            <Skeleton height={120} />
          ) : receipt.data ? (
            <Receipt data={receipt.data} />
          ) : (
            <p className="ui-hint">Reçu indisponible.</p>
          )}
        </div>
      )}
    </Sheet>
  );
}
