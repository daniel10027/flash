# Tâches Design & marque (`DSN`)

Identité : nom **Flash**. Idée du logo : « l'argent qui court vite » — une pièce / un
billet stylisé en mouvement, traits de vitesse, ou un éclair intégrant un symbole
monétaire. Couleur principale : **rouge bordeaux**. Couleur d'accompagnement à définir
(piste : un doré / ambre chaud pour contraster le bordeaux, + neutres).

- [x] **DSN-001** · palette figée dans `design/tokens.json` — bordeaux `brand.50…900` (`#8c1d33`), secondaire chaud `amber.500` (`#e0982a`), fonctionnel positif `accent.500` (`#12a594`), neutres `neutral.0…900`, sémantiques succès/alerte/danger/info ; clair + sombre, contrastes AA (texte sur `brand.500` en `neutral.0`, primaire → `brand.300` en sombre).
- [x] **DSN-002** · `design/tokens.json` complet : couleurs, `font` (famille Inter + échelle + poids + interlignes), `space`, `radius`, `shadow`, `duration` + `easing`, `z`. Généré en CSS vars par `web/scripts/build-tokens.mjs` → `tokens.css` (77 vars) ; reflété dans `mobile/lib/core/theme/tokens.dart`.
- [x] **DSN-003** · `design/logo/flash-logo.svg` (lockup horizontal éclair + mot « Flash », traits de vitesse) + `flash-symbol.svg` (symbole seul).
- [x] **DSN-004** · déclinaisons — `flash-symbol-white.svg` / `-black.svg` (monochromes), `flash-logo-white.svg` (fond foncé), `favicon.svg` (éclair blanc en pastille bordeaux). Taille min. documentée (symbole 16 px).
- [x] **DSN-005** · `design/app-icon/` — `icon.svg` (master 1024, dégradé bordeaux + éclair blanc, coins 230), `icon-maskable.svg` (Android adaptatif, cercle sûr 66 %), `icon-monochrome.svg` (Android 13+), `splash.svg` (fond `brand.500`). PNG dérivés via `flutter_launcher_icons` / `vite-plugin-pwa`.
- [x] **DSN-006** · `design/icons/` — 12 icônes 24 px, trait 1.75, bouts arrondis, `currentColor` : envoyer, payer, retirer, déposer, coffre, épargne, carte, agent, demander, opérateur, scanner, éclair.
- [x] **DSN-007** · **Inter** (SIL OFL), auto-hébergée — mobile `assets/fonts/Inter.ttf` (variable) + `fontFamily: Inter` ; web stack `Inter, 'Segoe UI', system-ui…`. Poids 400/500/600/700/800, chiffres tabulaires pour les montants. `google_fonts` (fetch runtime) retiré.
- [x] **DSN-008** · `design/COMPONENTS.md` — specs carte de solde (dégradé, count-up 700 ms), ligne d'historique, écran d'envoi (encart frais 0,8 %), reçu, carte virtuelle (ratio ID-1, révélation PAN/CVV 30 s).
- [x] **DSN-009** · `design/receipt/` — `receipt.html` (A6 paysage, imprimable PDF, zéro ressource externe) + `receipt-template.svg`, champs `{{…}}`, bandeau marque + statut, QR de vérification `flash.app/v/<référence>`. Utilisé web + mobile (partage image / PDF).
- [x] **DSN-010** · `design/BRAND.md` — idée, usage du logo + zone de protection + do/don't, couleurs (renvoi tokens), typographie, iconographie, ton, icône d'app & splash. `design/README.md` : index + chaîne de génération.