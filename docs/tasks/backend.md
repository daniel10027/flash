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

- [x] **BE-025** · `RegisterUser` : msisdn + pin + pays → crée `User` (KYC tier 0),
  wallet devise du pays, `LedgerAccount` client. OTP d'activation. Idempotent.
- [x] **BE-026** · `VerifyOtp` / `ResendOtp` (port `OtpChannel`, store Redis TTL, essais
  limités, anti‑bruteforce).
- [x] **BE-027** · `Login` (msisdn + pin + device) → tokens ; `RefreshToken` ; `Logout`.
- [x] **BE-028** · `AddPhoneNumber` (OTP sur le nouveau numéro, ≤ 5, unicité globale),
  `RemovePhoneNumber`, `SetPrimaryPhoneNumber`.
- [x] **BE-029** · `SubmitKyc` (paliers 1/2 : pièces via port `DocumentStore`, base64,
  idempotent), `WithdrawKyc`, `GetKycStatus`/`ListMyKycCases`, `ReviewKyc` (back‑office
  par clé `X-Admin-Key` en attendant le RBAC BE-071) → `approve` relève `KycTier` (les
  limites étant résolues par `(pays, palier)` à chaque opération). Agrégat `KycCase`
  (+ `KycDocument`), tables `kyc_cases`/`kyc_documents`, `LocalFilesystemDocumentStore`.
- [x] **BE-030** · `GetWallet` / `ListWallets` (soldes depuis projection + cohérence).
- [x] **BE-031** · `SendP2PTransfer` : cf. flux §3 architecture. Frais 0,8 %, limites,
  KYC, idempotence, `LedgerTransaction.transfer`+`fee`, événement `TransferCompleted`,
  reçu. Cas d'erreur couverts par tests.
- [x] **BE-032** · Demandes de paiement : agrégat `PaymentRequest` (PENDING → ACCEPTED /
  DECLINED / CANCELLED / EXPIRED, TTL 7 j). `CreatePaymentRequest` (idempotent),
  `AcceptPaymentRequest` (clé de transfert dérivée `paymentreq-<id>` → pas de double
  débit ; échoue proprement si fonds insuffisants, demande reste PENDING),
  `DeclinePaymentRequest`, `CancelPaymentRequest`, `ListPaymentRequests` (incoming /
  outgoing). Blueprint `/v1/payment-requests`, table `payment_requests`.
- [x] **BE-033** · Paiement marchand par QR : agrégats `Merchant` (enrôlement + CLI
  `flash merchant enroll`, `fee_bps`), `MerchantCharge` (QR **dynamique** : montant +
  référence + expiration, PENDING → PAID / CANCELLED / EXPIRED), `MerchantPayment`.
  `PayMerchant` (gratuit pour le client ; le marchand paie `fee_bps`, net sur
  `MERCHANT_PAYABLE`, `fee` sur `FLASH_FEE_INCOME`) via `LedgerTransaction.merchant_payment`,
  idempotent. QR **statique** (`flash://pay?m=<id>`, montant saisi). Routes `/v1/merchant/*`
  + `/v1/merchant-payments`. Règlement différé marchand = BE-063.
- [x] **BE-034** · `CreateCashDeposit` (agent) : agent encaisse le cash → débit
  `agent_float`, crédit wallet client ; commission agent (`agent_commission_expense`).
  Vérifie plafond float agent, KYC client, limites. Agrégats `Agent` + `CashOrder`,
  `EnrollAgent` + CLI `flash agent enroll`, `LedgerTransaction.agent_float_topup`.
- [x] **BE-035** · `InitiateCashWithdrawal` (client) : génère un **code de retrait** à
  usage unique (`PepperedWithdrawalCodes`, SHA-256 poivré) + réserve le montant+frais
  sur le wallet. TTL 15 min. `POST /v1/withdrawals`, idempotent.
- [x] **BE-036** · `ConfirmCashWithdrawal` (agent saisit le code) : libère la réserve,
  débit wallet client, crédit `agent_float`, frais → `flash_fee_income`, commission
  agent. Idempotent. `POST /v1/agent/withdrawals/confirm`. Annulation →
  `CancelCashWithdrawal` (`POST /v1/withdrawals/<id>/cancel`, rend la réserve).
- [x] **BE-037** · `CancelTransfer` / `RefundMerchantPayment` : contre-passation via
  `LedgerTransaction.reversal` (jamais de suppression). Fenêtre `reversal_window`
  (config, 1 h) → `ReversalWindowClosed` ; une seule fois → `DuplicateOperation` ;
  `CancelTransfer` réservé à l'émetteur et refusé si le destinataire a déjà dépensé →
  `RefundNotPossible` ; `RefundMerchantPayment` réservé au marchand, `MerchantPayment`
  passe `REFUNDED`. Routes `POST /v1/transfers/<id>/cancel`,
  `POST /v1/merchant/payments/<id>/refund`. Événements `TransferReversed`,
  `MerchantPaymentRefunded`.
- [x] **BE-038** · `ListStatement` : historique paginé (curseur), filtres (type, période,
  contrepartie, statut), projection `statement_entries` alimentée par les événements.
- [x] **BE-039** · `GetReceipt` : reçu détaillé d'une opération à partir du ledger (par
  id de transaction **ou** référence métier `TRX-`/`MPY-`/`DEP-`/`WDL-`…). Sens, montant
  net, frais supportés par l'appelant (isolés uniquement pour transfert / retrait),
  contrepartie masquée, note, statut `COMPLETED` / `REVERSED` (+ `reversed_at`).
  Réservé aux parties prenantes (un portefeuille touché) → sinon 404. Route
  `GET /v1/receipts/<reference>`. Projection factorisée avec `ListStatement`.
- [x] **BE-040** · Notifications — port `Notifier` + canaux `InAppChannel` (table
  `notifications`), `SmtpEmailChannel` (SMTP, actif dès qu'une adresse est jointe),
  `FcmPushChannel` (stub jusqu'à la collecte des jetons, BE-042),
  `LoggingNotificationChannel`. `NotificationDispatcher` mappe les événements de l'outbox
  (`TransferCompleted/Reversed`, `CashDeposit/WithdrawalConfirmed`,
  `MerchantPayment(Completed|Refunded)`, `KycCase(Approved|Rejected)`) → notifications,
  branché en aval de l'`EventPublisher` via `NotifyingEventPublisher` (best-effort,
  post-commit). Blueprint `/v1/notifications` (liste paginée + curseur + `unread`,
  `/<id>/read`, `/read-all`). Le flux SSE reste BE-042.
- [x] **BE-041** · `interface` blueprints livrés au fil des lots : `auth`, `phones`,
  `wallets`, `transfers` (+ `cancel`), `payment-requests`, `merchant` / `merchant-payments`,
  `withdrawals` / `agent` (cash), `kyc` / `admin/kyc`, `statement`, `receipts`,
  `notifications`. Schémas pydantic in/out + OpenAPI 3.1 (`/docs`, `/redoc`,
  `docs/api/openapi.json`, 38 chemins).
- [x] **BE-042** · SSE `GET /v1/notifications/stream` (auth). `NotificationStream`
  compose : rattrapage depuis le journal si `Last-Event-ID` (id > last, ordre chrono,
  dédoublonné avec le live), puis abonnement au bus temps réel. Bus
  `RedisNotificationBus` (pub/sub `flash:notif:<user>`, keep-alive `: keep-alive` à
  chaque expiration du poll) branché comme canal (`BusChannel`) du `FanOutNotifier` —
  fonctionne donc entre workers gunicorn (classe worker asynchrone requise en prod).
  En-têtes `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`,
  `retry: 3000`.
- [x] **BE-043** · Verrous & concurrence : `WalletRepository.get_for_update`
  (`SELECT … FOR UPDATE`) déjà utilisé par `SendP2PTransfer` / cash / marchand. Test de
  course d'intégration (`tests/infrastructure/test_wallet_concurrency.py`, sur l'`Engine`
  réel) : deux transferts de 8 000 lancés via une barrière de threads sur un solde de
  10 000 → exactement un `ok`, un `InsufficientFunds`, solde final = 1 936 ≥ 0.
- [x] **BE-044** · `ExpireStaleOperations` (`application/jobs/expire.py`) : passe à
  l'état expiré les retraits cash `INITIATED` périmés (**et libère la réserve**), les
  demandes de paiement `PENDING` périmées, les QR marchands `PENDING` périmés.
  Idempotent. Exposé par `flash run-jobs` (cron) et `POST /v1/admin/jobs/expire`.
- [x] **BE-045** · `ReconcileWalletBalances` (`application/jobs/reconcile.py`) : pour
  chaque portefeuille, compare `available + reserved` (projection) au solde recalculé
  depuis les postings du ledger (`LedgerRepository.wallet_balance`) ; renvoie la liste
  des écarts (lecture seule, aucune réécriture). `flash run-jobs` sort en code 1 si
  écart ; `POST /v1/admin/reconcile` (X-Admin-Key) → 200 / 409.
- [x] **BE-046** · `flash seed` (`interface/jobs_seed.py`) : 4 comptes actifs
  (1 agent avec float, 1 marchand + QR, 2 utilisateurs), les 2 utilisateurs
  approvisionnés par dépôt agent (ledger équilibré, sous le plafond palier 0).
  Idempotent. Pays / tarifs / plafonds viennent des référentiels statiques.

## Phase 3 — Épargne & carte (BE-047 → BE-060)

- [x] **BE-047** · `domain/vault/vault.py` : `Vault` (poches verrouillables sur un wallet ;
  `Wallet.vaulted` — `available` l'exclut, `balance = available + reserved + vaulted`).
  `VaultPocket` (nom, solde, objectif, `locked_until`, `progress_bps`). Invariant
  `sum(pocket.balance) == wallet.vaulted`. Tests d'invariants (domaine + wallet).
- [x] **BE-048** · `MoveToVault` / `MoveFromVault` (idempotents) : `LedgerTransaction.vault_move`
  entre analytique `client_liability` et `savings_liability` (poche coffre), instantané,
  sans frais. Historisé au relevé (`VAULT_MOVE`, sens + montant via métadonnées). Job de
  réconciliation aligné sur `wallet.balance`.
- [x] **BE-049** · `OpenVaultPocket` (nom, objectif optionnel, « verrouillé jusqu'à
  date » ISO 8601), `RenameVaultPocket`, `CloseVaultPocket` (vide obligatoire →
  `PocketNotEmpty`). Retrait avant échéance → `PocketLocked`.
- [x] **BE-050** · `domain/savings/plan.py` : `SavingsPlan` (objectif montant/date,
  `SavingsFrequency` NONE/WEEKLY/MONTHLY, `contribution`, `annual_rate_bps` ≤ 2000,
  statut ACTIVE/CLOSED). `deposit`/`withdraw`/`close`, échéancier
  (`contribution_due`/`advance_schedule`/`skip_contribution`), intérêts (`accrue`
  prorata jours dans un accumulateur micro + `capitalise` unités entières),
  `progress_bps`. Le principal vit dans `wallet.saved` (`balance = available + reserved
  + vaulted + saved`, `available` l'exclut). Tests d'invariants.
- [x] **BE-051** · `OpenSavingsPlan`, `ListSavingsPlans`, `ContributeToSavings` /
  `WithdrawFromSavings` (idempotents, `LedgerTransaction.savings_deposit` /
  `savings_withdrawal`), `CloseSavingsPlan` (tout est rapatrié au portefeuille).
- [x] **BE-052** · Job `RunScheduledSavings` : prélève les versements échus ; solde
  insuffisant → `skip_contribution` (`SavingsContributionSkipped` → notification) +
  échéance reportée, pas de boucle serrée. `flash run-jobs` + `POST /v1/admin/jobs/
  savings/contributions`.
- [x] **BE-053** · Job `AccrueSavingsInterest` : `plan.accrue` (prorata jours) puis
  `plan.capitalise` → `LedgerTransaction.interest` (`interest_expense`) + `wallet.
  add_savings_interest`. Paginé. `POST /v1/admin/jobs/savings/interest`. Tests de calcul.
- [x] **BE-054** · Blueprints `vault` (`GET /v1/vault`, `POST /pockets`, `PATCH`/`DELETE
  /pockets/<id>`, `deposit`/`withdraw`) et `savings` (`GET`/`POST /v1/savings/plans`,
  `POST /plans/<id>/{deposit,withdraw,close}`) + schémas + OpenAPI + notifications
  `VAULT` / `SAVINGS`.
- [x] **BE-055** · `domain/card/card.py` : `Card` (`pan_token` opaque, 4 derniers,
  `CardNetwork` VISA/MASTERCARD, statut ACTIVE/FROZEN/CLOSED, plafonds jour/mois,
  `CardChannel` ECOM/CONTACTLESS/ATM). `freeze`/`unfreeze`/`close` (CLOSED terminal),
  `set_limits`, `ensure_can_authorize` (→ `CardNotActive`/`ChannelDisabled`/
  `CardLimitReached`). Agrégat `CardAuthorization` (AUTHORIZED→CAPTURED/REVERSED,
  CAPTURED→REFUNDED, DECLINED). Tests d'invariants.
- [x] **BE-056** · Port `application/card/ports.py::CardIssuer` + `SandboxCardIssuer`
  (déterministe, PAN/CVV re-dérivés du token). `IssueCard` / `ListCards` / `GetCard` /
  `FreezeCard` / `UnfreezeCard` / `CloseCard` / `SetCardLimits`.
- [x] **BE-057** · Webhook `POST /v1/cards/authorizations` (signé HMAC `X-Card-Signature`) :
  `AuthorizeCardPayment` → `wallet.reserve` (aucune écriture) ; `CaptureCardPayment` →
  `settle_reservation` + `LedgerTransaction.card_capture` (`CARD_SCHEME_SUSPENSE`),
  capture partielle → `release` du reliquat ; `ReverseCardAuthorization` → `release` ;
  `RefundCardPayment` → `card_refund` + `wallet.credit`. Idempotent par `authorization_id`
  (la ligne `CardAuthorization` est l'enregistrement d'idempotence). Refus renvoyé en 200
  avec `decision`.
- [x] **BE-058** · `GetCardSensitive` : `issuer.reveal` renvoie PAN/CVV, audité
  (`CardSensitiveViewed`), route `POST /v1/cards/<id>/reveal` rate‑limitée (3 / 5 min),
  `Cache-Control: no-store`, jamais journalisé ni persisté.
- [x] **BE-059** · `ReconcileCardSettlements` : pour chaque autorisation CAPTURED/REFUNDED,
  vérifie l'écriture `CARDCAP-`/`CARDREF-` (présence, équilibre, montant net sur le
  portefeuille). `flash run-jobs` + `POST /v1/admin/jobs/cards/reconcile`.
- [x] **BE-060** · Blueprints `cards_bp` (titulaire) + `card_webhook_bp` (réseau) + schémas
  + OpenAPI + notifications `CARD` (autorisation, refus, gel, remboursement). Migration
  `e3d8b1a06f92` (`cards`, `card_authorizations`).

## Phase 4 — Multi‑pays, marchands, agents, back‑office (BE-061 → BE-078)

- [x] **BE-061** · `domain/country/reference.py` : VOs `Country` / `Operator` + port
  `ReferenceDirectory` (superset de `CountryDirectory`). `StaticReferenceDirectory` (jeu
  UEMOA + CEMAC intégré), `SqlAlchemyReferenceDirectory` (tables `countries`/`operators`,
  sessions propres), `CachingReferenceDirectory` (instantané mémoire revalidé contre
  `flash:reference:version` Redis ; `bump()` invalide tous les workers, `reload()` local).
  `flash reference seed` (idempotent) + migration `f4b7c2109ea3`. Blueprint public
  `GET /v1/reference/countries` + `/countries/<code>`. `Settings.reference_source`
  (`static` | `db`).
- [~] **BE-062** · CRUD back‑office `countries` / `operators` (rôle `admin` **ou**
  `compliance` via `require_role` + clés `ADMIN_API_KEYS`), chaque mutation tracée dans un
  **registre d'audit chaîné par hachage** (`domain/audit/` — `AuditEntry` avec
  `prev_hash`/`entry_hash`, `verify_chain` ; `SqlAlchemyAuditLog` append-only ; table
  `audit_entries`, migration `a8e3d5f10c47`). Endpoints `PUT`/`DELETE
  /v1/admin/reference/countries[/<code>/operators/<op>]`, `POST /v1/admin/reference/reload`
  (invalide le cache), `GET /v1/admin/audit?verify=1`. **Reste** : `pricing_rules` /
  `limits` éditables (nouvelles tables + repos), rôles nominatifs (BE-075).
- [x] **BE-063** · Grille tarifaire réellement par pays : CI transfert 0,8 % (80 bps),
  **SN 1,0 %** (preuve de généricité), CM/GA 0,9 % **en XAF** ; paiement marchand gratuit
  partout. Plafonds `limits` déclinés en XOF (UEMOA) et XAF (CEMAC). Tests par pays.
- [x] **BE-064** · Port `application/operators/ports.py::OperatorGateway` (`payout` /
  `collect` → `GatewayAck` accepted + external_ref, **asynchrone**) +
  `SandboxOperatorGateway` (déterministe). Agrégat `OperatorTransfer` (PENDING →
  SUCCEEDED / FAILED, idempotent) + events + `LedgerTransaction.operator_payout` /
  `operator_collect` (via `OPERATOR_SUSPENSE`). Grille `OPERATOR_PAYOUT` 1,5 % /
  `OPERATOR_COLLECT` 1 % par pays.
- [x] **BE-065** · `SendToOperatorAccount` : `wallet.reserve(amount + fee)`, appel
  `gateway.payout`, `OperatorTransfer` PENDING ; refus passerelle → `release` +
  `OperatorGatewayRejected`. Résolution sur callback : `SUCCEEDED` → `settle_reservation`
  + écriture ledger ; `FAILED` → `release`. Idempotent (`Idempotency-Key`).
- [x] **BE-066** · `TopUpFromOperator` : `OperatorTransfer` COLLECT PENDING (aucun
  mouvement de portefeuille) ; `SUCCEEDED` → `wallet.credit(amount - fee)` +
  `operator_collect`. Blueprint `POST /v1/operators/topups`.
- [x] **BE-067** · `HandleOperatorCallback` + webhook signé
  `POST /v1/operators/{operator}/callbacks` (`require_operator_webhook` HMAC du corps
  brut, `OPERATOR_WEBHOOK_SECRET`). Idempotent par `reference` (rejeu → `applied:false`) ;
  refus 422 si opérateur ≠ émetteur ou référence inconnue. Table `operator_transfers`,
  migration `b6c1e9d47f20`.
- [~] **BE-068** · `domain/merchants/` enrichi : VO `BankAccount` (IBAN/RIB masqué),
  `SettlementFrequency` (MANUAL/DAILY/WEEKLY/MONTHLY), `Merchant.configure_settlement`
  (compte bancaire + échéance `next_settlement_at`), `due_for_settlement` /
  `advance_settlement_schedule` / `record_settlement`. *Reste : sous‑comptes
  caisses/employés, frais négociés par canal.*
- [x] **BE-069** · KYB marchand : `Merchant.kyb_status` (PENDING/APPROVED/REJECTED),
  `submit_kyb` / `approve_kyb` / `reject_kyb` / `ensure_kyb_approved` + events.
  `SubmitMerchantKyb` (`POST /v1/merchant/kyb`), `ReviewMerchantKyb`
  (`POST /v1/admin/merchants/<id>/kyb`, rôles `admin`/`compliance`). Clés d'API :
  entité `MerchantApiKey` (préfixe visible + `secret_hash`, révocable), port
  `MerchantApiKeyVault` + `Sha256MerchantApiKeyVault` (secret `mk_<prefix>_<random>`,
  hash SHA-256 salé, jamais persisté en clair). `IssueMerchantApiKey`
  (`POST /v1/merchant/api-keys` → secret montré une seule fois, plafond 10 actives),
  `ListMerchantApiKeys` (`GET`), `RevokeMerchantApiKey` (`DELETE …/<id>`). Affiche
  imprimable : port `MerchantPosterRenderer` + `PillowMerchantPosterRenderer` (PNG A5
  avec QR statique), `RenderMerchantPoster` (`GET /v1/merchant/poster`, `image/png`).
  Table `merchant_api_keys` + colonnes KYB sur `merchants`, migration `d4e8a1c6b923`.
  *Note : affiche livrée en PNG (pas de dépendance PDF ajoutée).*
- [x] **BE-070** · Règlements marchands : port `application/merchants/bank.py::BankGateway`
  (`transfer` → `BankAck` synchrone) + `SandboxBankGateway` déterministe. Agrégat
  `MerchantSettlement` (PENDING → PAID / FAILED), `LedgerTransaction.merchant_settlement`
  (`MERCHANT_PAYABLE` ↓ / `BANK_SETTLEMENT` ↓). `settle_merchant` agrège le net des
  `MerchantPayment` COMPLETED non réglés, vire, rattache les paiements, avance l'échéance.
  `ConfigureMerchantSettlement` (`PUT /v1/merchant/settlement`), `SettleMerchantNow`
  (`POST /v1/merchant/settlements`), `ListMerchantSettlements`, `GetSettlementStatement`
  (relevé détaillé). Job `SettleDueMerchants` (`flash run-jobs` +
  `POST /v1/admin/jobs/merchants/settle`), notifications `SETTLEMENT`. Table
  `merchant_settlements` + colonnes règlement sur `merchants` / `merchant_payments`,
  migration `c7d2f4a91b38`.
- [x] **BE-071** · API marchande publique `Blueprint /merchant/v1` authentifiée par clé
  d'API (`Authorization: Bearer mk_…` ou `X-Merchant-Key`) → `AuthenticateMerchantApiKey`
  (401 si clé inconnue / révoquée, marchand suspendu ou KYB non validé ; horodate la
  clé). `POST /charges`, `GET /charges/<id>` (état + `payment_id` lié),
  `POST /charges/<id>/refund`, `GET /payments`. Webhooks marchand signés :
  `Merchant.configure_webhook` (URL http(s) + secret ≥ 16) via
  `PUT|DELETE /v1/merchant/webhook` ; agrégat `MerchantWebhookDelivery`
  (PENDING → DELIVERED / FAILED, backoff exponentiel, 6 tentatives) ;
  `MerchantWebhookEnqueuer` (consommateur d'événements chaîné, idempotent par
  `(event_type, payment_id)`) met en file sur `MerchantPaymentCompleted`/`Refunded` ;
  job `DispatchMerchantWebhooks` (`flash run-jobs` +
  `POST /v1/admin/jobs/merchants/webhooks`) POST le corps JSON signé
  `X-Flash-Signature: sha256=HMAC(secret, body)` via `HttpMerchantWebhookSender`. Table
  `merchant_webhook_deliveries` + colonnes `webhook_url`/`webhook_secret` sur
  `merchants`, migration `e1f4b7c92a05`.
- [x] **BE-072** · `Agent` enrichi : `parent_agent_id` + `attach_to_master` (hiérarchie
  master ↔ sous-agent), `top_up_float` / `withdraw_float` (achat / restitution d'e-money,
  events dédiés). Use cases `TopUpAgentFloat` / `WithdrawAgentFloat` (idempotents) →
  `LedgerTransaction.agent_float_topup` / `agent_float_withdraw`
  (`AGENT_FLOAT` ↔ `BANK_SETTLEMENT`). Back-office `POST /v1/admin/agents/<id>/master`
  (`AttachAgentToMaster`, rôles `admin`/`finance`).
- [x] **BE-073** · Commissions agent : `Agent.commission_earned` / `commission_paid` /
  `commission_owed` — `accrue_commission` cumule à chaque opération cash. `pay_commission`
  déplace le dû du float vers le portefeuille de l'agent
  (`LedgerTransaction.agent_commission_payout` : `AGENT_FLOAT` ↓ / `CLIENT_LIABILITY` ↑).
  `PayAgentCommission` (`POST /v1/agent/commission/payout`, montant ou tout le dû) ; job
  `PayDueAgentCommissions` (seuil, `flash run-jobs` +
  `POST /v1/admin/jobs/agents/commissions`). Relevé via `GET /v1/agent`.
- [x] **BE-074** · Espace agent API `/v1/agent` : `GET /` (float, plafond, commissions,
  master), `GET /operations` (`cash_orders.list_for_agent`), `POST /float/topup`,
  `POST /float/withdraw`, `POST /commission/payout`, `GET /customers?msisdn=`
  (`LookupCustomer` — données minimales : id, msisdn masqué, statut, palier KYC).
  Migration `f2a9c1e83b47` (colonnes `parent_agent_id` / `commission_*` sur `agents`).
- [x] **BE-075** · Back‑office comptes & support (`application/backoffice/`) :
  `SearchAccount` (`GET /v1/admin/accounts?q=` — id ou msisdn), `GetAccountDetail`
  (wallets + compteurs notes/tickets), `ListAccountTransactions` (ledger signé côté
  compte), `SetAccountFrozen` (`POST …/freeze`, motif requis pour geler),
  `ForceTransferReversal` (`POST /v1/admin/transactions/force-reversal` — contre-passe
  un `TRANSFER` hors fenêtre ; `InsufficientFunds` si le bénéficiaire a dépensé ;
  `DuplicateOperation` si déjà contre-passé). Notes `SupportNote`
  (`POST|GET …/notes`), tickets `SupportTicket` (OPEN→PENDING→RESOLVED/CLOSED,
  `POST|GET /v1/admin/tickets`, `POST …/<id>/status`). **Chaque action écrit une entrée
  d'audit chaîné** via `AuditLog` (`account.freeze`, `transaction.force_reversal`,
  `account.note`, `ticket.open`, `ticket.status`). RBAC : lectures + notes + tickets =
  `support`/`compliance`/`finance`/`admin` ; contre-passation = `finance`/`admin`.
  Tables `support_notes` / `support_tickets`, migration `a3c7e91d5f28`. `NOT_AN_AGENT`
  → 404.
- [x] **BE-076** · Conformité / AML : agrégat `ComplianceAlert` (OPEN → REVIEWING →
  CLEARED / ESCALATED). Job `ScanForAmlAlerts` (`POST /v1/admin/jobs/compliance/scan` +
  `flash run-jobs`) — lit `ledger.list_since` sur `AML_LOOKBACK_HOURS`, groupe les
  **débits** par titulaire de portefeuille, applique 3 règles paramétrables (`Settings`
  `AML_CTR_THRESHOLD_MINOR`, `AML_VELOCITY_*`, `AML_STRUCTURING_*`) : `CTR_THRESHOLD`
  (débit unitaire ≥ seuil), `STRUCTURING` (≥ N débits entre 70 % et 100 % du seuil sur
  la fenêtre, somme > seuil), `VELOCITY` (> max opérations ou > max volume sur 24 h).
  Dédoublonnage par `(user_id, kind, window_key)` (`ComplianceAlertRepository.exists_window`).
  `application/compliance/operations.py` : `ListComplianceAlerts` (file OPEN ou par
  statut), `RaiseManualAlert` (`POST /v1/admin/compliance/alerts`), `ReviewComplianceAlert`
  (`POST …/<id>/review` — `clear` = faux positif / `escalate` = **STR + `user.freeze`
  blocage préventif**), `ExportSuspiciousActivity` (`GET /v1/admin/compliance/reports/str
  ?start&end` → CSV, colonnes fixes). Chaque revue / ouverture manuelle est auditée
  (`aml.alert.manual` / `aml.alert.clear` / `aml.alert.escalate`). RBAC `compliance` /
  `admin`. Table `compliance_alerts`, migration `b8d1f6a2c904`.
- [x] **BE-077** · Exports réglementaires & compta. `application/reporting/ledger_reports.py` :
  `GetTrialBalance` (`GET /v1/admin/reports/trial-balance?as_of=` — balance générale à une
  date : par compte mouvementé du plan, cumul débit / crédit + solde signé dans le sens
  normal ; **contrôle : par devise Σ débits = Σ crédits**, `balanced:false` → HTTP 409),
  `GetLedgerJournal` (`GET …/journal?start&end&limit` — journal chronologique croissant des
  écritures + postings sur `[start, end)`), `ExportMonthlyLedger` (`GET …/monthly?year&month
  &currency=` — CSV d'un mois calendaire, une ligne par posting, filtre devise = proxy de
  zone XOF/XAF, `Content-Disposition: attachment`). Lectures seules, RBAC `finance` / `admin`.
  Ports ledger `list_between(start, end, *, limit)` + `list_accounts()` ajoutés (repo SQL +
  in-memory + round-trip Postgres). Pas de migration.
- [x] **BE-078** · Registre d'audit consultable (qui/quoi/quand/avant‑après). Le registre
  reste **append‑only + hash chaîné** (BE-062) ; cette tâche ajoute la *lecture*.
  `domain/audit/entry.py` : `audit_chain_report()` → `ChainReport(intact, checked,
  broken_at, reason)` qui localise la **première rupture** (trou de séquence,
  `prev_hash` incohérent, contenu altéré) ; `verify_chain` réécrit par‑dessus. Port
  `AuditLog` : `query(AuditFilter)` (actor / action / resource_type / resource_id /
  start / end / limit / before_sequence, plus récentes d'abord) + `verify_report()`
  (impl SQL `WHERE` + in‑memory + round‑trip Postgres). `application/audit/registry.py` :
  `QueryAuditLog` (parse ISO, `end > start`, `?verify` joint le rapport) et
  `VerifyAuditChain`. Blueprint `interface/http/audit.py` : `GET /v1/admin/audit`
  (filtres, `?verify=1`) et `GET /v1/admin/audit/verify` (409 si chaîne rompue), RBAC
  `admin` / `compliance` — l'ancienne route de `admin_reference.py` est déplacée ici.
  Pas de migration.

## Transverse (au fil des phases)

- [ ] **BE-T1** · Couverture ≥ 90 % `domain/` + `application/` (garde‑fou CI).
- [ ] **BE-T2** · Tests d'intégration DB réels (Postgres) sur repos + migrations + UoW.
- [ ] **BE-T3** · Tests de contrat OpenAPI (schemathesis) sur toutes les routes.
- [ ] **BE-T4** · Journalisation d'audit + métriques Prometheus (`/metrics`).
- [ ] **BE-T5** · `docs/api/errors.md` maintenu exhaustif (tous les `code`).
- [ ] **BE-T6** · Script de charge (locust) : transferts concurrents, objectif p95.
