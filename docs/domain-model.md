# Modèle de domaine — Flash

Langage omniprésent + agrégats, invariants et événements. Sert de contrat pour le code
de `backend/src/flash/domain/`. Les identifiants sont des UUIDv7 (`EntityId`).

## 1. Glossaire

| Terme | Définition |
|---|---|
| **Wallet** | Solde d'un utilisateur dans une devise. Projection du ledger. |
| **Ledger** | Grand livre en partie double. Seule source de vérité des montants. |
| **Posting** | Une ligne du ledger : compte, sens (débit/crédit), montant, wallet lié. |
| **LedgerTransaction** | Ensemble de postings équilibrés (somme = 0 par devise), immuable. |
| **Coffre (Vault)** | Poches d'un wallet, fonds mis de côté, exclus du disponible. |
| **Plan d'épargne** | Objectif + versements programmés + intérêts. |
| **Agent** | Point cash. Détient un *float*. Encaisse/décaisse pour les clients. |
| **Marchand** | Accepte des paiements par QR. Règlement différé. |
| **Code de retrait** | Jeton à usage unique généré par le client, saisi par l'agent. |
| **KYC tier** | Palier de vérification (0/1/2) → limites différentes par pays. |
| **Frais** | 0,8 % sur les transferts par défaut, paramétrable par pays/opération. |
| **Idempotency-Key** | En‑tête client garantissant qu'une opération n'est jouée qu'une fois. |

## 2. Value Objects

- **Currency** : `code` (ISO 4217, ex. `XOF`), `exponent` (XOF → 0). Immuable.
- **Money** : `amount_minor: int` + `currency`. Jamais de float. Opérations refusant les
  devises mixtes. `percentage(bps)` pour les frais. `is_negative/zero/positive`.
- **CountryCode** : ISO 3166‑1 alpha‑2 (`CI`, `SN`, …).
- **Msisdn** : numéro E.164 validé, connaît son `CountryCode` via indicatif.
- **Pin** : 4–6 chiffres, rejette `0000`, `1234`, `123456`, répétitions. Jamais stocké en
  clair (hashé par `PinHasher` → Argon2id dans l'infra).
- **IdempotencyKey** : chaîne opaque 8–255, scoping `(user_id, route, key)`.
- **Fee** : `amount: Money` + `breakdown` (part Flash, part opérateur, taxe éventuelle).
- **ExchangeRate** : `pair`, `rate`, `as_of` (phase multi‑devises).
- **WithdrawalCode** : `code` (6–8 chiffres/lettres non ambigus), `expires_at`, `status`.
- **KycTier** : `0 | 1 | 2`.

## 3. Agrégats et invariants

### User  *(racine)*
Champs : `id`, `status` (`PENDING_ACTIVATION | ACTIVE | FROZEN | CLOSED`), `kyc_tier`,
`phone_numbers: PhoneNumber[]`, `country`, `created_at`.
`PhoneNumber` : `msisdn`, `is_primary`, `verified_at`, `linked_at`.

Invariants :
- **1 à 5** `PhoneNumber` par utilisateur. Ajout au‑delà → `PhoneNumberLimitReached`.
- Exactement **un** `is_primary` à tout moment (si actif).
- Un `msisdn` est lié à **au plus un** `User` (unicité globale) → `PhoneNumberAlreadyLinked`.
- On ne supprime pas le dernier numéro → `CannotRemoveLastPhoneNumber`.
- Supprimer le principal exige de promouvoir un autre numéro d'abord (ou promotion auto
  du plus ancien vérifié, choix figé : **promotion explicite requise**).
- `FROZEN`/`CLOSED` → aucune opération monétaire sortante.

Événements : `UserRegistered`, `PhoneNumberAdded`, `PhoneNumberVerified`,
`PhoneNumberRemoved`, `PrimaryPhoneNumberChanged`, `KycTierChanged`, `UserFrozen`,
`UserUnfrozen`, `UserClosed`.

### Wallet  *(racine)*
Champs : `id`, `user_id`, `currency`, `status` (`ACTIVE | FROZEN`), `available: Money`,
`reserved: Money`, `vault_total: Money` (dérivé).

Invariants :
- `available >= 0` et `reserved >= 0` à tout instant.
- `available` exclut `reserved` (réservations retrait/carte) **et** `vault_total`.
- Toute variation de `available`/`reserved` provient d'une `LedgerTransaction` appliquée
  dans la même UoW ; pas de setter public libre.
- Un seul wallet par `(user_id, currency)`.

Événements : `WalletOpened`, `WalletCredited`, `WalletDebited`, `FundsReserved`,
`FundsReleased`, `WalletFrozen`, `WalletUnfrozen`.

### Ledger

**LedgerAccount** : `id`, `type` (`CLIENT_LIABILITY`, `FLASH_FEE_INCOME`, `AGENT_FLOAT`,
`AGENT_COMMISSION_EXPENSE`, `OPERATOR_SUSPENSE`, `CARD_SCHEME_SUSPENSE`,
`SAVINGS_LIABILITY`, `INTEREST_EXPENSE`, `BANK_SETTLEMENT`, `ROUNDING`,
`MERCHANT_PAYABLE`), `owner_ref` (user/agent/merchant/null), `currency`,
`normal_balance` (`DEBIT | CREDIT`).

**Posting** : `ledger_account_id`, `direction`, `amount: Money`, `wallet_id?`,
`analytic?` (ex. poche de coffre, plan d'épargne).

**LedgerTransaction** : `id`, `kind`, `postings: Posting[]`, `occurred_at`, `reference`,
`reason`, `metadata`, `reverses_transaction_id?`.

Invariants :
- Au moins 2 postings. Pour **chaque devise** présente : `Σ débits == Σ crédits`.
- Montants strictement positifs dans chaque posting (le sens porte le signe).
- Immuable après création. Correction = nouvelle transaction `kind=REVERSAL` pointant
  `reverses_transaction_id`.
- `kind ∈ { TRANSFER, FEE, CASH_IN, CASH_OUT, VAULT_MOVE, SAVINGS_DEPOSIT,
  SAVINGS_WITHDRAWAL, INTEREST, CARD_AUTH, CARD_CAPTURE, CARD_REFUND, OPERATOR_PAYOUT,
  OPERATOR_COLLECT, MERCHANT_SETTLEMENT, AGENT_FLOAT_TOPUP, AGENT_COMMISSION_PAYOUT,
  REVERSAL, ADJUSTMENT }`.

Fabriques (garantissent l'équilibre) : `LedgerTransaction.transfer(src_wallet,
dst_wallet, amount, fee)`, `.cash_in(agent, client_wallet, amount, commission)`,
`.cash_out(client_wallet, agent, amount, fee, commission)`, `.vault_move(wallet, pocket,
amount, direction)`, `.interest(plan, wallet, amount)`, `.reversal(original)`, etc.

### Transfer  *(processus, pas de solde propre)*
Champs : `id`, `sender_id`, `recipient_id`, `amount`, `fee`, `status`
(`COMPLETED | REVERSED`), `ledger_transaction_id`, `created_at`.
Règles : KYC suffisant (`KycPolicy`), sous limites (`LimitPolicy`), `available >=
amount + fee`. Annulable pendant `reversal_window` (config pays) si le destinataire n'a
pas déjà dépensé (règle : autorisé même si dépensé → passe le destinataire en négatif ?
**Non** : reversal refusé si `recipient.available < amount` → `RefundNotPossible`, gérer
en litige).
Événements : `TransferCompleted`, `TransferReversed`.

### MerchantPayment
`id`, `payer_id`, `merchant_id`, `till_id?`, `amount`, `fee` (grille marchand),
`reference`, `status` (`COMPLETED | REFUNDED`), `ledger_transaction_id`.
Le crédit va sur `MERCHANT_PAYABLE` (dette Flash → marchand), soldé par
`MerchantSettlement`.
Événements : `MerchantPaymentCompleted`, `MerchantPaymentRefunded`.

### CashOrder  *(dépôt ou retrait)*
`id`, `type` (`DEPOSIT | WITHDRAWAL`), `client_id`, `agent_id?`, `amount`, `fee`
(retrait uniquement), `agent_commission`, `status`, `withdrawal_code?`, `expires_at?`,
`ledger_transaction_id?`.

Retrait — machine à états : `INITIATED` (réserve `amount+fee` sur le wallet, code émis)
→ `CONFIRMED` (agent saisit le code : débit client, crédit `AGENT_FLOAT`, frais →
`FLASH_FEE_INCOME`, commission → `AGENT_COMMISSION_EXPENSE`) ou `EXPIRED`/`CANCELLED`
(réserve libérée). Le code est à **usage unique**, essais de saisie limités.

Dépôt : `INITIATED` (agent identifie le client) → `CONFIRMED` (débit `AGENT_FLOAT`,
crédit wallet client, commission agent). Vérifie `agent.float.available >= amount` →
`AgentFloatTooLow`. Vérifie `client_wallet.balance + amount <= balance_max(tier,pays)`.

Événements : `CashDepositCompleted`, `CashWithdrawalInitiated`, `CashWithdrawalConfirmed`,
`CashWithdrawalExpired`, `CashWithdrawalCancelled`.

### Vault
`id`, `wallet_id`, `pockets: VaultPocket[]`.
`VaultPocket` : `id`, `name`, `balance: Money`, `goal_amount?`, `locked_until?`.
Invariants : `Σ pockets.balance == wallet.vault_total` ; sortie d'une poche
`locked_until` dans le futur → `PocketLocked` (sauf clôture d'urgence tracée) ;
suppression d'une poche non vide → `PocketNotEmpty`.
Événements : `VaultPocketCreated`, `MovedToVault`, `MovedFromVault`,
`VaultPocketClosed`.

### SavingsPlan
`id`, `wallet_id`, `name`, `goal_amount?`, `goal_date?`, `frequency`
(`NONE | DAILY | WEEKLY | MONTHLY`), `contribution: Money`, `annual_rate_bps`,
`principal: Money`, `accrued_interest: Money`, `status` (`ACTIVE | CLOSED`),
`next_run_at?`.
Règles : versement programmé prélève `contribution` du wallet (`SAVINGS_DEPOSIT`) ;
échec si solde insuffisant → notification + réessai selon politique ; intérêts courus
quotidiennement (`principal * rate / 365`), capitalisés mensuellement (`INTEREST`).
Clôture → `SAVINGS_WITHDRAWAL` de `principal + accrued_interest` vers le wallet.
Événements : `SavingsPlanOpened`, `SavingsContributionMade`, `SavingsInterestAccrued`,
`SavingsPlanClosed`.

### Card
`id`, `wallet_id`, `pan_token`, `last4`, `network`, `status`
(`ACTIVE | FROZEN | CLOSED`), `limits` (`per_tx`, `daily`, `monthly`),
`channels` (`ecommerce`, `contactless`), `expiry`.
Flux : autorisation → `FundsReserved` + `CARD_AUTH` sur `CARD_SCHEME_SUSPENSE` ;
capture → `CARD_CAPTURE` (débit wallet, solde du suspense) ; remboursement → `CARD_REFUND`.
Invariants : opérations refusées si `status != ACTIVE`, hors plafonds, ou canal désactivé.
Événements : `CardIssued`, `CardFrozen`, `CardUnfrozen`, `CardClosed`,
`CardAuthorized`, `CardCaptured`, `CardRefunded`, `CardLimitReached`.

### Agent
`id`, `user_id`, `float: Wallet‑like` (compte `AGENT_FLOAT`), `commission_schedule`,
`caps` (par opération / jour), `parent_agent_id?`, `status`.
Événements : `AgentFloatToppedUp`, `AgentCommissionAccrued`, `AgentCommissionPaidOut`.

### Merchant
`id`, `user_id`, `category`, `pricing` (grille propre), `settlement_account`,
`tills: Till[]`, `api_keys`, `status`, `kyb_status`.
Événements : `MerchantOnboarded`, `MerchantSettled`.

### Country  *(référentiel, quasi‑statique)*
`code`, `currency`, `timezone`, `rounding_rule` (`UP_TO_UNIT | HALF_UP | …`),
`default_operator`, `operators[]`, `pricing_rules[]`, `limits[]` (par KYC tier),
`reversal_window`.
Chargé au démarrage, mis en cache Redis, rechargeable via back‑office (événement
`ReferenceDataChanged` → invalidation).

## 4. Politiques (services de domaine)

- **PricingService** : `fee_for(country, operation, amount) -> Fee`. Transfert :
  `base = amount * bps / 10_000`, applique `min_fee`/`max_fee`/`fixed_fee`, arrondit
  selon `country.rounding_rule`. XOF : arrondi à l'unité supérieure, jamais 0 si montant
  > 0 (plancher = `min_fee` ou 1 unité). Déterministe, testé aux bornes.
- **LimitPolicy** : vérifie `per_tx`, `daily`, `monthly` selon `(country, kyc_tier,
  operation)` via `LimitCounter` (somme glissante). Dépassement → `LimitExceeded` avec
  `remaining`.
- **KycPolicy** : opération autorisée pour le tier courant ? sinon `KycRequired(min_tier)`.
- **TransferPolicy** : compose KYC + limites + solde + statut + anti‑auto‑transfert.
- **ReversalPolicy** : fenêtre temporelle + faisabilité (fonds encore présents).

## 5. Erreurs de domaine (codes stables)

`INSUFFICIENT_FUNDS`, `LIMIT_EXCEEDED`, `KYC_REQUIRED`, `PHONE_NUMBER_LIMIT_REACHED`,
`PHONE_NUMBER_ALREADY_LINKED`, `CANNOT_REMOVE_LAST_PHONE_NUMBER`,
`DUPLICATE_OPERATION`, `WALLET_FROZEN`, `USER_FROZEN`, `AGENT_FLOAT_TOO_LOW`,
`WITHDRAWAL_CODE_INVALID`, `WITHDRAWAL_CODE_EXPIRED`, `POCKET_LOCKED`,
`POCKET_NOT_EMPTY`, `CARD_NOT_ACTIVE`, `CARD_LIMIT_REACHED`, `CHANNEL_DISABLED`,
`REFUND_NOT_POSSIBLE`, `SELF_TRANSFER`, `CURRENCY_MISMATCH`, `BALANCE_CAP_EXCEEDED`,
`OTP_INVALID`, `OTP_TOO_MANY_ATTEMPTS`, `RATE_LIMITED`.
→ Table maintenue et mappée en HTTP dans `docs/api/errors.md` (tâche `BE-T5`).

## 6. Événements & effets de bord

Les use cases collectent les événements des agrégats et les publient via `EventPublisher`
(pattern **outbox** : écrits en base dans la même transaction, dépilés par un worker).
Handlers : notifications (push/in‑app/email), alimentation des projections de lecture
(`statement_entries`, `wallet_balances`), alertes AML, métriques. Les handlers sont
**idempotents** et rejouables.
