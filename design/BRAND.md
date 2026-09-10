# Flash — guide de marque (DSN-010)

## Idée

**Flash** = l'argent qui court vite. Instantané, sans friction, sans frais cachés.
Le symbole est un **éclair** dont la fente centrale et les traits de vitesse
évoquent le mouvement.

## Logo

| Fichier | Usage |
|---|---|
| `logo/flash-logo.svg` | lockup horizontal (symbole + mot « Flash »), usage principal |
| `logo/flash-logo-white.svg` | idem sur fond foncé / photo sombre |
| `logo/flash-symbol.svg` | symbole seul (app bars, favicons de grande taille, tampons) |
| `logo/flash-symbol-white.svg` / `-black.svg` | symbole monochrome |
| `logo/favicon.svg` | symbole blanc dans une pastille bordeaux, coins `radius.lg` |

**Zone de protection** : au moins la hauteur de la barre de l'éclair (≈ ¼ de la
hauteur du symbole) sur chaque côté. Ne rien placer dans cette marge.

**Taille minimale** : symbole 16 px ; lockup 96 px de large.

### À ne pas faire

- ne pas changer les couleurs du logo hors palette (bordeaux, blanc, noir) ;
- ne pas déformer, incliner, ajouter d'ombre portée ou de contour ;
- ne pas recomposer le lockup (espacement symbole ↔ mot figé) ;
- ne pas poser le logo bordeaux sur un fond bordeaux ou peu contrasté — utiliser
  la version blanche.

## Couleurs

Source unique : [`tokens.json`](tokens.json). Générées en CSS
(`web/scripts/build-tokens.mjs` → `web/src/shared/theme/tokens.css`) et reflétées
à la main dans `mobile/lib/core/theme/tokens.dart`.

| Rôle | Jeton | Hex |
|---|---|---|
| Marque | `color.brand.500` | `#8c1d33` |
| Marque foncée (dégradés, pressé) | `color.brand.700` | `#621525` |
| Secondaire chaud (marketing) | `color.amber.500` | `#e0982a` |
| Fonctionnel positif | `color.accent.500` | `#12a594` |
| Fond clair / sombre | `color.neutral.0` / `neutral.900` | `#ffffff` / `#161619` |
| Succès / Alerte / Danger / Info | `color.success/warning/danger/info` | cf. jetons |

Contraste : le texte sur `brand.500` utilise `neutral.0` (ratio ≥ 4.5). En thème
sombre, la couleur primaire passe à `brand.300` pour rester lisible sur fond
`neutral.900`.

> Note d'implémentation : la couleur d'accompagnement **fonctionnelle** retenue
> pendant le développement est le vert d'eau `accent` (meilleur contraste pour les
> montants entrants et les états de succès). L'ambre `amber` reste la teinte
> chaude de marque pour les usages marketing / illustratifs.

## Typographie

**Inter** (SIL OFL), auto-hébergée — aucun CDN.

- Web : `@fontsource`-style local ou fallback ; stack `Inter, 'Segoe UI',
  system-ui, -apple-system, sans-serif`.
- Mobile : `assets/fonts/Inter.ttf` (variable) déclarée dans `pubspec.yaml`,
  `fontFamily: 'Inter'`.
- Poids utilisés : 400 (corps), 500, 600, 700, 800 (titres, montants).
- Montants : toujours en **chiffres tabulaires** (`font-feature-settings:
  "tnum"`).

## Iconographie

`icons/*.svg` — grille 24, trait 1.75, bouts et jonctions arrondis,
`stroke="currentColor"`. Un concept = une icône : envoyer, payer, retirer,
déposer, coffre, épargne, carte, agent, demander, opérateur, scanner, éclair.

## Ton

Direct, rassurant, sans jargon. On dit « envoyer de l'argent », pas « initier une
transaction ». Les erreurs sont expliquées et proposent une action. Jamais de
promesse que le produit ne tient pas (frais = **0,8 %**, affichés avant chaque
envoi).

## Icône d'application & splash

`app-icon/icon.svg` (master 1024, dégradé bordeaux, éclair blanc, coins 230),
`icon-maskable.svg` (Android adaptatif, symbole dans le cercle sûr 66 %),
`icon-monochrome.svg` (Android 13+ thématique), `splash.svg` (fond `brand.500`,
éclair centré). Les PNG dérivés sont générés par `flutter_launcher_icons` /
`vite-plugin-pwa`.
