// WEB-003 — galerie /ui : inventaire visuel des composants de base.
import { useState } from 'react';
import {
  Amount,
  Avatar,
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  ListRow,
  Money,
  PinInput,
  Sheet,
  Skeleton,
  Tabs,
  toast,
} from '@shared/ui';

export function UiGalleryPage() {
  const [pin, setPin] = useState('12');
  const [tab, setTab] = useState('a');
  const [sheet, setSheet] = useState(false);

  return (
    <div style={{ display: 'grid', gap: 'var(--space-5)' }}>
      <h1 style={{ fontSize: 'var(--text-2xl)' }}>Galerie UI</h1>

      <Section title="Boutons">
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <Button>Primaire</Button>
          <Button variant="secondary">Secondaire</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button loading>Chargement</Button>
          <Button disabled>Désactivé</Button>
          <Button size="sm">Petit</Button>
        </div>
      </Section>

      <Section title="Champs">
        <Input label="Numéro" placeholder="+225…" hint="Format international" />
        <Input label="Avec erreur" defaultValue="abc" error="Valeur invalide" />
        <PinInput label="Code secret" value={pin} onChange={setPin} />
      </Section>

      <Section title="Monnaie">
        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'baseline' }}>
          <Amount amountMinor={1_250_000} currency="XOF" />
          <Money amountMinor={80} currency="XOF" direction="out" sign />
          <Money amountMinor={50_000} currency="XOF" direction="in" sign />
        </div>
      </Section>

      <Section title="Divers">
        <div
          style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}
        >
          <Avatar name="Awa Diallo" />
          <Badge>Neutre</Badge>
          <Badge tone="success">Réussi</Badge>
          <Badge tone="warning">En attente</Badge>
          <Badge tone="danger">Échoué</Badge>
          <Skeleton width={120} />
        </div>
      </Section>

      <Section title="Tabs">
        <Tabs
          ariaLabel="Exemple"
          value={tab}
          onChange={setTab}
          items={[
            { id: 'a', label: 'Onglet A' },
            { id: 'b', label: 'Onglet B' },
          ]}
        />
        <p>Contenu : {tab}</p>
      </Section>

      <Section title="Lignes de liste">
        <Card style={{ padding: 0 }}>
          <ListRow
            leading={<Avatar name="Kofi B" />}
            title="Kofi Bamba"
            subtitle="+225 07 00 00 00 01"
            trailing={<Money amountMinor={25_000} currency="XOF" direction="in" sign />}
            onClick={() => toast.info('Ligne cliquée')}
          />
          <ListRow
            leading={<Avatar name="EDF" />}
            title="Facture électricité"
            subtitle="Aujourd’hui"
            trailing={<Money amountMinor={12_500} currency="XOF" direction="out" sign />}
          />
        </Card>
      </Section>

      <Section title="Sheet & Toast">
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button onClick={() => setSheet(true)}>Ouvrir la feuille</Button>
          <Button variant="secondary" onClick={() => toast.success('Enregistré')}>
            Toast succès
          </Button>
          <Button variant="danger" onClick={() => toast.error(new Error('Quelque chose a échoué'))}>
            Toast erreur
          </Button>
        </div>
        <Sheet open={sheet} onClose={() => setSheet(false)} title="Exemple de feuille">
          <EmptyState title="Contenu de la feuille" description="Fermez avec Échap ou ✕." />
        </Sheet>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ display: 'grid', gap: 'var(--space-3)' }}>
      <h2 style={{ fontSize: 'var(--text-lg)' }}>{title}</h2>
      {children}
    </section>
  );
}
