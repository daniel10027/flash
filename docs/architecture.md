# Architecture — Flash

## 1. Vue d'ensemble

Monorepo, 3 clients (web React, mobile Flutter, futurs partenaires via API) parlant à
**une seule API** (`backend/`). Le backend suit une **architecture hexagonale**
(ports & adapters) avec une orientation *clean architecture* : la règle de dépendance
pointe toujours vers l'intérieur.

```
                       ┌─────────────────────────────────────────┐
   HTTP / CLI / Cron ──▶│  interface/  (Flask blueprints, DTO,    │
                        │              schémas, mappers, docs)    │
                        └───────────────┬─────────────────────────┘
                                        │ appelle (use cases)
                        ┌───────────────▼─────────────────────────┐
                        │  application/  (services applicatifs,   │
                        │   orchestration, transactions, UoW,     │
                        │   politiques, événements)               │
                        └───────────────┬─────────────────────────┘
                                        │ dépend de (ports + modèle)
                        ┌───────────────▼─────────────────────────┐
                        │  domain/  (entités, agrégats, VO,       │
                        │   invariants, services de domaine,      │
                        │   ports = interfaces, erreurs métier)   │
                        └───────────────▲─────────────────────────┘
                                        │ implémente (adapters)
                        ┌───────────────┴─────────────────────────┐
                        │  infrastructure/  (SQLAlchemy repos,    │
                        │   Alembic, Redis, FCM, SMTP, SMS,       │
                        │   adapters opérateurs, horloge, UUID,   │
                        │   idempotence, chiffrement)             │
                        └─────────────────────────────────────────┘
```

**Le paquet `domain/` n'importe rien d'externe** (pas de Flask, pas de SQLAlchemy, pas de
`requests`). Il ne connaît que la bibliothèque standard et lui‑même. Vérifié par un test
d'architecture (`tests/architecture/test_dependencies.py`, tâche `BE-023`).

## 2. Couches et responsabilités

### `domain/`
- **Value Objects** : `Money`, `Currency`, `CountryCode`, `Msisdn` (numéro E.164),
  `Pin`, `IdempotencyKey`, `Fee`, `ExchangeRate`.
- **Agrégats** :
  - `User` (identité, statut KYC, jusqu'à **5** `PhoneNumber`, dont un principal).
  - `Wallet` (un par utilisateur et par devise ; solde = projection du ledger).
  - `LedgerAccount` (compte comptable : utilisateur, agent, marchand, frais, réserve,
    passif client, suspens opérateur…).
  - `LedgerTransaction` (ensemble de `Posting` équilibrés, immuable une fois validée).
  - `Vault` (coffre : sous‑soldes verrouillables rattachés à un wallet).
  - `SavingsPlan` (objectif, versements programmés, intérêts).
  - `Card` (carte virtuelle : PAN tokenisé, plafonds, statut).
  - `Agent`, `Merchant`, `CashOrder` (dépôt/retrait cash), `Transfer`, `MerchantPayment`.
- **Services de domaine** : `PricingService` (calcul des frais 0,8 % selon pays),
  `TransferPolicy`, `KycPolicy`, `LimitPolicy`.
- **Ports** (interfaces, définies ici, implémentées dans `infrastructure/`) :
  `UserRepository`, `WalletRepository`, `LedgerRepository`, `Clock`, `IdGenerator`,
  `IdempotencyStore`, `OtpChannel`, `PushSender`, `Mailer`, `OperatorGateway`,
  `CardIssuer`, `UnitOfWork`, `EventPublisher`, `RateProvider`.
- **Erreurs** : hiérarchie `DomainError` (`InsufficientFunds`, `LimitExceeded`,
  `KycRequired`, `PhoneNumberLimitReached`, `DuplicateOperation`, `AgentFloatTooLow`…).

### `application/`
- Un **use case = une classe** avec `execute(command) -> result`.
  Ex. `RegisterUser`, `AddPhoneNumber`, `SendP2PTransfer`, `PayMerchant`,
  `CreateCashDeposit`, `ConfirmCashWithdrawal`, `MoveToVault`, `OpenSavingsPlan`,
  `IssueCard`, `ListStatement`.
- Ouvre une **Unit of Work** (= transaction DB), charge les agrégats via les ports,
  applique la logique de domaine, persiste, publie les événements, renvoie un DTO.
- Applique l'**idempotence** : si la clé existe, renvoie le résultat mémorisé.
- Aucune règle métier « dure » ici : uniquement de l'orchestration.

### `interface/`
- **Flask** : app factory (`create_app`), blueprints par ressource, gestion centralisée
  des erreurs (mappe `DomainError` → HTTP + code stable), auth (JWT), rate‑limit,
  `request_id`, journalisation JSON.
- **Schémas** (pydantic v2) pour valider l'entrée et sérialiser la sortie. Les schémas
  ne fuient jamais vers `application/` : mapping DTO ↔ commande dans le blueprint.
- **OpenAPI** généré depuis les schémas + routes → `docs/api/openapi.json`, servi sur
  `/docs` (Swagger UI) et `/redoc`.
- Points d'entrée non‑HTTP : commandes CLI (`flask flash create-country …`), tâches
  planifiées (intérêts d'épargne, expiration des codes de retrait).

### `infrastructure/`
- `db/` : modèles SQLAlchemy 2 (mapping impératif, séparés des entités de domaine),
  `SqlAlchemyUnitOfWork`, repos concrets, migrations Alembic.
- `cache/` : Redis (idempotence, OTP, rate‑limit, verrous, pub/sub SSE).
- `notifications/` : `FcmPushSender`, `SmtpMailer`, `ConsoleOtpChannel` (dev) /
  `HttpSmsOtpChannel` (prod), `InAppNotificationStore`.
- `operators/` : `SandboxOperatorGateway` (simule Orange Money / MTN / Moov), interface
  prête pour les vrais connecteurs.
- `cards/` : `SandboxCardIssuer`.
- `crypto/` : chiffrement au repos des données sensibles (PIN → Argon2id, PAN → token).
- `time/` : `SystemClock` ; `uuid/` : `Uuid7Generator`.

## 3. Flux type — transfert P2P

1. `POST /v1/transfers` avec `Idempotency-Key`. Le blueprint valide le schéma, construit
   `SendP2PTransferCommand`, appelle le use case.
2. `SendP2PTransfer.execute` : ouvre l'UoW ; vérifie l'idempotence ; charge l'émetteur,
   le destinataire (par `Msisdn`), leurs wallets XOF.
3. `PricingService.fee_for(country, amount)` → frais = `arrondi(amount * 0,008)` selon la
   règle d'arrondi du pays (au FCFA supérieur, jamais négatif, plancher/plafond éventuels).
4. `TransferPolicy` + `LimitPolicy` : KYC suffisant ? plafonds jour/mois ? solde ≥
   montant + frais ?
5. Construction d'une `LedgerTransaction` :
   - débit *passif client / wallet émetteur* : `montant + frais`
   - crédit *passif client / wallet destinataire* : `montant`
   - crédit *produits / compte de frais Flash* : `frais`
   - somme des postings = 0 (invariant vérifié à la construction).
6. `LedgerRepository.add(txn)` ; `WalletRepository` met à jour les projections de solde ;
   `EventPublisher.publish(TransferCompleted)`.
7. Commit UoW. Les *event handlers* envoient les notifications (push + in‑app) hors
   transaction. Réponse `201` avec le reçu.

## 4. Argent & comptabilité

- Montants stockés en **entiers, unité mineure** (XOF n'a pas de sous‑unité → facteur 1 ;
  le VO `Currency` porte `exponent`).
- **Partie double** obligatoire. Plan de comptes minimal :
  `client_liability`, `flash_fee_income`, `agent_float`, `agent_commission_expense`,
  `operator_suspense`, `card_scheme_suspense`, `savings_liability`, `interest_expense`,
  `bank_settlement`, `rounding`.
- Chaque `Posting` : `(ledger_account_id, direction[DEBIT|CREDIT], Money, wallet_id?)`.
- Le solde d'un wallet = somme signée des postings de son `client_liability` analytique.
  Une table de **projection** `wallet_balances` est maintenue dans la même transaction
  pour les lectures rapides ; un job de contrôle (`INFRA` / `BE`) recompute et compare.
- Rien ne modifie un solde sans `LedgerTransaction`. Les remboursements/annulations
  créent une transaction inverse, jamais une suppression.

## 5. Multi‑pays

Table `countries` : `code` (CI, SN, ML, BF, BJ…), `currency`, `timezone`,
`rounding_rule`, `default_operator`. Table `pricing_rules` : `country_code`,
`operation_type`, `percent_bps` (transfert = **80 bps = 0,8 %**), `min_fee`, `max_fee`,
`fixed_fee`. Table `limits` : `country_code`, `kyc_tier`, `per_tx`, `daily`, `monthly`,
`balance_max`. Aucune de ces valeurs n'est en dur : chargées au démarrage + cache Redis,
rechargeables via le back‑office.

## 6. Sécurité (résumé — détail dans `docs/tasks/infra.md`)

- Auth : `Msisdn` + PIN (Argon2id) + OTP à l'enrôlement d'appareil ; JWT access court
  (15 min) + refresh rotatif lié à l'appareil ; révocation par `jti` en liste Redis.
- Rate‑limit par IP + par sujet sur les routes sensibles (OTP, login, transferts).
- Idempotence obligatoire sur toute route qui déplace de l'argent.
- Journsplit : logs JSON sans PII en clair ; PAN/PIN jamais journalisés.
- Chiffrement au repos des colonnes sensibles ; secrets via variables d'environnement /
  secret store du VPS, jamais dans le dépôt.
- `.env.example` documente toutes les variables ; `.env` est git‑ignoré.

## 7. Tests

- `tests/domain/` : purs, sans I/O, rapides. Couvrent tous les invariants.
- `tests/application/` : use cases avec adapters **en mémoire** (fakes fournis).
- `tests/interface/` : Flask test client + DB éphémère (Postgres via testcontainers ou
  service CI).
- `tests/architecture/` : interdit les imports sortants depuis `domain/`.
- Objectif de couverture : **≥ 90 %** sur `domain/` et `application/`.
