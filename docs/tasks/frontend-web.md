# Tâches Web / React (`WEB`)

Stack : React 18 + Vite + TypeScript, TanStack Query, React Router, Zustand (état léger),
React Hook Form + Zod, client API généré depuis `docs/api/openapi.json`, i18n FR (EN en
option), thème bordeaux (`design/tokens.json`), PWA. Tests : Vitest + Testing Library,
Playwright (E2E).

## Socle (WEB-001 → WEB-012) — **livré**

> `web/` : Vite + React 18 + TS strict (`noUncheckedIndexedAccess`), alias `@app`/`@features`
> /`@shared`/`@pages`, ESLint (+ `jsx-a11y`) + Prettier. `design/tokens.json` →
> `scripts/build-tokens.mjs` → `src/shared/theme/tokens.css` (rôles sémantiques clair/sombre,
> `data-theme` system/light/dark). Composants `shared/ui` + galerie `/ui`. Client API :
> `npm run gen:api` (openapi-typescript ← `docs/api/openapi.json`) + `apiFetch` (base URL
> runtime, `X-Request-ID`, `Idempotency-Key` auto, refresh 401 unique, `ApiError`/`NetworkError`).
> Session Zustand (access en mémoire, refresh localStorage) + `RequireAuth`/`RedirectIfAuthed`
> + pont d'expiration → `/login`. Layout responsive (nav latérale desktop / barre du bas
> mobile, en-tête solde masquable, menu profil thème+déconnexion). i18n `react-i18next` FR +
> `formatMoney` (XOF/XAF sans décimale) / `formatDate` / `formatRelative`. `ErrorBoundary`,
> pages 404/500, `Toaster` (mappe `code` → message). PWA (`vite-plugin-pwa`, manifest,
> `NetworkFirst` sur `wallets`/`statement`/`notifications`, invite de MAJ). A11y (skip-link,
> focus visible, aria, tabs au clavier). Config runtime `window.__FLASH_CONFIG__` via
> `/config.js` généré par `docker-entrypoint.sh`. `web/Dockerfile` (stages dev / build /
> runtime Caddy) + service `web` (profil `web`) dans `infra/docker-compose.yml`.
> Vérifs : `tsc` + ESLint + Prettier OK, 8 tests Vitest, build de prod OK, e2e Playwright
> (fumée : redirection login, 404, validation du formulaire).

- [x] **WEB-001** · Init Vite + TS + ESLint/Prettier + structure (`app/`, `features/`,
  `shared/`, `pages/`). Alias de chemins. Scripts `dev/build/preview/test/e2e`.
- [x] **WEB-002** · Intégration des design tokens (couleurs bordeaux + secondaire,
  typo, espacements, rayons, ombres) → CSS variables + thème. Mode clair/sombre.
- [x] **WEB-003** · Composants UI de base : Button, Input, PinInput, Money, Amount,
  Sheet/Modal, Toast, Skeleton, EmptyState, Avatar, Badge, Tabs, ListRow. Storybook
  ou galerie `/ui`.
- [x] **WEB-004** · Génération du client API typé (openapi-typescript + wrapper fetch
  avec `Idempotency-Key`, `request_id`, refresh token auto, gestion `DomainError`).
- [x] **WEB-005** · Couche auth : contexte session, stockage token (mémoire + refresh
  cookie/localStorage sécurisé), guard de routes, redirection.
- [x] **WEB-006** · Layout applicatif : barre latérale/bottom‑nav responsive, en‑tête
  avec solde masquable, sélecteur de wallet/pays, menu profil.
- [x] **WEB-007** · i18n (react‑i18next), FR par défaut, fichiers de traduction, format
  monétaire/date par pays.
- [x] **WEB-008** · Gestion d'erreurs globale (ErrorBoundary, page 500/404, toasts
  d'erreur API mappés depuis `code`).
- [x] **WEB-009** · PWA : manifest (icônes Flash), service worker (cache shell,
  offline lecture historique/solde en cache), invite d'installation.
- [x] **WEB-010** · Accessibilité : focus visible, navigation clavier, aria sur les
  composants, contraste AA vérifié sur le thème bordeaux.
- [x] **WEB-011** · Config runtime (`window.__FLASH_CONFIG__` injecté par l'image),
  `API_BASE_URL`, `SENTRY_DSN` optionnel, `ENV`.
- [x] **WEB-012** · Dockerfile web (build Vite → Nginx/Caddy statique), intégration
  `infra/docker-compose.yml`, hot reload en dev.

## Parcours client (WEB-013 → WEB-032)

- [ ] **WEB-013** · Inscription : numéro + pays, création PIN, OTP, écran succès.
- [ ] **WEB-014** · Connexion : numéro + PIN, gestion appareil, OTP si nouvel appareil,
  mot de passe oublié → réinitialisation PIN par OTP.
- [ ] **WEB-015** · Tableau de bord : solde(s), raccourcis (Envoyer, Payer, Retirer,
  Ajouter), 5 dernières opérations, bandeau KYC si tier 0.
- [ ] **WEB-016** · Envoyer de l'argent : saisie destinataire (numéro / contacts /
  favoris), montant, **aperçu des frais 0,8 %** et total, confirmation par PIN, reçu.
- [ ] **WEB-017** · Demander de l'argent : créer une demande, la partager (lien/QR),
  liste des demandes reçues/émises, accepter/refuser.
- [ ] **WEB-018** · Payer un marchand : scanner un QR (caméra `getUserMedia` + fallback
  saisie code), QR dynamique (montant pré‑rempli), confirmation, reçu.
- [ ] **WEB-019** · Présenter mon QR (pour recevoir) : QR personnel + montant optionnel.
- [ ] **WEB-020** · Retrait cash : générer un code de retrait (montant, frais affichés),
  compte à rebours d'expiration, annulation, statut « encaissé ».
- [ ] **WEB-021** · Dépôt cash : écran explicatif + mon identifiant/QR à présenter à
  l'agent, notification à réception.
- [ ] **WEB-022** · Retrait/dépôt vers compte opérateur (Orange/MTN/Moov) : choix
  opérateur, numéro, montant, frais, statut asynchrone.
- [ ] **WEB-023** · Historique : liste paginée (scroll infini), filtres (type, période,
  statut, contrepartie), recherche, groupement par jour.
- [ ] **WEB-024** · Détail opération + reçu : montant, frais, référence, parties, statut,
  actions (annuler si éligible, signaler, partager PDF/PNG).
- [ ] **WEB-025** · Coffre : liste des poches, créer/renommer/supprimer, déplacer
  vers/depuis, poche « verrouillée jusqu'à », part du solde réservée visible.
- [ ] **WEB-026** · Épargne : ouvrir un plan (objectif, fréquence, source), suivi de
  progression, intérêts cumulés, versement manuel, clôture.
- [ ] **WEB-027** · Carte : demander une carte virtuelle, afficher (numéro masqué,
  révéler PAN/CVV via flux sécurisé), geler/dégeler, plafonds, canaux, opérations carte.
- [ ] **WEB-028** · Mes numéros : liste (max 5), ajouter (OTP), définir principal,
  supprimer, indication du numéro utilisé pour se connecter.
- [ ] **WEB-029** · Profil & KYC : infos, upload pièce + selfie, statut de vérification,
  paliers et limites associées, préférences de notification.
- [ ] **WEB-030** · Notifications : centre in‑app (SSE temps réel), marquage lu, réglages
  push (activer via navigateur), historique.
- [ ] **WEB-031** · Sécurité : appareils connectés, déconnexion à distance, changer le
  PIN, activité récente.
- [ ] **WEB-032** · Paramètres : langue, pays d'affichage, thème, confidentialité
  (masquer soldes par défaut), à propos / mentions légales.

## Espace agent (WEB-033 → WEB-039)

- [ ] **WEB-033** · Connexion agent (rôle), tableau de bord : solde float, commissions du
  jour, nombre d'opérations.
- [ ] **WEB-034** · Dépôt client : rechercher le client (numéro/QR), montant, confirmer,
  reçu agent + client.
- [ ] **WEB-035** · Retrait client : saisir le code de retrait, vérifier montant, remettre
  le cash, confirmer, reçu.
- [ ] **WEB-036** · Journal des opérations agent : filtres, export CSV.
- [ ] **WEB-037** · Float : demander un réapprovisionnement, historique des mouvements de
  float.
- [ ] **WEB-038** · Commissions : détail par opération, cumul, relevés périodiques.
- [ ] **WEB-039** · Multi‑guichet (sous‑agents) : liste, plafonds, activité.

## Back‑office (WEB-040 → WEB-046)

- [ ] **WEB-040** · Connexion staff + RBAC (support / compliance / finance / admin),
  layout dédié.
- [ ] **WEB-041** · Recherche & fiche client : profil, KYC, wallets, appareils, historique,
  actions (geler/dégeler, forcer reversal) avec motif obligatoire.
- [ ] **WEB-042** · File KYC : à revoir, approuver/rejeter avec motif, voir les documents.
- [ ] **WEB-043** · File AML : alertes, blocage préventif, clôture d'alerte, export STR/CTR.
- [ ] **WEB-044** · Référentiel : pays, grille tarifaire (frais 0,8 % éditables par pays),
  limites par KYC, opérateurs — avec journal des modifications.
- [ ] **WEB-045** · Finance : balance du ledger à une date, journal, exports mensuels,
  états de règlement marchands/agents.
- [ ] **WEB-046** · Audit : registre consultable de toutes les actions sensibles.

## Transverse

- [ ] **WEB-T1** · Tests unitaires composants + hooks (Vitest), ≥ 80 % sur `features/`.
- [ ] **WEB-T2** · E2E Playwright : inscription → dépôt agent → transfert → retrait →
  historique ; coffre ; carte ; ajout d'un 2e numéro.
- [ ] **WEB-T3** · Lighthouse : perf/PWA/a11y ≥ 90 en CI.
