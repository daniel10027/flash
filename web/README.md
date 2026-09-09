# Flash — application web

React 18 + Vite + TypeScript. Client API **généré** depuis `../docs/api/openapi.json`.
État léger : Zustand. Données serveur : TanStack Query. Formulaires : React Hook Form +
Zod. i18n FR (`react-i18next`). PWA (installable, lecture hors-ligne dégradée).
Thème bordeaux issu de `../design/tokens.json`.

## Démarrer

```sh
cd web
npm install
npm run tokens      # design/tokens.json -> src/shared/theme/tokens.css
npm run gen:api     # docs/api/openapi.json -> src/shared/api/schema.d.ts
npm run dev         # http://localhost:5173  (proxy /v1 -> http://localhost:8000)
```

Avec Docker (API + web) : `docker compose -f infra/docker-compose.yml --profile web up`.

## Scripts

| Script              | Rôle                                                |
| ------------------- | --------------------------------------------------- |
| `npm run dev`       | serveur de dev (HMR), proxy `/v1` vers l'API        |
| `npm run build`     | typecheck + bundle de production (`dist/`)          |
| `npm run preview`   | sert `dist/` en local                               |
| `npm run lint`      | ESLint + Prettier (vérif)                           |
| `npm run format`    | Prettier (écriture)                                 |
| `npm run typecheck` | `tsc` sans émission                                 |
| `npm run test`      | Vitest (unitaires + composants)                     |
| `npm run e2e`       | Playwright (fumée ; démarre `preview`)              |
| `npm run gen:api`   | régénère le client typé depuis la spec OpenAPI      |
| `npm run tokens`    | régénère les variables CSS depuis les design tokens |

## Structure

```
src/
  app/        providers, routeur, thème, ErrorBoundary
  features/   modules métier (layout, auth, …)
  pages/      écrans routés
  shared/     api (client + types), auth (session), i18n, ui (composants), config, theme
```

## Config runtime (WEB-011)

En production, `docker-entrypoint.sh` écrit `/srv/config.js` à partir des variables
d'environnement de l'image :

- `FLASH_API_BASE_URL` — base des appels API (ex. `https://api.flash.example`)
- `FLASH_ENV` — `production` \| `staging`
- `FLASH_SENTRY_DSN` — optionnel

`index.html` charge `/config.js` avant le bundle ; en dev, un bloc de repli fournit des
valeurs vides (le proxy Vite prend le relais).

## État du lot

Socle **WEB-001 → WEB-012** livré : init, design tokens + thème clair/sombre, composants
de base + galerie `/ui`, client API typé + wrapper (Idempotency-Key, X-Request-ID,
refresh auto, `ApiError`), couche session + garde de routes, layout responsive
(nav latérale / barre du bas, solde masquable, menu profil), i18n FR + formats
monétaires par devise, gestion d'erreurs globale (ErrorBoundary, 404/500, toasts),
PWA (manifest + SW), accessibilité (skip-link, focus visible, aria), config runtime,
Dockerfile + intégration compose.

Les parcours (`WEB-013+`) branchent ces fondations sur l'API.
