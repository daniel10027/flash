# Composants clés — specs (DSN-008)

Référence visuelle des écrans structurants. Les valeurs renvoient aux jetons de
`tokens.json`. Implémentations : web `web/src/shared/ui` + pages, mobile
`mobile/lib/shared/widgets` + features.

## Carte de solde

| Propriété | Valeur |
|---|---|
| Fond | dégradé `brand.500 → brand.700`, 135° |
| Rayon | `radius.xl` (24) |
| Ombre | `0 12px 30px rgba(140,29,51,.35)` |
| Padding | `space.5` (mobile 22) |
| Libellé | `font.size.sm`, `neutral.0` @ 70 % |
| Montant | `font.size.3xl`, poids 800, chiffres tabulaires, **count-up 700 ms** `easing.enter` |
| Ligne « réservés » | `font.size.xs`, `neutral.0` @ 60 %, visible si `reserved > 0` et soldes non masqués |

## Ligne d'historique

- Hauteur cible ≥ 56 ; zone tactile pleine largeur.
- **Leading** : pastille ronde 40, fond `neutral.100` (dark `neutral.800`), flèche
  `↙` entrée / `↗` sortie.
- **Titre** : contrepartie masquée ou type d'opération, 1 ligne, ellipse.
- **Sous-titre** : `référence · heure`, `neutral.500`.
- **Trailing** : montant signé, chiffres tabulaires ; entrée en `accent.500`,
  sortie en `neutral.900`. `+`/`−` explicite.
- Tap → feuille de reçu.

## Écran d'envoi (aperçu des frais)

1. Champ destinataire (numéro / contact) — icône `person`.
2. **AmountField** : saisie centrée grande taille ; XOF/XAF sans décimale.
3. Encart frais (visible si montant > 0) :
   - `Frais (0,8 %)` = `ceil(montant × 80 / 10000)`
   - `Total débité` = `montant + frais`, en gras.
4. CTA `Continuer` → **feuille de confirmation** : récap + `PinInput` (friction
   volontaire — le backend n'exige pas le PIN, la session suffit).
5. Succès → **reçu** + `Nouveau transfert`.

## Reçu

Voir `receipt/receipt.html` (A6 paysage) et `receipt-template.svg`. Structure :
bandeau marque + statut, montant, `operation · date`, liste clé/valeur
(référence, de, vers, frais, total), pied avec **QR de vérification** +
`flash.app/v/<référence>`. Statut `COMPLÉTÉ` (vert) / `CONTRE-PASSÉ` (rouge).
Partage : image (mobile `share_plus`) ou impression PDF.

## Carte virtuelle

| Élément | Spéc |
|---|---|
| Ratio | 1.586 (ISO/IEC 7810 ID-1) |
| Fond actif | dégradé `brand.500 → brand.800` |
| Fond gelé | dégradé `neutral.500 → neutral.700` |
| Haut | éclair blanc + réseau (`VISA` / `MASTERCARD`), lettres espacées |
| PAN | masqué `•••• •••• •••• 1234` ; **révélé 30 s** après appel `/sensitive`, compte à rebours affiché |
| CVV | `CVV •••` → `CVV 123` pendant la fenêtre |
| Actions | `Révéler` (désactivé si gelée), `Geler` / `Dégeler` |
| Copie PAN | appui long pendant la fenêtre de révélation |
