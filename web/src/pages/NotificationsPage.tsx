// WEB-030 — centre de notifications : liste, temps réel (SSE), marquage lu.
import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Card, EmptyState, ListRow, Skeleton } from '@shared/ui';
import { PageHeader } from '@features/common/kit';
import { qk, useNotificationActions, useNotifications } from '@shared/api/hooks';
import { config } from '@shared/config/runtime';
import { getAccessToken } from '@shared/auth/session';
import { formatRelative } from '@shared/i18n/format';

export function NotificationsPage() {
  const list = useNotifications();
  const actions = useNotificationActions();
  const qc = useQueryClient();

  // SSE : à chaque évènement, on invalide la liste (rattrapage via Last-Event-ID géré serveur).
  useEffect(() => {
    const token = getAccessToken();
    if (!token) return;
    const base = config.API_BASE_URL.replace(/\/$/, '');
    const url = `${base}/v1/notifications/stream?access_token=${encodeURIComponent(token)}`;
    let es: EventSource | null = null;
    try {
      es = new EventSource(url, { withCredentials: true });
      es.onmessage = () => void qc.invalidateQueries({ queryKey: qk.notifications });
    } catch {
      /* SSE indisponible : la liste reste rafraîchie au focus / à la navigation */
    }
    return () => es?.close();
  }, [qc]);

  const items = list.data?.notifications ?? [];
  const unread = items.filter((n) => !n.read_at).length;

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle={unread ? `${unread} non lue(s)` : undefined}
        action={
          unread ? (
            <Button size="sm" variant="ghost" onClick={() => actions.markAll.mutate()}>
              Tout marquer lu
            </Button>
          ) : undefined
        }
      />
      {list.isLoading ? (
        <Card>
          <Skeleton height={56} />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState title="Aucune notification" />
        </Card>
      ) : (
        <Card style={{ padding: 0 }}>
          {items.map((n) => (
            <ListRow
              key={n.id}
              title={n.title}
              subtitle={`${n.body} · ${formatRelative(n.created_at)}`}
              trailing={
                n.read_at ? null : (
                  <Button size="sm" variant="ghost" onClick={() => actions.markRead.mutate(n.id)}>
                    <Badge tone="danger">Nouveau</Badge>
                  </Button>
                )
              }
            />
          ))}
        </Card>
      )}
    </div>
  );
}
