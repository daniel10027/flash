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

## Parcours client (WEB-013 → WEB-032) — **livré**

> Couche données `src/shared/api/hooks.ts` (React Query, clés `qk`, mutations avec
> invalidations). Briques `features/common/kit.tsx` : `PageHeader`, `AmountField`
> (aperçu **frais 0,8 %** + total), `ConfirmSheet` (friction code secret avant débit),
> `Receipt` générique. `<Qr>` via `qrcode`. Écrans : inscription (`RegisterPage`,
> numéro→PIN→confirmation→OTP→succès), connexion enrichie (renvoi d'OTP, lien inscription),
> tableau de bord (solde, raccourcis, 5 dernières opérations, bandeau KYC tier 0),
> envoi (destinataire + montant + frais + confirmation + reçu), demandes de paiement
> (créer / lister reçues·émises / payer / refuser / annuler), payer un marchand
> (`BarcodeDetector` + fallback code, QR statique/dynamique), recevoir (mon QR + montant),
> retrait cash (code + compte à rebours + annulation), dépôt cash (QR d'identifiant),
> compte opérateur (payout / topup + statut), historique (scroll infini via
> `IntersectionObserver`, recherche, filtre, groupement par jour) + détail·reçu en feuille,
> coffre (poches CRUD + alimenter/retirer + verrou), épargne (plans + progression +
> intérêts + versement/retrait/clôture), carte (émettre, révéler PAN/CVV 30 s, geler,
> plafonds, canaux), profil à onglets : KYC (upload base64 + `target_tier`), mes numéros
> (max 5, ajout+OTP, principal, retrait), sécurité (changer le code secret, liste des
> appareils connectés + déconnexion à distance, logout serveur+local), paramètres
> (thème, masquer soldes, à propos), notifications (liste + SSE `EventSource` + marquage lu,
> pastille non-lus dans l'en-tête). Connexion : « code secret oublié » →
> réinitialisation par OTP (numéro → code → nouveau code). Router : toutes les routes
> câblées, secondaires dans le menu `⋮`. Vérifs : `tsc` + ESLint (`jsx-a11y`) + Prettier
> OK, 10 tests Vitest (dont rendu Dashboard/Send avec `fetch` mocké), build OK, e2e
> Playwright.

- [x] **WEB-013** · Inscription : numéro + pays, création PIN, OTP, écran succès.
- [x] **WEB-014** · Connexion : numéro + PIN, gestion appareil, OTP si nouvel appareil,
  mot de passe oublié → réinitialisation PIN par OTP.
- [x] **WEB-015** · Tableau de bord : solde(s), raccourcis (Envoyer, Payer, Retirer,
  Ajouter), 5 dernières opérations, bandeau KYC si tier 0.
- [x] **WEB-016** · Envoyer de l'argent : saisie destinataire (numéro / contacts /
  favoris), montant, **aperçu des frais 0,8 %** et total, confirmation par PIN, reçu.
- [x] **WEB-017** · Demander de l'argent : créer une demande, la partager (lien/QR),
  liste des demandes reçues/émises, accepter/refuser.
- [x] **WEB-018** · Payer un marchand : scanner un QR (caméra `getUserMedia` + fallback
  saisie code), QR dynamique (montant pré‑rempli), confirmation, reçu.
- [x] **WEB-019** · Présenter mon QR (pour recevoir) : QR personnel + montant optionnel.
- [x] **WEB-020** · Retrait cash : générer un code de retrait (montant, frais affichés),
  compte à rebours d'expiration, annulation, statut « encaissé ».
- [x] **WEB-021** · Dépôt cash : écran explicatif + mon identifiant/QR à présenter à
  l'agent, notification à réception.
- [x] **WEB-022** · Retrait/dépôt vers compte opérateur (Orange/MTN/Moov) : choix
  opérateur, numéro, montant, frais, statut asynchrone.
- [x] **WEB-023** · Historique : liste paginée (scroll infini), filtres (type, période,
  statut, contrepartie), recherche, groupement par jour.
- [x] **WEB-024** · Détail opération + reçu : montant, frais, référence, parties, statut,
  actions (annuler si éligible, signaler, partager PDF/PNG).
- [x] **WEB-025** · Coffre : liste des poches, créer/renommer/supprimer, déplacer
  vers/depuis, poche « verrouillée jusqu'à », part du solde réservée visible.
- [x] **WEB-026** · Épargne : ouvrir un plan (objectif, fréquence, source), suivi de
  progression, intérêts cumulés, versement manuel, clôture.
- [x] **WEB-027** · Carte : demander une carte virtuelle, afficher (numéro masqué,
  révéler PAN/CVV via flux sécurisé), geler/dégeler, plafonds, canaux, opérations carte.
- [x] **WEB-028** · Mes numéros : liste (max 5), ajouter (OTP), définir principal,
  supprimer, indication du numéro utilisé pour se connecter.
- [x] **WEB-029** · Profil & KYC : infos, upload pièce + selfie, statut de vérification,
  paliers et limites associées, préférences de notification.
- [x] **WEB-030** · Notifications : centre in‑app (SSE temps réel), marquage lu, réglages
  push (activer via navigateur), historique.
- [x] **WEB-031** · Sécurité : appareils connectés, déconnexion à distance, changer le
  PIN, activité récente.
- [x] **WEB-032** · Paramètres : langue, pays d'affichage, thème, confidentialité
  (masquer soldes par défaut), à propos / mentions légales.

## Espace agent (WEB-033 → WEB-039) — **livré**

> `features/agent/hooks.ts` (React Query sur `/v1/agent/*`, `useIsAgent` conditionne
> l'entrée « Espace agent » du menu). Écrans `pages/agent/AgentPages.tsx` : tableau de bord
> (float disponible, commissions gagnées/versées/dues + `payout`, sous-agents s'il y en a),
> dépôt client (recherche `/v1/agent/customers` + `POST /deposits` + reçu), retrait client
> (`POST /withdrawals/confirm` par code + contrôle montant + reçu), journal des opérations
> (`GET /operations`, filtres, **export CSV** côté client), gestion du float (`topup` /
> `withdraw`). WEB-039 multi-guichet : liste des sous-agents affichée quand `GET /v1/agent`
> la renvoie (la hiérarchie s'administre côté back-office).

- [x] **WEB-033** · Connexion agent (rôle), tableau de bord : solde float, commissions du
  jour, nombre d'opérations.
- [x] **WEB-034** · Dépôt client : rechercher le client (numéro/QR), montant, confirmer,
  reçu agent + client.
- [x] **WEB-035** · Retrait client : saisir le code de retrait, vérifier montant, remettre
  le cash, confirmer, reçu.
- [x] **WEB-036** · Journal des opérations agent : filtres, export CSV.
- [x] **WEB-037** · Float : demander un réapprovisionnement, historique des mouvements de
  float.
- [x] **WEB-038** · Commissions : détail par opération, cumul, relevés périodiques.
- [x] **WEB-039** · Multi‑guichet (sous‑agents) : liste, plafonds, activité.

## Back‑office (WEB-040 → WEB-046) — **livré**

> Arbre `/admin/*` **séparé** de l'app cliente. `features/admin/client.ts` : store de clé
> (`X-Admin-Key`, localStorage) + `adminFetch` (erreurs `ApiError`, support CSV brut).
> `AdminShell.tsx` : `AdminLoginPage` (saisie de la clé — le rôle réel est décidé par le
> serveur, 403 sinon), `RequireAdmin`, `AdminLayout` (nav Comptes / KYC / AML / Référentiel
> / Finance / Audit + Quitter). `features/admin/hooks.ts` + `pages/admin/AdminPages.tsx` :
> **Comptes** (recherche `/v1/admin/accounts`, fiche en feuille : détail, gel/dégel avec
> motif, contre-passation forcée `force-reversal`, notes internes) ; **KYC** (file des
> dossiers par statut `/v1/admin/kyc/submissions`, feuille détail avec **aperçu des
> pièces** — octets servis `no-store` via `adminFetchBlob` + `URL.createObjectURL` —
> approuver / rejeter avec motif) ; **AML** (file d'alertes par statut, statuer
> `clear`/`escalate` avec note, **export STR CSV**) ; **Référentiel** (tables grille
> tarifaire / plafonds + `reload` du cache ; édition ligne à ligne via
> `useReferenceActions`) ; **Finance** (balance générale à une date avec badge d'équilibre,
> journal des écritures par période, lien export mensuel CSV) ; **Audit** (registre filtré
> acteur/action + **contrôle d'intégrité de la chaîne**). Table générique `DataTable`
> (colonnes auto). Vérifs : `tsc` + ESLint + Prettier OK, e2e (redirection `/admin` →
> `/admin/login`).

- [x] **WEB-040** · Connexion staff + RBAC (support / compliance / finance / admin),
  layout dédié.
- [x] **WEB-041** · Recherche & fiche client : profil, KYC, wallets, appareils, historique,
  actions (geler/dégeler, forcer reversal) avec motif obligatoire.
- [x] **WEB-042** · File KYC : à revoir, approuver/rejeter avec motif, voir les documents.
- [x] **WEB-043** · File AML : alertes, blocage préventif, clôture d'alerte, export STR/CTR.
- [x] **WEB-044** · Référentiel : pays, grille tarifaire (frais 0,8 % éditables par pays),
  limites par KYC, opérateurs — avec journal des modifications.
- [x] **WEB-045** · Finance : balance du ledger à une date, journal, exports mensuels,
  états de règlement marchands/agents.
- [x] **WEB-046** · Audit : registre consultable de toutes les actions sensibles.

## Transverse

- [ ] **WEB-T1** · Tests unitaires composants + hooks (Vitest), ≥ 80 % sur `features/`.
- [ ] **WEB-T2** · E2E Playwright : inscription → dépôt agent → transfert → retrait →
  historique ; coffre ; carte ; ajout d'un 2e numéro.
- [ ] **WEB-T3** · Lighthouse : perf/PWA/a11y ≥ 90 en CI.
