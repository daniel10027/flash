# Guide d'utilisation Flash

Ce guide décrit **tous les rôles** de la plateforme et **toutes les
fonctionnalités** livrées, avec les points d'entrée (web, mobile, API) et les
comptes de démonstration pour les essayer.

- Vue d'ensemble : [`README.md`](../README.md) · Architecture :
  [`docs/architecture.md`](architecture.md) · Modèle métier :
  [`docs/domain-model.md`](domain-model.md)
- Référence API : [`docs/api/openapi.json`](api/openapi.json) (Swagger UI sur
  `http://localhost:8000/docs`) · Codes d'erreur :
  [`docs/api/errors.md`](api/errors.md)

---

## 1. Démarrer l'environnement de démonstration

**Tout (backend + web + mobile) en une commande :**

```sh
./scripts/dev.sh
```

Le script lève la pile Docker, attend l'API, détecte l'IP LAN de la machine et
lance `flutter run` sur cette IP (téléphone / émulateur du même réseau).
`SKIP_MOBILE=1 ./scripts/dev.sh` pour la pile seule.

**Ou la pile Docker seule :**

```sh
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

| Service | URL |
|---|---|
| Application web | http://localhost:5173 |
| API + doc interactive | http://localhost:8000 · http://localhost:8000/docs |
| Boîte mail (Mailhog) | http://localhost:8025 |
| Back-office | http://localhost:5173/admin |

Au démarrage l'API applique les migrations, charge le référentiel
(pays / grille tarifaire / plafonds) puis joue **`flash seed`** — le jeu de
démonstration ci-dessous (idempotent : relancer `up` ne double rien).

Les **codes OTP** (activation, connexion nouvel appareil, réinitialisation du
code secret) sont écrits dans les logs de l'API :

```sh
docker compose -f infra/docker-compose.yml logs -f api | grep -i otp
```

### Comptes de démonstration

Tous les comptes clients partagent le **code secret `1397`**.

| Numéro | Profil | KYC | Solde initial |
|---|---|---|---|
| `+2250700000101` | Cliente « Awa » | palier 0 | 150 000 XOF |
| `+2250700000102` | Client « Kofi » | palier 0 | 90 000 XOF |
| `+2250700000103` | Cliente « Fatou » | **palier 1** (dossier approuvé) | 500 000 XOF |
| `+2250700000104` | Client « Yao » | **dossier en attente** (pour la file back-office) | 120 000 XOF |
| `+2250700000199` | **Agent** « Agence Centrale » | — | float 10 000 000 XOF, commission 1 % |
| `+2250700000188` | **Marchand** « Café de la Gare » | KYB approuvé | clé d'API + 1 caisse |

Back-office (en-tête `X-Admin-Key`) :

| Rôle | Clé (dev) |
|---|---|
| Admin | `dev-admin-key` |
| Conformité | `dev-compliance-key` |
| Finance | `dev-finance-key` |

> La **clé d'API marchande** est un secret aléatoire affiché **une seule fois**
> par `flash seed` (chercher `clé d'API émise` dans les logs). En ré-émettre une
> depuis l'espace marchand si besoin.

---

## 2. Profil **Client**

Le cœur de Flash. Un client peut lier jusqu'à **5 numéros**, son solde est un
portefeuille en devise du pays (XOF en zone UEMOA). Tous les débits passent par
le **ledger en partie double** ; les frais de transfert entre particuliers sont
de **0,8 %**, affichés avant chaque envoi.

| Fonctionnalité | Web | Mobile | API |
|---|---|---|---|
| **Inscription** — numéro + pays + code secret, activation par OTP | `/register` | Onboarding → « Créer un compte » | `POST /v1/auth/register` → `POST /v1/auth/verify-otp` |
| **Connexion** — numéro + code secret ; OTP si nouvel appareil ; biométrie (mobile) | `/login` | Écran de connexion / verrou | `POST /v1/auth/login` |
| **Code secret oublié** — réinitialisation par OTP | `/login` → « Code secret oublié ? » | idem | `POST /v1/auth/reset-pin/request` → `…/confirm` |
| **Tableau de bord** — solde (masquable), 5 dernières opérations, bandeau KYC | `/` | Accueil (montant animé, raccourcis, grille de services) | `GET /v1/wallets`, `GET /v1/statement?limit=5`, `GET /v1/kyc/status` |
| **Envoyer de l'argent** — destinataire + montant, **aperçu des frais 0,8 %** et total, confirmation par code secret, reçu | `/send` | « Envoyer » | `POST /v1/transfers` |
| **Annuler un transfert** — par l'émetteur, fenêtre 1 h, refusé si le destinataire a dépensé | via l'historique | via l'historique | `POST /v1/transfers/<id>/cancel` |
| **Demander de l'argent** — créer, partager (lien / QR), listes reçues / émises, payer / refuser / annuler | `/request` | « Demander » | `POST /v1/payment-requests`, `…/<id>/{accept,decline,cancel}` |
| **Payer un marchand** — scanner un QR (statique ou dynamique) ou saisir le code, confirmation, reçu ; **gratuit pour le client** | `/pay` | Onglet « Payer » (`mobile_scanner`) | `POST /v1/merchant-payments` |
| **Recevoir** — présenter son QR personnel (montant optionnel), partage | `/receive` | « Recevoir » | (payload `flash://pay?u=<id>&amount=<minor>`) |
| **Retrait cash en agence** — générer un code à usage unique, compte à rebours d'expiration, annulation | `/cash/withdraw` | « Retirer » | `POST /v1/withdrawals`, `…/<id>/cancel` |
| **Dépôt cash en agence** — présenter son identifiant / QR à l'agent, crédit immédiat + notification | `/cash/deposit` | « Déposer » | (l'agent appelle `POST /v1/agent/deposits`) |
| **Compte opérateur** — envoyer vers un opérateur mobile money ou recharger Flash, suivi asynchrone | `/operators` | « Opérateur » | `POST /v1/operators/<op>/{payout,topup}` |
| **Historique** — liste paginée, groupée par jour, recherche / filtre, **reçu détaillé** partageable (image / PDF) | `/history` | Onglet « Historique » (scroll infini) | `GET /v1/statement`, `GET /v1/receipts/<référence>` |
| **Coffre** — poches d'épargne libres, alimenter / retirer, poche verrouillable | `/vault` | « Coffre » | `GET /v1/vault`, `POST /v1/vault/pockets`, `…/<id>/{deposit,withdraw,lock,unlock}` |
| **Épargne** — plans avec objectif et taux, progression, versement manuel, **intérêts capitalisés**, clôture | `/savings` | « Épargne » | `GET/POST /v1/savings/plans`, `…/<id>/{deposit,withdraw,close}` |
| **Carte virtuelle** — émettre, visuel, **révéler PAN / CVV 30 s**, geler / dégeler, plafonds, canaux, opérations | `/card` | Onglet « Carte » | `GET/POST /v1/cards`, `…/<id>/{sensitive,freeze,unfreeze,limits}` |
| **Mes numéros** — ajouter (OTP), définir principal, retirer (≤ 5) | `/profile` → Numéros | Profil → Mes numéros | `GET /v1/phones`, `POST /v1/phones`, `…/verify`, `…/primary`, `DELETE /v1/phones` |
| **Vérification d'identité (KYC)** — téléverser pièce + selfie, suivre le statut, retirer un dossier ; l'approbation relève le palier et donc les plafonds | `/profile` → Identité | Profil → carte KYC (photo caméra) | `GET /v1/kyc/status`, `POST /v1/kyc/submissions`, `…/<id>/withdraw` |
| **Notifications** — centre in-app, marquage lu, **flux temps réel** (SSE), push mobile (FCM), pastille de non-lus | `/notifications` | Cloche d'accueil + centre | `GET /v1/notifications`, `…/<id>/read`, `…/read-all`, **`GET /v1/notifications/stream`** |
| **Sécurité** — **appareils connectés** + déconnexion à distance, **changer le code secret** | `/profile` → Sécurité | Profil → Sécurité | `GET/DELETE /v1/auth/devices[/<id>]`, `POST /v1/auth/change-pin` |
| **Paramètres** — thème clair / sombre, langue FR / EN, masquer les soldes par défaut | `/profile` → Paramètres | Profil → Paramètres | (préférences locales) |
| **Mobile — confort** : mode hors-ligne lecture (dernier solde / historique en cache), verrou biométrie à l'ouverture, masquage du contenu dans l'aperçu multitâche, re-verrouillage après inactivité. | — | oui | — |

### Paliers KYC et plafonds

| Palier | Obtention | Effet |
|---|---|---|
| 0 | à l'inscription | plafonds bas (ex. 200 000 XOF / opération) |
| 1 | pièce d'identité + selfie approuvés | plafonds relevés |
| 2 | dossier complet (recto/verso + selfie + justificatif de domicile) | plafonds les plus élevés |

Les limites sont résolues par `(pays, palier)` **à chaque opération** : dès
qu'un palier est approuvé, les nouveaux plafonds s'appliquent.

---

## 3. Profil **Agent**

Un agent est un client dont le compte a été **enrôlé** comme agent : il détient
un **float** (encaisse cash / verse cash) plafonné, et perçoit une **commission**
sur les opérations. Chaque opération agent garde le ledger équilibré (commission
payée par Flash).

| Fonctionnalité | Web (dans l'app) | Mobile | API |
|---|---|---|---|
| **Espace agent** — tableau de bord : float disponible, commissions gagnées / dues | menu « Agent » (visible si le compte est agent) | Profil → « Espace agent » | `GET /v1/agent` |
| **Dépôt client** — l'agent encaisse les espèces, le solde du client est crédité immédiatement | Agent → Dépôt | « Dépôt client » | `POST /v1/agent/deposits` |
| **Confirmer un retrait client** — le client montre son code de retrait, l'agent le valide et remet les espèces | Agent → Retrait | « Confirmer un retrait client » | `POST /v1/agent/withdrawals/confirm` |
| **Gérer son float** — approvisionner (top-up) / retirer (withdraw) auprès du réseau | Agent → Float | via l'espace agent | `POST /v1/agent/float/{topup,withdraw}` |
| **Commissions** — consulter et déclencher le versement | Agent → tableau de bord | via l'espace agent | `POST /v1/agent/commission/payout` |
| **Journal & export** — historique des opérations agent + export CSV | Agent → Opérations | — | `GET /v1/agent/operations` |
| **Rechercher un client** | Agent → recherche | via les écrans de dépôt | `GET /v1/agent/customers?q=` |
| **Hiérarchie & commissions** — réseau d'agents (agent parent / sous-agents), partage de commission | back-office / API | — | `GET /v1/agent` (`parent_agent_id`, `sub_agents`) |

---

## 4. Profil **Marchand**

Un marchand accepte des **paiements par QR** (gratuits pour le client ; le
marchand paie `fee_bps`, net sur `MERCHANT_PAYABLE`, frais sur
`FLASH_FEE_INCOME`). Il dispose d'une **API publique** `/merchant/v1` et de
**webhooks signés**.

| Fonctionnalité | Point d'entrée | API |
|---|---|---|
| **Enrôlement** | CLI `flash merchant enroll` / back-office | `POST /v1/merchant` |
| **QR statique** — `flash://pay?m=<id>` (le client saisit le montant) | espace marchand | `GET /v1/merchant/qr` |
| **QR dynamique (charge)** — montant + référence + expiration | espace marchand / API publique | `POST /v1/merchant/charges` |
| **Vérification d'entreprise (KYB)** — soumettre, suivre ; approbation par le back-office | espace marchand | `POST /v1/merchant/kyb`, back-office `POST /v1/admin/merchants/<id>/kyb/review` |
| **Clés d'API publiques** — émettre (secret montré une fois), lister, révoquer ; ≤ 10 actives | espace marchand | `POST/GET /v1/merchant/api-keys`, `DELETE …/<id>` |
| **API marchande publique** — auth par clé, créer une charge, encaisser, consulter | serveur du marchand | `POST /merchant/v1/charges`, `/merchant/v1/payments`, … |
| **Webhooks signés** — `X-Flash-Signature: sha256=HMAC(secret, body)` sur `MerchantPaymentCompleted` / `Refunded`, backoff 6 tentatives | configuration marchand | `PUT/DELETE /v1/merchant/webhook` |
| **Sous-comptes (caisses / employés)** — `TILL` ou `EMPLOYEE`, attribution `sub_account_id` sur les paiements et le relevé | espace marchand | `GET/POST /v1/merchant/sub-accounts`, `PATCH …/<id>` |
| **Frais négociés par canal** — `QR` / `API`, taux spécifiques | back-office | `PUT /v1/admin/merchants/<id>/channel-fees/<canal>` |
| **Remboursement** — annuler un paiement reçu (`MerchantPayment` → `REFUNDED`) | espace marchand | `POST /v1/merchant-payments/<id>/refund` |
| **Relevés & règlements** — encours, virement `BANK_SETTLEMENT` via job `settle_merchants` | back-office finance | `GET /v1/merchant/settlements`, `/v1/admin/reports/…` |
| **Affiche imprimable** — QR + identité, PNG généré | espace marchand | `GET /v1/merchant/poster` |

---

## 5. Back-office (`/admin`, en-tête `X-Admin-Key`)

Arbre `/admin/*` **séparé** de l'app client. Le rôle effectif est décidé
**côté serveur** à partir de la clé (403 si insuffisant). Quatre rôles :

### 5.1 Support (`dev-admin-key`)

| Fonction | Où | API |
|---|---|---|
| **Rechercher un compte** (numéro, id, nom) | `/admin` (Comptes) | `GET /v1/admin/accounts?q=` |
| **Fiche client** — profil, KYC, wallets, appareils, historique | fiche en feuille | `GET /v1/admin/accounts/<id>` |
| **Geler / dégeler** un compte (motif obligatoire) | fiche | `POST /v1/admin/accounts/<id>/freeze` |
| **Contre-passation forcée** d'une opération (motif obligatoire) | fiche | `POST /v1/admin/transactions/force-reversal` |
| **Notes internes** | fiche | `GET/POST /v1/admin/accounts/<id>/notes` |
| **Tickets de support** | `/admin` | `GET/POST /v1/admin/tickets`, `…/<id>` |
| **File KYC** — dossiers par statut, **aperçu des pièces** (octets `no-store`), approuver / rejeter avec motif | `/admin/kyc` | `GET /v1/admin/kyc/submissions[?status]`, `…/<id>`, `…/<id>/documents/<kind>`, `…/<id>/review` |

### 5.2 Conformité (`dev-compliance-key`)

| Fonction | Où | API |
|---|---|---|
| **File d'alertes AML** par statut | `/admin/aml` | `GET /v1/admin/compliance/alerts?status=` |
| **Scan par seuils** (CTR, vélocité) | job / API | `POST /v1/admin/compliance/scan` |
| **Blocage préventif** d'un compte | fiche d'alerte | `POST /v1/admin/compliance/alerts/<id>/review` (`escalate`) |
| **Clôturer une alerte** (`clear` / `escalate` + note) | fiche d'alerte | idem |
| **Export STR / CTR** (CSV) | `/admin/aml` | `GET /v1/admin/compliance/reports/str?start=&end=` |
| **Registre d'audit** — filtré acteur / action / ressource / période | `/admin/audit` | `GET /v1/admin/audit` |
| **Contrôle d'intégrité de la chaîne d'audit** — localise la 1ʳᵉ rupture | `/admin/audit` → « Vérifier » | `GET /v1/admin/audit/verify` |

### 5.3 Finance (`dev-finance-key`)

| Fonction | Où | API |
|---|---|---|
| **Balance générale** du ledger à une date (badge d'équilibre) | `/admin/finance` | `GET /v1/admin/reports/trial-balance?as_of=` |
| **Journal des écritures** par période | `/admin/finance` | `GET /v1/admin/reports/journal?start=&end=` |
| **Export mensuel** du grand livre (CSV) | `/admin/finance` | `GET /v1/admin/reports/monthly?month=` |
| **États de règlement** marchands / agents | `/admin/finance` | `GET /v1/admin/reports/settlements` |
| **Grille tarifaire éditable** — frais 0,8 % par pays / opération | `/admin/reference` | `GET/PUT /v1/admin/reference/pricing/<code>/<op>` |
| **Plafonds éditables** — par pays / palier / opération | `/admin/reference` | `GET/PUT /v1/admin/reference/limits/<code>/<tier>/<op>` |
| **Recharger le cache** du référentiel | `/admin/reference` | `POST /v1/admin/reference/reload` |

### 5.4 Admin

Cumule tout ce qui précède + gestion du référentiel pays / opérateurs.

---

## 6. Jobs planifiés

Une passe : `flash run-jobs` (à mettre en cron ; sort **1** si un écart de
réconciliation est détecté). Déclenchables aussi par API back-office
(`POST /v1/admin/jobs/…`).

| Job | Effet |
|---|---|
| `ExpireStaleOperations` | retraits / demandes / QR périmés → expirés, réserve libérée |
| `ReconcileWalletBalances` | compare la projection au solde recalculé du ledger, signale les écarts |
| `RunScheduledSavings` | versements d'épargne échus (report si fonds insuffisants) |
| `AccrueSavingsInterest` | calcul + capitalisation des intérêts |
| `SettleDueMerchants` | virements de règlement marchands via `BankGateway` |
| `DispatchMerchantWebhooks` | livraison des webhooks signés, backoff 6 tentatives |
| `PayDueAgentCommissions` | versement des commissions agent dues |
| `ReconcileCardSettlements` | rapprochement des règlements carte |

---

## 7. Parcours de démonstration (pas à pas)

1. **Ouvrir l'app** http://localhost:5173 → traverser l'onboarding → « Créer un
   compte » ou se connecter avec `+2250700000101` / `1397` (OTP dans les logs API).
2. **Envoyer** 10 000 XOF à `+2250700000102` : constater l'aperçu des frais
   (80 XOF), confirmer par code secret, voir le reçu, puis le solde mis à jour.
3. **Payer un marchand** : sur `/pay`, saisir le code
   `flash://pay?m=<id du marchand>` (dans les logs `flash seed`), payer 2 000 XOF.
4. **Retrait cash** : `/cash/withdraw` → générer un code.
5. **Côté agent** : se connecter avec `+2250700000199`, ouvrir « Espace agent »,
   « Confirmer un retrait client » avec le code généré à l'étape 4.
6. **Back-office KYC** : http://localhost:5173/admin, clé `dev-admin-key`, onglet
   KYC → le dossier de `+2250700000104` est **en attente** → ouvrir, voir les
   pièces, approuver.
7. **Finance** : clé `dev-finance-key` → `/admin/finance` → balance générale du
   jour, vérifier le **badge d'équilibre** (débits = crédits).
8. **Notifications** : revenir côté client, la cloche affiche les opérations
   reçues en **temps réel** (SSE).

---

## 8. Limites connues / hors périmètre

Le logiciel est complet côté fonctionnel, mais **opérer réellement** exige :
agrément **BCEAO**, intégrations **bancaires / opérateurs / réseau carte** de
production (aujourd'hui des adaptateurs *sandbox* : `OPERATOR_GATEWAY`,
`CARD_ISSUER`, `BANK_GATEWAY`), audits **PCI-DSS** et sécurité, campagne de
tests de charge sur l'infrastructure cible. Les notifications **push** mobile
nécessitent une configuration Firebase (`flutterfire configure`) — sans elle,
l'app fonctionne, seul le push est inactif.
