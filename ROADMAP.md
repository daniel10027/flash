# Flash — Map de développement

> **Dernière mise à jour : 2026-09-09**
> **Phases 1-3 complètes · Phase 4 en cours : BE-061 (référentiel pays) + BE-063 (grille multi-pays)**
> (auth, numéros, wallets, transfert + **annulation**, **demandes de paiement**,
> **paiement marchand QR** + **remboursement**, **dépôt & retrait cash agent**,
> relevé + **reçu détaillé**, **KYC**, **notifications** + **flux SSE**, **jobs
> d'expiration / réconciliation**, **seed de démo**).
> Domaine complet (identity + PIN Argon2, wallet, ledger partie double, pricing 0,8 %,
> limits, référentiel pays, **agent + ordre cash**). Application : `RegisterUser`, auth
> (`Login`/`VerifyOtp`/`ResendOtp` + `TokenService`), gestion des numéros,
> `GetWallet`/`ListWallets`, **`SendP2PTransfer`** (flux §3 archi, frais 0,8 %, ledger
> équilibré, idempotent, `TransferCompleted`), **cash** : `EnrollAgent`,
> `CreateCashDeposit`, `InitiateCashWithdrawal` (code à usage unique SHA-256 poivré,
> TTL 15 min), `ConfirmCashWithdrawal`, `CancelCashWithdrawal` — commission agent payée
> par Flash, ledger toujours équilibré. Port `WorkUnitOfWork` (UoW typée, +`agents`
> +`cash_orders`) + `add_event`. Infra : grilles tarifaire/plafonds statiques (UEMOA),
> migration `agents` + `cash_orders`, CLI `flash agent enroll`.
> **KYC (BE-029)** : agrégat `KycCase` (+ `KycDocument`), port `DocumentStore`
> (`LocalFilesystemDocumentStore`), `SubmitKyc` (base64, idempotent) / `WithdrawKyc` /
> `GetKycStatus` / `ReviewKyc` (back-office par clé `X-Admin-Key`, RBAC = BE-071).
> L'approbation relève `KycTier` → les plafonds `(pays, palier)` s'appliquent aussitôt.
> **Demandes de paiement (BE-032)** : agrégat `PaymentRequest` (PENDING → ACCEPTED /
> DECLINED / CANCELLED / EXPIRED, TTL 7 j). `AcceptPaymentRequest` compose
> `SendP2PTransfer` avec une clé d'idempotence dérivée (`paymentreq-<id>`) : accepter
> deux fois ne débite qu'une fois ; fonds insuffisants → la demande reste PENDING.
> **Paiement marchand par QR (BE-033)** : agrégats `Merchant` (CLI `flash merchant enroll`,
> `fee_bps`), `MerchantCharge` (QR dynamique montant + réf + expiration), `MerchantPayment`.
> `PayMerchant` — gratuit pour le client, le marchand paie `fee_bps` (net → `MERCHANT_PAYABLE`,
> frais → `FLASH_FEE_INCOME`) via `LedgerTransaction.merchant_payment`, idempotent. QR
> statique `flash://pay?m=<id>` (montant saisi).
> **Annulation & remboursement (BE-037)** : `CancelTransfer` (émetteur seul, fenêtre
> `reversal_window` 1 h, refus si le destinataire a dépensé → `RefundNotPossible`),
> `RefundMerchantPayment` (marchand, `MerchantPayment` → REFUNDED). Contre-passation
> `LedgerTransaction.reversal` (jamais de suppression), événements `TransferReversed` /
> `MerchantPaymentRefunded`.
> **Reçu détaillé (BE-039)** : `GetReceipt` — reçu d'une opération lu du ledger (par id
> ou référence métier), du point de vue de l'appelant (parties prenantes seulement,
> sinon 404), avec statut `COMPLETED` / `REVERSED`. Projection factorisée avec
> `ListStatement`.
> **Notifications (BE-040/041/042)** : port `Notifier` + canaux (in-app table
> `notifications`, bus temps réel, SMTP, FCM stub, log). `NotificationDispatcher` mappe
> les événements de l'outbox (transfert / cash / marchand / KYC) en notifications,
> branché post-commit via `NotifyingEventPublisher` (best-effort). Blueprint
> `/v1/notifications` (liste + curseur + `unread`, `/<id>/read`, `/read-all`) et
> **SSE `/v1/notifications/stream`** (`RedisNotificationBus` pub/sub, rattrapage
> `Last-Event-ID` depuis le journal, keep-alive).
> **67 chemins** : `auth` (6), `phones` (5), `wallets` (2), `transfers` (2),
> `payment-requests` (4), `merchant` (4), `merchant-payments` (1), `statement` (1),
> `receipts` (1), `notifications` (4), `withdrawals` (2), `agent` (2), `kyc` (4),
> `vault` (6), `savings` (5), `cards` (8), `cards/authorizations` (4), `reference` (2),
> `admin/kyc` (1), `admin` ops (5) + `/health*`, `/openapi.json`, `/docs`, `/redoc`.
> **Tout vérifié end-to-end via docker compose** : cash, KYC, demandes de paiement,
> paiement marchand, annulation / remboursement (soldes restaurés, rejeu → 409),
> reçus (out/in, 404 pour un tiers, REVERSED) ; un transfert génère « Argent reçu » /
> « Transfert envoyé », un dépôt agent « Dépôt reçu » ; **SSE** : `retry` + trame
> `event: notification` (rattrapage `Last-Event-ID`) + `: keep-alive`, en-têtes
> `text/event-stream` corrects.
> **Concurrence (BE-043)** : `SELECT … FOR UPDATE` sur le portefeuille (déjà en place)
> prouvé par un test de course d'intégration — deux transferts simultanés sur un solde
> insuffisant : exactement un passe, l'autre `InsufficientFunds`, solde jamais négatif.
> **Jobs (BE-044/045)** : `ExpireStaleOperations` (retraits / demandes / QR périmés →
> expirés, réserve libérée, idempotent) + `ReconcileWalletBalances` (projection
> `available + reserved` vs solde recalculé du ledger, écarts signalés, lecture seule).
> `flash run-jobs` (cron, exit 1 si écart) + `POST /v1/admin/{jobs/expire,reconcile}`.
> **Seed (BE-046)** : `flash seed` — agent + marchand + 2 utilisateurs approvisionnés,
> idempotent.
> **Carte virtuelle (BE-055 → BE-060)** : agrégat `Card` (`pan_token` opaque — jamais le
> vrai PAN —, réseau VISA/MASTERCARD, ACTIVE/FROZEN/CLOSED, plafonds jour/mois, canaux
> ECOM/CONTACTLESS/ATM) + `CardAuthorization` (AUTHORIZED→CAPTURED/REVERSED→REFUNDED,
> DECLINED). Port `CardIssuer` + `SandboxCardIssuer` (PAN/CVV re-dérivés du token).
> `IssueCard`/`ListCards`/`GetCard`/`Freeze`/`Unfreeze`/`Close`/`SetCardLimits`,
> `GetCardSensitive` (audité, rate-limité 3/5 min, `no-store`). Webhook signé
> `POST /v1/cards/authorizations` (+ `/capture`, `/reverse`, `/refund`) : l'autorisation
> **réserve** (aucune écriture), la capture consomme via `LedgerTransaction.card_capture`
> (`CARD_SCHEME_SUSPENSE`), le remboursement via `card_refund` ; idempotent par
> `authorization_id` ; refus renvoyé en 200 avec `decision`. Job `ReconcileCardSettlements`
> (`flash run-jobs` + `POST /v1/admin/jobs/cards/reconcile`). Notifications `CARD`. Tables
> `cards` + `card_authorizations` (migration `e3d8b1a06f92`).
>
> **Épargne (BE-050 → BE-054)** : agrégat `SavingsPlan` (objectif montant/date, fréquence
> NONE/WEEKLY/MONTHLY + `contribution`, `annual_rate_bps` ≤ 2000, ACTIVE/CLOSED). Le
> `Wallet` gagne `saved` : `balance = available + reserved + vaulted + saved`, l'`available`
> l'exclut. `OpenSavingsPlan` / `ContributeToSavings` / `WithdrawFromSavings` (idempotents,
> `LedgerTransaction.savings_deposit`/`withdrawal`) / `CloseSavingsPlan` (tout rapatrié).
> Intérêts : `plan.accrue` (prorata jours, accumulateur sous-unité) puis `plan.capitalise`
> (unités entières) → `LedgerTransaction.interest` (`interest_expense`) +
> `wallet.add_savings_interest`. Jobs `RunScheduledSavings` (versements échus ; solde
> insuffisant → `SavingsContributionSkipped` + échéance reportée) et `AccrueSavingsInterest`
> (paginé), branchés sur `flash run-jobs` et `POST /v1/admin/jobs/savings/{contributions,
> interest}`. Blueprint `/v1/savings` (`GET`/`POST /plans`, `POST /plans/<id>/{deposit,
> withdraw,close}`). Statement : `SAVINGS_DEPOSIT`/`WITHDRAWAL`/`INTEREST` projetés depuis
> les métadonnées. Notifications `SAVINGS`. Colonne `wallets.saved_minor` + table
> `savings_plans` (migration `c7f2a0e9d4b1`).
>
> **Coffre (BE-047 → BE-049 + BE-054 partiel)** : agrégat `Vault` = les **poches** d'un
> portefeuille (nom, solde, objectif + `progress_bps`, `locked_until`). Le `Wallet` gagne
> `vaulted` : `balance = available + reserved + vaulted`, l'`available` **exclut** le coffre.
> `OpenVaultPocket` / `RenameVaultPocket` / `CloseVaultPocket` (vide → `PocketNotEmpty`).
> `MoveToVault` / `MoveFromVault` idempotents, instantanés, **sans frais**, via
> `LedgerTransaction.vault_move` (analytiques `client_liability` ↔ `savings_liability`,
> les deux écritures portent le wallet → solde ledger inchangé, cohérent avec `balance`).
> Retrait d'une poche verrouillée → `PocketLocked` (409). Historisé au relevé
> (`VAULT_MOVE`, sens/montant via métadonnées) ; job de réconciliation aligné sur
> `wallet.balance`. Notifications `VAULT` (« Mis de côté » / « Repris du coffre »).
> Blueprint `/v1/vault` : `GET`, `POST /pockets`, `PATCH`/`DELETE /pockets/<id>`,
> `POST /pockets/<id>/{deposit,withdraw}`. Colonne `wallets.vaulted_minor` + table
> `vault_pockets` (migration `a1c9f4e2b7d3`).
> **Référentiel pays / opérateurs (BE-061)** : VOs `Country` / `Operator` + port
> `ReferenceDirectory` (superset de `CountryDirectory`). `StaticReferenceDirectory`
> (UEMOA + CEMAC : CI, SN, ML, BF, BJ, TG, NE, GW, CM, GA + opérateurs Orange/MTN/Moov/
> Wave…), `SqlAlchemyReferenceDirectory` (tables `countries`/`operators`),
> `CachingReferenceDirectory` (instantané mémoire revalidé contre `flash:reference:version`
> Redis ; `bump()` invalide tous les workers). `flash reference seed` + migration
> `f4b7c2109ea3`. Blueprint **public** `GET /v1/reference/countries` (+ `/countries/<code>`).
> **Grille multi-pays (BE-063)** : transfert CI 0,8 %, **SN 1,0 %** (preuve de généricité),
> CM/GA 0,9 % **en XAF** ; paiement marchand gratuit partout ; plafonds déclinés XOF/XAF.
> **67 chemins.** 885 tests unit + 20 d'intégration (Postgres réel), couverture 100 %
> domain+application, ruff + mypy stricts.
> **Phases 1-3 terminées. Phase 4 en cours** : `BE-061` + `BE-063` livrés. Prochaine :
> `BE-062` (CRUD back-office référentiel + audit trail), `BE-064` → `BE-078`.

Ce fichier est la vue d'ensemble. Le détail (une ligne = une tâche cochable) est dans
`docs/tasks/`. On avance **dans l'ordre des identifiants** à l'intérieur de chaque lot,
mais les lots Backend / Infra avancent en priorité car Web et Mobile en dépendent.

## Comment lire / mettre à jour

- `[ ]` = à faire · `[~]` = en cours (commencée, pas finie) · `[x]` = terminée + testée
- Ne jamais cocher `[x]` sans : code complet, tests verts, doc à jour, pas de `TODO`.
- Après chaque tâche : cocher ici **et** dans le fichier `docs/tasks/*.md` correspondant,
  puis actualiser la date et la ligne « Session courante » ci‑dessus.

## Avancement global

| Lot | Fichier détaillé | Fait / Total |
|-----|------------------|--------------|
| Fondations & docs | ce fichier | 6 / 6 |
| Backend (BE) | [docs/tasks/backend.md](docs/tasks/backend.md) | 62 / 78 |
| Web (WEB) | [docs/tasks/frontend-web.md](docs/tasks/frontend-web.md) | 0 / 46 |
| Mobile (MOB) | [docs/tasks/mobile.md](docs/tasks/mobile.md) | 0 / 44 |
| Infra & CI/CD (INFRA) | [docs/tasks/infra.md](docs/tasks/infra.md) | 2 / 24 |
| Design & marque (DSN) | [docs/tasks/design.md](docs/tasks/design.md) | 0 / 10 |

---

## Phase 0 — Fondations (terminée)

- [x] F0‑1 · Structure du monorepo (`backend web mobile infra design docs`)
- [x] F0‑2 · `README.md` + principes non négociables
- [x] F0‑3 · Cette map + fichiers de tâches détaillés
- [x] F0‑4 · `docs/architecture.md` (architecture hexagonale, couches, flux)
- [x] F0‑5 · `docs/domain-model.md` (entités, invariants, agrégats, événements)
- [x] F0‑6 · ADR 0001‑0004 (stack, hexagonal, ledger partie double, multi‑pays)

## Phase 1 — Socle backend (terminée)

Domaine partagé (Money, Currency, Country), identité (User, PhoneNumber ≤ 5), wallet,
**ledger partie double**, ports, config multi‑pays, app factory Flask, Postgres + Alembic,
auth (téléphone + PIN + OTP, JWT), erreurs & idempotence, tests unitaires du domaine.
→ `BE-001` à `BE-024`.

## Phase 2 — Cas d'usage cœur (terminée : 22 / 22)

Ouverture de compte, KYC par paliers, transfert P2P (frais 0,8 %), paiement marchand par
QR, dépôt cash agent, retrait cash agent (code de retrait), annulation / remboursement,
relevé & historique paginé, notifications (push FCM / email / in‑app SSE).
→ `BE-025` à `BE-046`.

## Phase 3 — Produits d'épargne & carte

Coffre (sous‑comptes verrouillables), objectifs d'épargne, épargne programmée & intérêts,
carte virtuelle (émission, gel, plafonds, tokenisation), rapprochement carte.
→ `BE-047` à `BE-060`.

## Phase 4 — Multi‑pays, marchands, agents, back‑office

Référentiel pays / opérateurs / grille tarifaire, interopérabilité (Orange/MTN/Moov via
adapters), comptes marchands & règlements, réseau d'agents (float, commissions, plafonds),
console d'administration (support, conformité, litiges), export réglementaire.
→ `BE-061` à `BE-078`.

## Phase 5 — Web (React)

Auth, tableau de bord, transfert, QR (scan + présenter), historique + reçus, coffre,
épargne, carte, gestion des 5 numéros, profil / KYC, **espace agent** (dépôt/retrait,
float, commissions), **back‑office** (rôles). i18n FR (+ EN), thème bordeaux, PWA.
→ `WEB-001` à `WEB-046`.

## Phase 6 — Mobile (Flutter)

Mêmes parcours client que le web + scan QR natif, biométrie, notifications push,
mode hors‑ligne lecture, deep links, build Android/iOS, signature.
→ `MOB-001` à `MOB-044`.

## Phase 7 — Industrialisation

CI complète (lint, tests, couverture, images), CD VPS (compose + Caddy + sauvegardes PG),
observabilité (logs JSON, métriques, /health), tests d'intégration & E2E, tests de
charge, revue sécurité (OWASP ASVS, secrets, rate‑limit), doc API publiée, runbook.
→ `INFRA-001` à `INFRA-024`, `BE` tests transverses.

---

## Prochaine action

**Phases 1-3 terminées.** **Phase 4 démarrée** : `BE-061` (référentiel pays / opérateurs :
`Country`/`Operator` + `ReferenceDirectory` static / SQL / cache Redis, `flash reference
seed`, `GET /v1/reference/countries`, migration `f4b7c2109ea3`) et `BE-063` (grille
tarifaire réellement par pays : CI 0,8 %, SN 1,0 %, CM/GA 0,9 % en XAF ; plafonds XOF/XAF).

Prochaine : `BE-062` (CRUD back-office `countries`/`operators`/`pricing_rules`/`limits`
avec rôles `compliance`/`admin` + audit trail immuable). Puis `BE-064` → `BE-067`
(interop opérateurs : port `OperatorGateway` + `SandboxOperatorGateway`,
`SendToOperatorAccount` / `TopUpFromOperator`, webhooks signés), `BE-068` → `BE-078`
(marchands & règlements, agents, back-office, conformité AML, exports réglementaires,
registre d'audit hash-chaîné).

✅ Phase 2 livrée : `BE-029` (KYC), `BE-032` (demandes de paiement), `BE-033` (marchand
QR), `BE-034` → `BE-036` (cash agent), `BE-037` (annulation / remboursement), `BE-038`
(relevé), `BE-039` (reçu détaillé), `BE-040/041/042` (notifications + SSE), `BE-043`
(course wallet), `BE-044/045` (jobs), `BE-046` (seed).
