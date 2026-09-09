// Écrans du parcours client à venir (WEB-016+). Coquille en attendant.
import { EmptyState } from '@shared/ui';

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <EmptyState
      title={title}
      description="Cet écran sera livré dans un lot ultérieur du parcours client."
    />
  );
}
