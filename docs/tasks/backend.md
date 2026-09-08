# Tâches Backend (`BE`)

Ordre = ordre d'implémentation. `[ ]` à faire · `[~]` en cours · `[x]` fait+testé.
Chaque tâche livrée : code complet + tests + doc, **zéro `TODO`**.

## Phase 1 — Socle (BE-001 → BE-024)

- [x] **BE-001** · `backend/pyproject.toml` (deps : flask, sqlalchemy, alembic, psycopg,
  pydantic, argon2-cffi, pyjwt, redis, gunicorn, python-dotenv, structlog, qrcode ;
  dev : pytest, pytest-cov, ruff, mypy, factory-boy, freezegun). Layout `src/flash`.
- [x] **BE-002** · Arborescence des paquets : `domain/`, `application/`, `interface/`,
  `infrastructure/`, avec `__init__.py` et un `README` d'une ligne par couche.
- [x] **BE-003** · `domain/shared/money.py` : VO `Currency` (code, exponent), `Money`
  (entier mineur + Currency ; add/sub/mul/percent ; comparaisons ; interdit devises
  mixtes ; interdit négatif là où précisé). Tests exhaustifs.
- [x] **BE-004** · `domain/shared/identifiers.py` : `CountryCode`, `Msisdn` (parse/format
  E.164, indicatif pays), `IdempotencyKey`, `EntityId` (UUIDv7). Tests.
- [x] **BE-005** · `domain/shared/errors.py` : `DomainError` + sous‑classes avec `code`
  stable (SCREAMING_SNAKE) et message FR. Table des codes dans `docs/api/errors.md`.
- [x] **BE-006** · `domain/shared/ports.py` : `Clock`, `IdGenerator`, `UnitOfWork`,
  `EventPublisher`, `IdempotencyStore` (interfaces + docstrings de contrat).
- [x] **BE-007** · `domain/identity/user.py` : agrégat `User` (statut, `KycTier`,
  liste `PhoneNumber` ≤ 5, un principal, ajout/suppression/promotion, invariants).
  `DomainError.PhoneNumberLimitReached`, `PhoneNumberAlreadyLinked`. Tests.
- [x] **BE-008** · `domain/identity/pin.py` : VO `Pin` (4–6 chiffres, refuse suites
  triviales), port `PinHasher`. Tests.
- [x] **BE-009** · `domain/wallet/wallet.py` : agrégat `Wallet` (user, currency, statut,
  `available`/`reserved`, opérations de réservation). Tests.
- [x] **BE-010** · `domain/ledger/account.py` : `LedgerAccount` (type, propriétaire,
  devise, `normal_balance`). Plan de comptes en `domain/ledger/chart.py`.
- [x] **BE-011** · `domain/ledger/transaction.py` : `Posting` + `LedgerTransaction`
  (immuable ; invariant somme des postings = 0 par devise ; horodatée ; `reason`,
  `reference`, `metadata`). Fabriques : `transfer`, `fee`, `cash_in`, `cash_out`,
  `vault_move`, `savings_deposit`, `interest`, `reversal`. Tests d'équilibre.
- [x] **BE-012** · `domain/pricing/pricing.py` : `PricingRule` (bps, min, max, fixed),
  `PricingService.fee_for(country, operation, amount) -> Fee` avec règle d'arrondi.
  Transfert CI = 80 bps. Tests (montants limites, arrondis).
- [x] **BE-013** · `domain/limits/limits.py` : `LimitRule` par (pays, KYC), `LimitPolicy`
  (par opération, cumul jour/mois via port `LimitCounter`), `KycPolicy`. Tests.
- [x] **BE-014** · Ports métier : `UserRepository`, `WalletRepository`,
  `LedgerRepository`, `PricingRepository`, `LimitRepository` dans chaque sous‑paquet.
- [x] **BE-015** · `application/` : `Command`/`Result` de base, `UseCase` abstrait,
  décorateur/mixin d'idempotence, helper d'ouverture d'UoW.
- [x] **BE-016** · Fakes de test : `InMemoryUnitOfWork`, repos en mémoire, `FixedClock`,
  `SeqIdGenerator`, `InMemoryIdempotencyStore`, `RecordingEventPublisher` dans
  `tests/support/`.
- [x] **BE-017** · `infrastructure/db/` : `Base`, `engine`, session ; modèles SQLAlchemy
  pour user, phone_number, wallet, wallet_balances, ledger_account, ledger_transaction,
  ledger_posting, idempotency_key, outbox. Mapping ORM ↔ domaine explicite (mappers).
- [x] **BE-018** · `infrastructure/db/uow.py` : `SqlAlchemyUnitOfWork` (transaction,
  repos concrets, `collect_new_events`). Repos concrets user/wallet/ledger.
- [x] **BE-019** · Alembic : config + **migration initiale** couvrant BE-017. Script
  `flask flash db-upgrade`. Test : migration up/down sur base éphémère.
- [x] **BE-020** · `infrastructure/` divers : `SystemClock`, `Uuid7Generator`,
  `Argon2PinHasher`, `RedisIdempotencyStore`, `OutboxEventPublisher`.
- [x] **BE-021** · `interface/app.py` : `create_app(config)` ; enregistrement blueprints ;
  handler d'erreurs (`DomainError` → JSON `{code,message,details}` + HTTP) ; `request_id`
  middleware ; logs structlog JSON ; CORS configurable ; `/health` `/health/ready`.
- [x] **BE-022** · `interface/security/` : émission/vérif JWT (access 15 min, refresh
  rotatif lié `device_id`), dépendance `current_user`, révocation via Redis `jti`,
  rate‑limit (Redis token bucket) décorable par route.
- [x] **BE-023** · `tests/architecture/test_dependencies.py` : échoue si `domain/` importe
  flask / sqlalchemy / redis / requests / pydantic. + `ruff` + `mypy` config stricte.
- [x] **BE-024** · `interface/openapi.py` : génération OpenAPI 3.1 depuis les schémas
  pydantic + routes ; `/docs` (Swagger UI statique embarqué), `/redoc` ; écriture
  `docs/api/openapi.json` via `flask flash openapi-dump`.

## Phase 2 — Cas d'usage cœur (BE-025 → BE-046)

- [ ] **BE-025** · `RegisterUser` : msisdn + pin + pays → crée `User` (KYC tier 0),
  wallet devise du pays, `LedgerAccount` client. OTP d'activation. Idempotent.
- [ ] **BE-026** · `VerifyOtp` / `ResendOtp` (port `OtpChannel`, store Redis TTL, essais
  limités, anti‑bruteforce).
- [ ] **BE-027** · `Login` (msisdn + pin + device) → tokens ; `RefreshToken` ; `Logout`.
- [ ] **BE-028** · `AddPhoneNumber` (OTP sur le nouveau numéro, ≤ 5, unicité globale),
  `RemovePhoneNumber`, `SetPrimaryPhoneNumber`.
- [ ] **BE-029** · `SubmitKyc` (tier 1 : identité + selfie via port `DocumentStore`),
  `ReviewKyc` (back‑office) → change `KycTier`, recharge les limites applicables.
- [ ] **BE-030** · `GetWallet` / `ListWallets` (soldes depuis projection + cohérence).
- [ ] **BE-031** · `SendP2PTransfer` : cf. flux §3 architecture. Frais 0,8 %, limites,
  KYC, idempotence, `LedgerTransaction.transfer`+`fee`, événement `TransferCompleted`,
  reçu. Cas d'erreur couverts par tests.
- [ ] **BE-032** · `RequestMoney` (demande de paiement entre utilisateurs) + acceptation
  = déclenche un `SendP2PTransfer`.
- [ ] **BE-033** · `PresentMerchantQr` / `PayMerchant` : QR statique (id marchand) ou
  dynamique (montant, référence, expiration). Frais marchand selon `pricing_rules`.
  Règlement marchand différé via compte `bank_settlement`.
- [ ] **BE-034** · `CreateCashDeposit` (agent) : agent encaisse le cash → débit
  `agent_float`, crédit wallet client ; commission agent (`agent_commission_expense`).
  Vérifie plafond float agent, KYC client, limites.
- [ ] **BE-035** · `InitiateCashWithdrawal` (client) : génère un **code de retrait** à
  usage unique + réserve le montant+frais sur le wallet. TTL configurable.
- [ ] **BE-036** · `ConfirmCashWithdrawal` (agent saisit le code) : libère la réserve,
  débit wallet client, crédit `agent_float`, frais → `flash_fee_income`, commission
  agent. Idempotent. Expiration → `CancelCashWithdrawal` (rend la réserve).
- [ ] **BE-037** · `CancelTransfer` / `RefundMerchantPayment` : `LedgerTransaction.reversal`
  (jamais de suppression), fenêtre et règles d'autorisation.
- [ ] **BE-038** · `ListStatement` : historique paginé (curseur), filtres (type, période,
  contrepartie, statut), projection `statement_entries` alimentée par les événements.
- [ ] **BE-039** · `GetReceipt` : reçu détaillé d'une opération (montant, frais, réf,
  parties masquées, QR de vérification).
- [ ] **BE-040** · Notifications — port `Notifier` ; handlers d'événements → push (FCM),
  in‑app (table + SSE), email (SMTP) pour : réception d'argent, débit, dépôt/retrait
  agent, KYC, sécurité (nouvel appareil).
- [ ] **BE-041** · `interface` blueprints : `auth`, `users`, `phones`, `wallets`,
  `transfers`, `requests`, `merchant-payments`, `cash`, `statement`, `notifications`.
  Schémas in/out + exemples OpenAPI.
- [ ] **BE-042** · SSE `/v1/notifications/stream` (auth, keep‑alive, reprise par
  `Last-Event-ID`, backend Redis pub/sub).
- [ ] **BE-043** · Verrous & concurrence : verrou pessimiste par wallet dans l'UoW,
  test de course (deux transferts simultanés ne doivent pas passer le solde en négatif).
- [ ] **BE-044** · Job `expire_withdrawal_codes` (planifié) + `flask flash run-jobs`.
- [ ] **BE-045** · Job `reconcile_wallet_balances` : recompute depuis le ledger, alerte
  si écart, endpoint back‑office pour lancer à la demande.
- [ ] **BE-046** · Seed de développement : pays CI/SN, grille tarifaire, limites par
  KYC, 1 agent, 1 marchand, 2 utilisateurs. `flask flash seed`.

## Phase 3 — Épargne & carte (BE-047 → BE-060)

- [ ] **BE-047** · `domain/vault/vault.py` : `Vault` (poches verrouillables sur un wallet ;
  `available` du wallet exclut le contenu du coffre). Tests d'invariants.
- [ ] **BE-048** · `MoveToVault` / `MoveFromVault` : `LedgerTransaction.vault_move` entre
  analytique `client_liability` et `savings_liability` (poche coffre), instantané, sans
  frais. Historisé.
- [ ] **BE-049** · `CreateVaultPocket` (nom, objectif optionnel, option « verrouillé
  jusqu'à date »), `RenameVaultPocket`, `DeleteVaultPocket` (vide obligatoire).
- [ ] **BE-050** · `domain/savings/plan.py` : `SavingsPlan` (objectif montant/date,
  fréquence de versement, source wallet, statut, taux annuel).
- [ ] **BE-051** · `OpenSavingsPlan` / `CloseSavingsPlan` (rapatrie au wallet).
- [ ] **BE-052** · Job `run_scheduled_savings` : prélève les versements dus (échoue
  proprement si solde insuffisant → notification, réessai).
- [ ] **BE-053** · Job `accrue_savings_interest` : calcul quotidien prorata, crédite
  mensuellement via `LedgerTransaction.interest` (`interest_expense`). Tests de calcul.
- [ ] **BE-054** · Blueprints `vault`, `savings` + schémas + OpenAPI + notifications.
- [ ] **BE-055** · `domain/card/card.py` : `Card` (token PAN, 4 derniers, réseau, statut
  ACTIVE/FROZEN/CLOSED, plafonds jour/mois, canaux autorisés e‑com/sans‑contact).
- [ ] **BE-056** · Port `CardIssuer` + `SandboxCardIssuer` (émission, gel, clôture,
  autorisation). `IssueCard` / `FreezeCard` / `UnfreezeCard` / `CloseCard` /
  `SetCardLimits`.
- [ ] **BE-057** · Webhook `POST /v1/cards/authorizations` (signé) : autorisation carte →
  réservation sur le wallet ; `capture` / `refund` / `reversal` → `LedgerTransaction`
  via `card_scheme_suspense`. Idempotent par `authorization_id`.
- [ ] **BE-058** · `GetCardSensitive` : renvoie PAN/CVV **uniquement** via un flux chiffré
  court, audité, rate‑limité, jamais journalisé.
- [ ] **BE-059** · Rapprochement carte : job qui compare `card_scheme_suspense` aux
  fichiers réseau simulés ; rapport d'écarts.
- [ ] **BE-060** · Blueprint `cards` complet + OpenAPI + notifications (autorisation,
  gel, plafond atteint).

## Phase 4 — Multi‑pays, marchands, agents, back‑office (BE-061 → BE-078)

- [ ] **BE-061** · `domain/country/` : `Country`, `Operator`, chargement depuis DB + cache
  Redis, invalidation. `GET /v1/reference/countries`.
- [ ] **BE-062** · CRUD back‑office : `countries`, `pricing_rules`, `limits`, `operators`
  (rôle `compliance`/`admin`), avec audit trail immuable des changements.
- [ ] **BE-063** · `PricingService` multi‑pays effectif + tests par pays (CI 0,8 % ;
  paramétrer SN différemment pour prouver la généricité).
- [ ] **BE-064** · Port `OperatorGateway` + `SandboxOperatorGateway` : `payout` (Flash →
  Orange/MTN/Moov) et `collect` (opérateur → Flash), statuts asynchrones + webhooks.
- [ ] **BE-065** · `SendToOperatorAccount` (retrait interopérable) : réserve, appel
  `payout`, `operator_suspense`, réconciliation sur callback ; échec → reversal.
- [ ] **BE-066** · `TopUpFromOperator` (dépôt depuis un compte opérateur) via `collect` +
  webhook signé.
- [ ] **BE-067** · Webhooks opérateurs `POST /v1/operators/{op}/callbacks` (signature,
  rejeu, idempotence, mise à jour du suspense).
- [ ] **BE-068** · `domain/merchant/` : `Merchant` (catégorie, comptes de règlement,
  frais négociés, sous‑comptes caisses/employés).
- [ ] **BE-069** · Onboarding marchand + KYB, génération QR marchand (statique + affiche
  imprimable PDF), clés API marchand.
- [ ] **BE-070** · Règlements marchands : job `settle_merchants` (fréquence par marchand)
  → virement `bank_settlement` (port `BankGateway` + sandbox), relevé de règlement.
- [ ] **BE-071** · API marchande publique (`/merchant/v1/…`) : créer une demande de
  paiement, statut, remboursement, webhooks marchand signés. Doc séparée.
- [ ] **BE-072** · `domain/agent/` : `Agent` (float, plafonds, grille de commission,
  hiérarchie master/sous‑agent), `AgentFloatTopUp` / `AgentFloatWithdraw`.
- [ ] **BE-073** · Commissions agent : calcul par opération, cumul, versement périodique
  (`agent_commission_expense` → wallet agent), relevé de commissions.
- [ ] **BE-074** · Espace agent API : lister opérations, dépôt/retrait, solde float,
  commissions, recherche client par msisdn (données minimales).
- [ ] **BE-075** · Back‑office API : recherche utilisateur, détail compte, gel/dégel,
  liste des transactions, forcer reversal, notes, tickets de support. RBAC
  (`support`, `compliance`, `finance`, `admin`) + audit de chaque action.
- [ ] **BE-076** · Conformité : détection de seuils (structuration, vélocité), file
  d'alertes AML, blocage préventif, export STR/CTR (format CSV paramétrable).
- [ ] **BE-077** · Exports réglementaires & compta : balance des comptes du ledger à une
  date, journal, export mensuel par pays. Vérif : la balance est équilibrée.
- [ ] **BE-078** · Registre d'audit consultable (qui/quoi/quand/avant‑après) pour toutes
  les actions sensibles, immuable (append‑only + hash chaîné).

## Transverse (au fil des phases)

- [ ] **BE-T1** · Couverture ≥ 90 % `domain/` + `application/` (garde‑fou CI).
- [ ] **BE-T2** · Tests d'intégration DB réels (Postgres) sur repos + migrations + UoW.
- [ ] **BE-T3** · Tests de contrat OpenAPI (schemathesis) sur toutes les routes.
- [ ] **BE-T4** · Journalisation d'audit + métriques Prometheus (`/metrics`).
- [ ] **BE-T5** · `docs/api/errors.md` maintenu exhaustif (tous les `code`).
- [ ] **BE-T6** · Script de charge (locust) : transferts concurrents, objectif p95.
