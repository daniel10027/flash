# Flash — Map de développement

> **Dernière mise à jour : 2026-09-08**
> **Phase 1 terminée + Phase 2 : BE-025 → BE-031 + BE-038 (auth, numéros, wallets, transfert, relevé).**
> Domaine complet (identity + PIN Argon2, wallet, ledger partie double, pricing 0,8 %,
> limits, référentiel pays). Application : `RegisterUser`, auth (`Login`/`VerifyOtp`/
> `ResendOtp` + `TokenService`), gestion des numéros, `GetWallet`/`ListWallets`,
> **`SendP2PTransfer`** (flux §3 archi, frais 0,8 %, ledger équilibré, idempotent,
> `TransferCompleted`). Port `WorkUnitOfWork` (UoW typée) + `add_event` pour les
> événements transverses. Infra : grilles tarifaire/plafonds statiques (UEMOA).
> **15 routes** : `auth` (6), `phones` (5), `wallets` (2), `transfers` (1), `statement` (1)
> + `/health*`, `/openapi.json`, `/docs`, `/redoc`.
> **Transfert vérifié end-to-end via docker compose** : `POST /v1/transfers` → 201 (reçu
> avec frais 0,8 %), soldes émetteur/destinataire mis à jour, **ledger équilibré
> (débits = crédits = 25 200)**, `TransferCompleted` en outbox, rejeu idempotent OK.
> **`GET /v1/statement`** (BE-038) : relevé paginé par curseur, projeté du point de vue du
> client (sens in/out, montant, frais, contrepartie masquée, note) — lu directement du
> ledger. Vérifié end-to-end : émetteur voit `out 25000 / fee 200 / +225…0002`,
> destinataire voit `in 25000 / fee 0`.
> 402 tests unit + 6 d'intégration (Postgres réel), couverture 100 % domain+application,
> ruff + mypy stricts.
> **Prochaine : BE-029 (KYC par paliers), BE-032 (RequestMoney), BE-033 (paiement marchand
> QR), BE-034/035/036 (dépôt & retrait cash agent).**

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
| Backend (BE) | [docs/tasks/backend.md](docs/tasks/backend.md) | 31 / 78 |
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

## Phase 2 — Cas d'usage cœur (en cours : 7 / 22)

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

`BE-029` — `SubmitKyc` (palier 1 : pièce d'identité + selfie via port `DocumentStore`) et
`ReviewKyc` (back‑office) → change `KycTier` et recharge les limites. Puis `BE-032`
(`RequestMoney`), `BE-033` (paiement marchand QR), `BE-034` → `BE-036` (dépôt & retrait
cash en agence avec code de retrait), `BE-039` (reçu détaillé).
