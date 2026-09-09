# Flash — Map de développement

> **Dernière mise à jour : 2026-09-09**
> **Phases 1-3 complètes · Phase 4 backend TERMINÉE : BE-061→078 + transverses BE-T1→T6 livrés (… conformité AML, exports réglementaires, audit consultable, sous-comptes marchands & frais/canal, CI GitHub Actions, métriques Prometheus, contrats OpenAPI, test de charge)**
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
> **120 chemins** : `auth` (6), `phones` (5), `wallets` (2), `transfers` (2),
> `payment-requests` (4), `merchant` (17, dont `sub-accounts`), `merchant-payments` (1),
> `merchant/v1`
> (public, 4), `statement` (1), `receipts` (1), `notifications` (4), `withdrawals` (2),
> `agent` (8), `kyc` (4), `vault` (6), `savings` (5), `cards` (8),
> `cards/authorizations` (4), `operators` (3) + `operators/callbacks` (1),
> `reference` (2), `admin/kyc` (1), `admin` ops (9), `admin/merchants` (3, KYB + frais/canal),
> `admin/agents` (1), `admin/accounts` (6) + `admin/transactions` (1) +
> `admin/tickets` (3), `admin/compliance` (4), `admin/reports` (3),
> `admin/reference` (9, dont `pricing` / `limits` éditables) +
> `admin/audit` (2, dont `/verify`) + `/health*`, `/openapi.json`, `/docs`, `/redoc`.
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
> **CRUD back-office + audit chaîné (BE-062)** : `require_role("admin","compliance")` (clés
> `ADMIN_API_KEYS` porteuses d'un rôle) ; `PUT`/`DELETE /v1/admin/reference/countries` &
> `.../operators`, `POST .../reload` (invalide le cache), `GET /v1/admin/audit?verify=1`.
> Chaque mutation écrit une entrée dans un **registre d'audit append-only chaîné par
> hachage** (`AuditEntry` : `prev_hash` + `entry_hash` sur le contenu canonique ;
> `verify_chain` détecte trou / lien cassé / altération). Table `audit_entries`.
> **Interop opérateurs (BE-064 → BE-067)** : port `OperatorGateway` (`payout`/`collect`
> **asynchrones** → `GatewayAck`) + `SandboxOperatorGateway` ; agrégat `OperatorTransfer`
> (PENDING → SUCCEEDED/FAILED, idempotent) ; `LedgerTransaction.operator_payout` /
> `operator_collect` via `OPERATOR_SUSPENSE`. `SendToOperatorAccount` (réserve
> `amount + fee`, appelle la passerelle ; refus → `release`), `TopUpFromOperator` (PENDING
> sans mouvement) ; résolution sur webhook signé `POST /v1/operators/{op}/callbacks`
> (`require_operator_webhook` HMAC ; idempotent par `reference` ; `SUCCEEDED` →
> `settle_reservation`/`credit(amount-fee)` + écriture ; `FAILED` → `release`). Grille
> payout 1,5 % / collect 1 % par pays. Table `operator_transfers`.
> **KYB marchand + clés d'API + affiche (BE-069)** : `Merchant.kyb_status`
> (PENDING/APPROVED/REJECTED) — `submit_kyb` (self), `approve_kyb`/`reject_kyb`
> (back-office `admin`/`compliance` via `POST /v1/admin/merchants/<id>/kyb`),
> `ensure_kyb_approved`. Entité `MerchantApiKey` (préfixe visible + hash SHA-256 salé,
> jamais de secret en clair, révocable) ; port `MerchantApiKeyVault` +
> `Sha256MerchantApiKeyVault` (secret `mk_<prefix>_<random>`) ;
> `POST/GET/DELETE /v1/merchant/api-keys` (secret montré une seule fois, 10 actives max).
> Affiche imprimable PNG A5 avec QR statique : port `MerchantPosterRenderer` +
> `PillowMerchantPosterRenderer`, `GET /v1/merchant/poster`. Table `merchant_api_keys`
> + colonnes KYB, migration `d4e8a1c6b923`.
> **Règlements marchands (BE-070)** : port `BankGateway` (`transfer` → `BankAck`
> synchrone) + `SandboxBankGateway` ; `Merchant.configure_settlement` (compte
> `BankAccount`, fréquence MANUAL/DAILY/WEEKLY/MONTHLY, `next_settlement_at`) ; agrégat
> `MerchantSettlement` (PENDING → PAID/FAILED) ; `LedgerTransaction.merchant_settlement`
> (`MERCHANT_PAYABLE` ↓ / `BANK_SETTLEMENT` ↓). `settle_merchant` agrège le net des
> `MerchantPayment` non réglés, vire, rattache les paiements, avance l'échéance ; échec
> banque → règlement FAILED, paiements rendus au cycle suivant. Routes
> `PUT /v1/merchant/settlement`, `POST|GET /v1/merchant/settlements`,
> `GET /v1/merchant/settlements/{id}` (relevé) ; job `SettleDueMerchants`
> (`flash run-jobs` + `POST /v1/admin/jobs/merchants/settle`) ; notifications `SETTLEMENT`.
> Table `merchant_settlements`, migration `c7d2f4a91b38`.
> **API marchande publique (BE-071)** : `Blueprint /merchant/v1` authentifié par clé
> d'API (`Authorization: Bearer mk_…` ou `X-Merchant-Key`) → `AuthenticateMerchantApiKey`
> (401 si clé inconnue/révoquée, marchand suspendu ou KYB non validé ; horodate la clé).
> `POST /merchant/v1/charges` (crée un QR dynamique), `GET /merchant/v1/charges/{id}`
> (état + paiement lié), `POST /merchant/v1/charges/{id}/refund`, `GET
> /merchant/v1/payments`. Webhooks signés : `Merchant.configure_webhook` (URL http(s) +
> secret ≥ 16) via `PUT|DELETE /v1/merchant/webhook` ; `MerchantWebhookEnqueuer`
> (consommateur d'événements chaîné après le dispatcher) met en file une
> `MerchantWebhookDelivery` sur `MerchantPaymentCompleted`/`Refunded` si un webhook est
> configuré, idempotent par `(event_type, payment_id)` ; job `DispatchMerchantWebhooks`
> (`flash run-jobs` + `POST /v1/admin/jobs/merchants/webhooks`) POST le corps JSON signé
> `X-Flash-Signature: sha256=HMAC(secret, body)` via `HttpMerchantWebhookSender`, backoff
> exponentiel sur 6 tentatives puis `FAILED`. Table `merchant_webhook_deliveries` +
> colonnes `webhook_url`/`webhook_secret`, migration `e1f4b7c92a05`.
> **Réseau d'agents enrichi (BE-072/073/074)** : `Agent` gagne `parent_agent_id`
> (hiérarchie master ↔ sous-agent), `commission_earned`/`commission_paid` (cumul,
> `commission_owed`), `top_up_float`/`withdraw_float`, `pay_commission`. Factories
> `agent_float_withdraw` et `agent_commission_payout` (float ↓ / wallet agent ↑). Espace
> agent `/v1/agent` : `GET /`, `GET /operations`, `POST /float/topup`,
> `POST /float/withdraw`, `POST /commission/payout`, `GET /customers?msisdn=`. Job
> `PayDueAgentCommissions` (`POST /v1/admin/jobs/agents/commissions`) ; back-office
> `POST /v1/admin/agents/<id>/master`. Migration `f2a9c1e83b47`.
> **Back-office comptes & support (BE-075)** : `GET /v1/admin/accounts?q=` (id ou
> msisdn), `GET /v1/admin/accounts/<id>` (wallets, notes, tickets),
> `GET …/transactions` (ledger signé), `POST …/freeze` (`support`+),
> `POST /v1/admin/transactions/force-reversal` (contre-passation P2P hors fenêtre,
> `finance`/`admin` ; échoue si le bénéficiaire a dépensé), notes
> `POST|GET …/notes`, tickets `POST|GET /v1/admin/tickets` +
> `POST …/<id>/status` (entité `SupportTicket` OPEN→PENDING→RESOLVED/CLOSED). **Chaque
> action écrit une entrée d'audit chaîné** (`account.freeze`,
> `transaction.force_reversal`, `ticket.open`…). Tables `support_notes` /
> `support_tickets`, migration `a3c7e91d5f28`. `NOT_AN_AGENT` → 404.
> **Conformité / AML (BE-076)** : agrégat `ComplianceAlert` (OPEN → REVIEWING → CLEARED /
> ESCALATED). Job `ScanForAmlAlerts` (`POST /v1/admin/jobs/compliance/scan` +
> `flash run-jobs`) parcourt les débits récents des portefeuilles clients
> (`ledger.list_since`) et applique 3 règles paramétrables (`Settings` `AML_*`) :
> **CTR_THRESHOLD** (débit unitaire ≥ seuil), **STRUCTURING** (≥ N débits juste sous le
> seuil sur une fenêtre, somme > seuil), **VELOCITY** (trop d'opérations / trop de volume
> sur 24 h) ; dédoublonné par `(user, kind, window_key)`. `GET|POST
> /v1/admin/compliance/alerts` (file + ouverture manuelle), `POST …/<id>/review`
> (`clear` = faux positif / `escalate` = **gel préventif du compte** + STR), export CSV
> `GET /v1/admin/compliance/reports/str?start&end`. Chaque revue est auditée
> (`aml.alert.escalate`…). Table `compliance_alerts`, migration `b8d1f6a2c904`.
> **Exports réglementaires & compta (BE-077)** : `GET /v1/admin/reports/trial-balance
> ?as_of=` (balance générale à une date : par compte du plan, cumul débit / crédit +
> solde signé ; **contrôle : par devise Σ débits = Σ crédits**, sinon 409),
> `GET …/journal?start&end` (journal chronologique des écritures + postings),
> `GET …/monthly?year&month&currency=` (CSV d'un mois, une ligne par posting, filtre
> devise/zone). Lectures seules, rôles `finance` / `admin`. Ports ledger
> `list_accounts` / `list_between` ajoutés.
> **Registre d'audit consultable (BE-078)** : `GET /v1/admin/audit` filtré
> (`actor` / `action` / `resource_type` / `resource_id` / `start` / `end` / `limit` /
> `before_sequence`, plus récentes d'abord ; `?verify=1` joint le rapport d'intégrité),
> `GET /v1/admin/audit/verify` (contrôle de toute la chaîne chaînée par hachage :
> `intact`, `checked`, `broken_at`, `reason` — 409 si rompue). Le registre reste
> append-only + chaîné (BE-062) ; ports `AuditLog.query` / `verify_report` +
> `audit_chain_report` (localise la 1re rupture). Rôles `admin` / `compliance`, pas de
> migration.
> **Grille tarifaire & plafonds éditables (reste de BE-062)** : tables `pricing_rules` /
> `limit_rules` (migration `c3f5a9e0d182`), repos SQL en lecture directe +
> `SqlAlchemyPricingEditor` / `SqlAlchemyLimitEditor`, CRUD back-office
> `PUT/GET/DELETE /v1/admin/reference/pricing[/<pays>/<op>]` et
> `…/limits[/<pays>/<palier>/<op>]` (rôles `admin`/`compliance`, chaque mutation auditée
> `pricing_rule.*` / `limit_rule.*`). `flash reference seed` charge aussi la grille et les
> plafonds. Câblage : `REFERENCE_SOURCE=db` → base, sinon jeu par défaut en lecture seule.
> **Sous-comptes marchands & frais par canal (reste de BE-068)** : agrégat
> `MerchantSubAccount` (caisse `TILL` / employé `EMPLOYEE`, simple **étiquette
> d'attribution**), CRUD libre-service `/v1/merchant/sub-accounts` (POST/GET/PATCH) ;
> les paiements (QR statique, demande, API) portent un `sub_account_id` optionnel et le
> relevé filtre dessus. `PaymentChannel` (`QR` / `API`) + `Merchant.channel_fees` :
> commission négociée par canal côté back-office
> (`PUT/DELETE /v1/admin/merchants/<id>/channel-fees/<canal>`, `GET …/fees`), sinon
> `fee_bps` par défaut. Migration `d1e4b7a2f9c6`.
> **Lots transverses `BE-T1` → `BE-T6` livrés** : CI GitHub Actions
> (`.github/workflows/backend-ci.yml` : ruff + mypy + `pytest --cov` avec Postgres/Redis
> + diff OpenAPI), tests de migrations Alembic (upgrade / round-trip / diff modèles),
> tests de contrat OpenAPI (schemathesis, 137 opérations), métriques Prometheus
> `GET /metrics` (hors OpenAPI), `docs/api/errors.md` exhaustif (garde-fou
> `test_errors_doc.py`), script de charge locust (`backend/loadtest/`, SLO p95 < 300 ms).
> **120 chemins.** 1375 tests unit + 39 d'intégration + contrat OpenAPI (schemathesis),
> couverture 100 % domain+application, ruff + mypy stricts.
> **Phases 1-3 terminées. Phase 4 backend TERMINÉE** : `BE-061` → `BE-078` livrés
> (référentiel + grille / plafonds éditables, audit chaîné + registre consultable, grille
> multi-pays, interop opérateurs, marchands complets — sous-comptes & frais par canal
> inclus —, agents enrichis + espace agent, back-office comptes & support, conformité
> AML, exports réglementaires). Migrations `f4b7c2109ea3`, `a8e3d5f10c47`,
> `b6c1e9d47f20`, `c7d2f4a91b38`, `d4e8a1c6b923`, `e1f4b7c92a05`, `f2a9c1e83b47`,
> `a3c7e91d5f28`, `b8d1f6a2c904`, `c3f5a9e0d182`, `d1e4b7a2f9c6`.

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
| Backend (BE) | [docs/tasks/backend.md](docs/tasks/backend.md) | 70 / 78 + transverses BE-T1→T6 |
| Web (WEB) | [docs/tasks/frontend-web.md](docs/tasks/frontend-web.md) | 46 / 49 (socle, client, agent, back-office) |
| Mobile (MOB) | [docs/tasks/mobile.md](docs/tasks/mobile.md) | 0 / 44 |
| Infra & CI/CD (INFRA) | [docs/tasks/infra.md](docs/tasks/infra.md) | 3 / 24 |
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

**Phases 1-3 terminées.** **Phase 4 backend livrée** (`BE-061` → `BE-078`, `BE-068`
partiel) : `BE-061` (référentiel `Country`/`Operator`
+ `ReferenceDirectory` static / SQL / cache Redis + `flash reference seed`), `BE-063`
(grille réellement par pays : CI 0,8 %, SN 1,0 %, CM/GA 0,9 % en XAF), et `BE-062`
(CRUD `countries`/`operators` + **grille tarifaire / plafonds éditables** en base sous
rôle `admin`/`compliance` + **registre d'audit chaîné par hachage** — fondation de
`BE-078`). Migrations `f4b7c2109ea3`, `a8e3d5f10c47`, `c3f5a9e0d182`.

`BE-069` **livré** (KYB marchand `submit`/`approve`/`reject` + `ensure_kyb_approved` ;
entité `MerchantApiKey` + `Sha256MerchantApiKeyVault` ; `POST/GET/DELETE
/v1/merchant/api-keys` ; affiche PNG `GET /v1/merchant/poster` via
`PillowMerchantPosterRenderer` ; migration `d4e8a1c6b923`). `BE-070` **livré**
(règlements marchands : `BankGateway` + `SandboxBankGateway`, agrégat
`MerchantSettlement`, `settle_merchant`, routes + job `SettleDueMerchants`, migration
`c7d2f4a91b38`). `BE-068` **partiel** (VO `BankAccount`, `SettlementFrequency`,
`KybStatus`, planification d'échéance).

`BE-071` **livré** (API marchande publique `/merchant/v1/…` par clé d'API +
`AuthenticateMerchantApiKey`, webhooks signés `MerchantWebhookDelivery` +
`DispatchMerchantWebhooks`, migration `e1f4b7c92a05`).

`BE-072`/`BE-073`/`BE-074` **livrés** (agents : `parent_agent_id` + `attach_to_master`,
`commission_earned`/`paid`/`owed`, `top_up_float`/`withdraw_float`, `pay_commission` ;
factories `agent_float_withdraw` / `agent_commission_payout` ; espace `/v1/agent` ; job
`PayDueAgentCommissions` ; migration `f2a9c1e83b47`).

`BE-075` **livré** (back-office comptes & support : recherche / détail / transactions /
gel-dégel / contre-passation P2P forcée / notes / tickets `SupportTicket`, chaque action
tracée dans le registre d'audit chaîné, RBAC `support`/`compliance`/`finance`/`admin`,
migration `a3c7e91d5f28`).

`BE-076` **livré** (conformité AML : agrégat `ComplianceAlert`, job `ScanForAmlAlerts`
— CTR_THRESHOLD / STRUCTURING / VELOCITY paramétrables —, file d'alertes + revue avec
gel préventif à l'escalade, export STR CSV, migration `b8d1f6a2c904`).

`BE-077` **livré** (exports réglementaires & compta : `GetTrialBalance` avec contrôle
d'équilibre, `GetLedgerJournal`, `ExportMonthlyLedger` CSV ; ports ledger
`list_accounts` / `list_between` ; blueprint `/v1/admin/reports`, rôles `finance`/`admin`
— lectures seules, pas de migration).

`BE-078` **livré** (registre d'audit consultable : `QueryAuditLog` filtré
actor/action/ressource/période + curseur, `VerifyAuditChain` avec `audit_chain_report`
qui localise la 1re rupture ; ports `AuditLog.query` / `verify_report` ; blueprint
`/v1/admin/audit` + `/verify`, rôles `admin`/`compliance` — le registre reste
append-only + chaîné par hachage de BE-062, pas de migration).

Reste de `BE-062` **livré** (grille tarifaire & plafonds éditables : tables
`pricing_rules` / `limit_rules`, repos SQL + éditeurs, CRUD back-office audité sous
`/v1/admin/reference/pricing` et `…/limits`, `flash reference seed` étendu, migration
`c3f5a9e0d182`).

Reste de `BE-068` **livré** (agrégat `MerchantSubAccount` caisses/employés + CRUD
`/v1/merchant/sub-accounts` + attribution `sub_account_id` sur les paiements et le
relevé ; `PaymentChannel` QR/API + `Merchant.channel_fees` négociés sous
`/v1/admin/merchants/<id>/channel-fees/<canal>` ; migration `d1e4b7a2f9c6`).

**Phase 4 backend TERMINÉE** (`BE-061` → `BE-078`) + **lots transverses `BE-T1` → `BE-T6`
livrés** (CI GitHub Actions, tests de migrations, contrats OpenAPI schemathesis, métriques
Prometheus `/metrics`, `docs/api/errors.md` exhaustif, test de charge locust).

**Front web `web/` : `WEB-001` → `WEB-046` livrés** (46/49 ; reste transverse `WEB-047→049`).
Vite + React 18 + TS strict ; `design/tokens.json` (bordeaux) → CSS ; `shared/ui` + galerie
`/ui` ; client API typé généré depuis `openapi.json` + `apiFetch` (Idempotency-Key,
X-Request-ID, refresh 401) ; session + garde de routes ; layout responsive ; i18n FR ;
ErrorBoundary + 404/500 + toasts ; PWA ; a11y ; config runtime ; Dockerfile + compose.
**Parcours client** (17 écrans) : inscription, connexion, tableau de bord, envoyer, demander,
payer marchand (scan QR), recevoir, retrait/dépôt cash, opérateur, historique (scroll
infini) + reçu, coffre, épargne, carte (révéler PAN/CVV), profil (KYC / numéros / sécurité /
paramètres), notifications (SSE). **Espace agent** : tableau de bord (float, commissions),
dépôt / retrait client, journal + export CSV, gestion du float. **Back-office** (arbre
`/admin/*` séparé, clé `X-Admin-Key`) : comptes (gel, contre-passation forcée, notes),
KYC, AML (statuer + export STR), référentiel (grille / plafonds), finance (balance,
journal, export), audit (+ contrôle d'intégrité de la chaîne). `tsc` + ESLint + Prettier
OK, 10 tests Vitest, build OK, e2e Playwright. Correctif backend au passage : `openapi.py`
hisse les `$defs` Pydantic dans `components/schemas`.

Prochaine : transverse web (`WEB-047` tests E2E parcours, `WEB-048` perf/Lighthouse,
`WEB-049` i18n complète), puis `MOB-*`, `INFRA` (CD/VPS), `DSN-*`.

✅ Phase 2 livrée : `BE-029` (KYC), `BE-032` (demandes de paiement), `BE-033` (marchand
QR), `BE-034` → `BE-036` (cash agent), `BE-037` (annulation / remboursement), `BE-038`
(relevé), `BE-039` (reçu détaillé), `BE-040/041/042` (notifications + SSE), `BE-043`
(course wallet), `BE-044/045` (jobs), `BE-046` (seed).
