# Design & marque Flash

Source de vérité visuelle, consommée par le web et le mobile.

```
design/
  tokens.json          jetons (couleurs, typo, espacements, rayons, ombres, motion)
  BRAND.md             guide de marque (logo, couleurs, ton, do/don't)
  COMPONENTS.md        specs des écrans structurants
  logo/                lockup + symbole + déclinaisons + favicon (SVG)
  app-icon/            master 1024, maskable, monochrome, splash (SVG)
  icons/               jeu d'icônes fonctionnelles 24px (SVG, currentColor)
  receipt/             modèle de reçu (HTML A6 + SVG), champs {{…}}
```

## Chaîne de génération

| Cible | Commande | Sortie |
|---|---|---|
| Web (CSS vars) | `cd web && npm run tokens` (`scripts/build-tokens.mjs`) | `web/src/shared/theme/tokens.css` |
| Mobile (Dart) | reflété manuellement | `mobile/lib/core/theme/tokens.dart` |
| Icônes d'app | `flutter_launcher_icons` (mobile) / `vite-plugin-pwa` (web) | PNG dérivés de `app-icon/` |

`tokens.json` est **la** source ; toute évolution de couleur/rayon/typo part de
là, puis régénère le web et met à jour `tokens.dart`.

## Palette (DSN-001, figée)

Bordeaux `#8c1d33` (famille `brand.50…900`), secondaire chaud `amber.500`
`#e0982a`, fonctionnel positif `accent.500` `#12a594`, neutres `neutral.0…900`,
sémantiques succès/alerte/danger/info — versions claire et sombre, contrastes AA
vérifiés (texte sur `brand.500` en `neutral.0`, primaire → `brand.300` en sombre).
